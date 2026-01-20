'''
新的设计，把旧的BufferModel和MeshExporter以及ObjDataModel整合到一起了
因为从结果上来看，BufferModel和MeshExporter只调用了一次，属于严重浪费
不如直接传入d3d11_game_type和obj_name到ObjBufferModel，然后直接一次性得到所有的内容

ObjBufferModel一创建，就自动把所有的内容都搞定了，后面只需要直接拿去使用就行了
'''

import collections
import numpy
import bpy

from dataclasses import dataclass, field
from typing import Dict

from ..utils.format_utils import FormatUtils, Fatal
from ..utils.timer_utils import TimerUtils
from ..utils.vertexgroup_utils import VertexGroupUtils
from ..utils.obj_utils import ObjUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from ..base.obj_data_model import ObjDataModel

@dataclass
class ObjElementModel:
    '''
    这个类只负责把Blender的数据转换为element_ndarray的dict
    然后后面可以根据element来获取其数据就足够了

    TODO 目前的架构还是有问题，这里应该是先从obj获取数据
    获取的数据根据Element存放好
    后面再来一层转换层，把数据再转换为带dtype的形式，而不是在这里创建的时候就转换好
    不然的话就会遇到uint8但是实际上需要uint16的情况
    然后这个uint8声明的时候就限制死了dtype导致后续替换流程特别麻烦
    所以现在这么复杂，基本上就是由于层级拆分不明确导致的，后面必须重构

    TODO 暂时先不管了，先去完成ini生成的部分，不然不管我们怎么改，都无法去游戏里验证实际效果
    修改完ini的部分就回来拆分这里的部分。

    '''
    # 初始化时必须填的字段
    d3d11_game_type:D3D11GameType
    obj_name:str
    # Note: previously this class accepted a `blendindices_override`
    # parameter to allow callers to provide remapped BLENDINDICES before
    # packing. That facility has been removed — callers should now modify
    # `elementname_data_dict['BLENDINDICES']` after parsing and before
    # calling `fill_into_element_vertex_ndarray()`.

    # 外用字段
    obj:bpy.types.Object = field(init=False,repr=False)
    mesh:bpy.types.Mesh = field(init=False,repr=False)
    total_structured_dtype:numpy.dtype = field(init=False, repr=False)

    # 数据先从obj中提取出来，按 ElementName 放到这个 Dict 中，作为原始未修改数据
    original_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)

    # 在外部对原始数据进行修改/remap 后，结果应写入 final_elementname_data_dict
    # 然后再由 fill_into_element_vertex_ndarray() 优先使用 final 的内容进行打包。
    final_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)

    # 然后再把数据写入
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    def __post_init__(self) -> None:
        '''
        使用Numpy直接从指定名称的obj的mesh中转换数据到目标格式Buffer
        '''
        self.obj = ObjUtils.get_obj_by_name(name=self.obj_name)

        self.check_and_verify_attributes()
        
        mesh = ObjUtils.get_mesh_evaluate_from_obj(obj=self.obj)
        # 三角化mesh
        ObjUtils.mesh_triangulate(mesh)
        # Calculates tangents and makes loop normals valid (still with our custom normal data from import time):
        # 前提是有UVMap，前面的步骤应该保证了模型至少有一个TEXCOORD.xy
        mesh.calc_tangents()
        self.mesh = mesh
        # Cache frequently accessed mesh collections/lengths to avoid repeated attribute lookups
        self.mesh_loops = mesh.loops
        self.mesh_loops_length = len(self.mesh_loops)
        self.mesh_vertices = mesh.vertices
        self.mesh_vertices_length = len(self.mesh_vertices)
        self.vertex_colors = mesh.vertex_colors
        self.uv_layers = mesh.uv_layers
    
        # 读取并解析数据（填充到 `original_elementname_data_dict`）
        # NOTE: we only parse into `original_elementname_data_dict` here and defer
        # packing into the structured `element_vertex_ndarray` until an
        # external caller invokes `fill_into_element_vertex_ndarray()`.
        # This allows callers to modify `final_elementname_data_dict` (for
        # example, to apply per-component BLENDINDICES remaps) before the
        # structured dtype is allocated and packed, avoiding uint8
        # truncation issues.
        self.parse_elementname_data_dict()

    def check_and_verify_attributes(self):
        '''
        校验并补全部分元素
        COLOR
        TEXCOORD、TEXCOORD1、TEXCOORD2、TEXCOORD3
        '''
        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            d3d11_element = self.d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]
            # 校验并补全所有COLOR的存在
            if d3d11_element_name.startswith("COLOR"):
                if d3d11_element_name not in self.obj.data.vertex_colors:
                    self.obj.data.vertex_colors.new(name=d3d11_element_name)
                    print("当前obj ["+ self.obj.name +"] 缺少游戏渲染所需的COLOR: ["+  "COLOR" + "]，已自动补全")
            
            # 校验TEXCOORD是否存在
            if d3d11_element_name.startswith("TEXCOORD"):
                if d3d11_element_name + ".xy" not in self.obj.data.uv_layers:
                    # 此时如果只有一个UV，则自动改名为TEXCOORD.xy
                    if len(self.obj.data.uv_layers) == 1 and d3d11_element_name == "TEXCOORD":
                            self.obj.data.uv_layers[0].name = d3d11_element_name + ".xy"
                    else:
                        # 否则就自动补一个UV，防止后续calc_tangents失败
                        self.obj.data.uv_layers.new(name=d3d11_element_name + ".xy")
            
            # Check if BLENDINDICES exists
            if d3d11_element_name.startswith("BLENDINDICES"):
                if not self.obj.vertex_groups:
                    raise Fatal("your object [" +self.obj.name + "] need at leat one valid Vertex Group, Please check if your model's Vertex Group is correct.")


    def fill_into_element_vertex_ndarray(self):
        # Create the element array with the original dtype (matching ByteWidth)
        self.element_vertex_ndarray = numpy.zeros(self.mesh_loops_length, dtype=self.total_structured_dtype)
        # For each expected element, prefer the remapped/modified value in
        # `final_elementname_data_dict` if present; otherwise use the parsed
        # value from `original_elementname_data_dict`.
        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            if d3d11_element_name in self.final_elementname_data_dict:
                data = self.final_elementname_data_dict[d3d11_element_name]
            else:
                data = self.original_elementname_data_dict.get(d3d11_element_name, None)

            if data is None:
                # Missing data is a fatal condition — better to raise so caller
                # can diagnose than to silently write zeros for an expected
                # element (which would corrupt downstream buffers).
                raise Fatal(f"Missing element data for '{d3d11_element_name}' when packing vertex ndarray")
            print("尝试赋值 Element: " + d3d11_element_name)
            self.element_vertex_ndarray[d3d11_element_name] = data

    
    def parse_elementname_data_dict(self):
        '''
        - 注意这里是从mesh.loops中获取数据，而不是从mesh.vertices中获取数据
        - 所以后续使用的时候要用mesh.loop里的索引来进行获取数据
        '''

        mesh_loops = self.mesh_loops
        mesh_loops_length = self.mesh_loops_length
        mesh_vertices = self.mesh_vertices
        mesh_vertices_length = self.mesh_vertices_length

        loop_vertex_indices = numpy.empty(mesh_loops_length, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)


        self.total_structured_dtype = numpy.dtype([])

        # 预设的权重个数，也就是每个顶点组受多少个权重影响
        blend_size = 4

        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            d3d11_element = self.d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]
            np_type = FormatUtils.get_nptype_from_format(d3d11_element.Format)

            

            format_len = int(d3d11_element.ByteWidth / numpy.dtype(np_type).itemsize)

            if d3d11_element_name.startswith("BLENDINDICES") or d3d11_element_name.startswith("BLENDWEIGHT"):
                blend_size = format_len
                
            # XXX 长度为1时必须手动指定为(1,)否则会变成1维数组
            if format_len == 1:
                self.total_structured_dtype = numpy.dtype(self.total_structured_dtype.descr + [(d3d11_element_name, (np_type, (1,)))])
            else:
                self.total_structured_dtype = numpy.dtype(self.total_structured_dtype.descr + [(d3d11_element_name, (np_type, format_len))])


        normalize_weights = "Blend" in self.d3d11_game_type.OrderedCategoryNameList

        # normalize_weights = False

        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            # print("鸣潮专属测试版权重处理：")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=self.mesh,normalize_weights = normalize_weights,blend_size=blend_size)

        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            print("尘白禁区权重处理")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=self.mesh,normalize_weights = normalize_weights,blend_size=blend_size)
        else:
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v3(mesh=self.mesh,normalize_weights = normalize_weights)

        # The per-loop BLENDINDICES values are available in `blendindices_dict`
        # (one entry per semantic index). We intentionally do NOT keep a
        # separate `raw_blendindices` attribute here — the extracted per-
        # element data will be placed into `self.original_elementname_data_dict['BLENDINDICES']`.
        # Note: callers that need to remap BLENDINDICES should operate on
        # `self.final_elementname_data_dict['BLENDINDICES']` after
        # `parse_elementname_data_dict()` and before
        # `fill_into_element_vertex_ndarray()`.


        # 对每一种Element都获取对应的数据
        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            d3d11_element = self.d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]

            if d3d11_element_name == 'POSITION':
                vertex_coords = numpy.empty(mesh_vertices_length * 3, dtype=numpy.float32)
                # Follow WWMI-Tools: fetch the undeformed vertex coordinates and do
                # not apply mirroring or dtype conversion at extraction stage.
                mesh_vertices.foreach_get('co', vertex_coords)
                positions = vertex_coords.reshape(-1, 3)[loop_vertex_indices]


                if d3d11_element.Format == 'R32G32B32A32_FLOAT':
                    # If format expects 4 components, add a zero alpha column (float32)
                    new_array = numpy.zeros((positions.shape[0], 4), dtype=numpy.float32)
                    new_array[:, :3] = positions
                    positions = new_array
                elif d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    # If format expects 4 components, add a W column (float16).
                    # Expand the 3-component positions into the first 3 slots
                    # and set the 4th (W) component to 1.0 (homogeneous coord).
                    new_array = numpy.zeros((positions.shape[0], 4), dtype=numpy.float16)
                    new_array[:, :3] = positions.astype(numpy.float16)
                    new_array[:, 3] = numpy.ones(positions.shape[0], dtype=numpy.float16)
                    positions = new_array

                self.original_elementname_data_dict[d3d11_element_name] = positions

            elif d3d11_element_name == 'NORMAL':
                # 统一获取法线数据
                normals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                mesh_loops.foreach_get('normal', normals)

                if d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    result = result.astype(numpy.float16)
                    self.original_elementname_data_dict[d3d11_element_name] = result

                elif d3d11_element.Format == 'R32G32B32A32_FLOAT':
                    
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    result = result.astype(numpy.float32)
                    self.original_elementname_data_dict[d3d11_element_name] = result

                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # WWMI 这里已经确定过NORMAL没问题

                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    
                    if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
                        bitangent_signs = numpy.empty(mesh_loops_length, dtype=numpy.float32)
                        mesh_loops.foreach_get("bitangent_sign", bitangent_signs)
                        result[3::4] = bitangent_signs * -1
                        # print("Unreal: Set NORMAL.W to bitangent_sign")
                    
                    result = result.reshape(-1, 4)

                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(result)


                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    # 因为法线数据是[-1,1]如果非要导出成UNORM，那一定是进行了归一化到[0,1]
                    
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    

                    # 燕云十六声的最后一位w固定为0
                    if GlobalConfig.logic_name == LogicName.YYSLS:
                        result = numpy.zeros(mesh_loops_length * 4, dtype=numpy.float32)
                        
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    # 归一化 (此处感谢 球球 的代码开发)
                    def DeConvert(nor):
                        return (nor + 1) * 0.5

                    for i in range(len(result)):
                        result[i][0] = DeConvert(result[i][0])
                        result[i][1] = DeConvert(result[i][1])
                        result[i][2] = DeConvert(result[i][2])

                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)
                
                else:
                    # 将一维数组 reshape 成 (mesh_loops_length, 3) 形状的二维数组
                    result = normals.reshape(-1, 3)

                    self.original_elementname_data_dict[d3d11_element_name] = result


            elif d3d11_element_name == 'TANGENT':

                result = numpy.empty(mesh_loops_length * 4, dtype=numpy.float32)

                # 使用 foreach_get 批量获取切线和副切线符号数据
                tangents = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                mesh_loops.foreach_get("tangent", tangents)

                # 将切线分量放置到输出数组中
                result[0::4] = tangents[0::3]  # x 分量
                result[1::4] = tangents[1::3]  # y 分量
                result[2::4] = tangents[2::3]  # z 分量

                if GlobalConfig.logic_name == LogicName.YYSLS:
                    # 燕云十六声的TANGENT.w固定为1
                    tangent_w = numpy.ones(mesh_loops_length, dtype=numpy.float32)
                    result[3::4] = tangent_w
                elif GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
                    # Unreal引擎中这里要填写固定的1
                    tangent_w = numpy.ones(mesh_loops_length, dtype=numpy.float32)
                    result[3::4] = tangent_w
                else:
                    print("其它游戏翻转TANGENT的W分量")
                    # 默认就设置BITANGENT的W翻转，大部分Unity游戏都要用到
                    bitangent_signs = numpy.empty(mesh_loops_length, dtype=numpy.float32)
                    mesh_loops.foreach_get("bitangent_sign", bitangent_signs)
                    # XXX 将副切线符号乘以 -1
                    # 这里翻转（翻转指的就是 *= -1）是因为如果要确保Unity游戏中渲染正确，必须翻转TANGENT的W分量
                    bitangent_signs *= -1
                    result[3::4] = bitangent_signs  # w 分量 (副切线符号)
                # 重塑 output_tangents 成 (mesh_loops_length, 4) 形状的二维数组
                result = result.reshape(-1, 4)

                if d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    result = result.astype(numpy.float16)

                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # print("WWMI TANGENT To SNORM")
                    result = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(result)

                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    result = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)
                
                # 第五人格格式
                elif d3d11_element.Format == "R32G32B32_FLOAT":
                    result = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)

                    result[0::3] = tangents[0::3]  # x 分量
                    result[1::3] = tangents[1::3]  # y 分量
                    result[2::3] = tangents[2::3]  # z 分量

                    result = result.reshape(-1, 3)

                # 燕云十六声格式
                elif d3d11_element.Format == 'R16G16B16A16_SNORM':
                    result = FormatUtils.convert_4x_float32_to_r16g16b16a16_snorm(result)
                    

                self.original_elementname_data_dict[d3d11_element_name] = result

            #  YYSLS需要BINORMAL导出，前提是先把这些代码差分简化，因为YYSLS的TANGENT和NORMAL的.w都是固定的1
            elif d3d11_element_name.startswith('BINORMAL'):
                result = numpy.empty(mesh_loops_length * 4, dtype=numpy.float32)

                # 使用 foreach_get 批量获取切线和副切线符号数据
                binormals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                mesh_loops.foreach_get("bitangent", binormals)
                
                if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
                    # 鸣潮逆向翻转：Binormal (-x, -y, z)
                    binormals[0::3] *= -1
                    binormals[1::3] *= -1

                # 将切线分量放置到输出数组中
                # BINORMAL全部翻转即可得到和YYSLS游戏中一样的效果。
                result[0::4] = binormals[0::3]  # x 分量
                result[1::4] = binormals[1::3]   # y 分量
                result[2::4] = binormals[2::3]  # z 分量
                binormal_w = numpy.ones(mesh_loops_length, dtype=numpy.float32)
                result[3::4] = binormal_w
                result = result.reshape(-1, 4)

                if d3d11_element.Format == 'R16G16B16A16_SNORM':
                    #  燕云十六声格式
                    result = FormatUtils.convert_4x_float32_to_r16g16b16a16_snorm(result)
                    
                self.original_elementname_data_dict[d3d11_element_name] = result
            elif d3d11_element_name.startswith('COLOR'):
                if d3d11_element_name in self.vertex_colors:
                    # 因为COLOR属性存储在Blender里固定是float32类型所以这里只能用numpy.float32
                    result = numpy.zeros(mesh_loops_length, dtype=(numpy.float32, 4))
                    # result = numpy.zeros((mesh_loops_length,4), dtype=(numpy.float32))

                    self.vertex_colors[d3d11_element_name].data.foreach_get("color", result.ravel())
                    
                    if d3d11_element.Format == 'R16G16B16A16_FLOAT':
                        result = result.astype(numpy.float16)
                    elif d3d11_element.Format == "R16G16_UNORM":
                        # 鸣潮的平滑法线存UV，在WWMI中的处理方式是转为R16G16_UNORM。
                        # 但是这里很可能存在转换问题。
                        result = result.astype(numpy.float16)
                        result = result[:, :2]
                        result = FormatUtils.convert_2x_float32_to_r16g16_unorm(result)
                    elif d3d11_element.Format == "R16G16_FLOAT":
                        # 
                        result = result[:, :2]
                    elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                        result = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)

                    print(d3d11_element.Format)
                    print(d3d11_element_name)
           
                    self.original_elementname_data_dict[d3d11_element_name] = result

            elif d3d11_element_name.startswith('TEXCOORD') and d3d11_element.Format.endswith('FLOAT'):
                # TimerUtils.Start("GET TEXCOORD")
                for uv_name in ('%s.xy' % d3d11_element_name, '%s.zw' % d3d11_element_name):
                    if uv_name in self.uv_layers:
                        uvs_array = numpy.empty(mesh_loops_length ,dtype=(numpy.float32,2))
                        self.uv_layers[uv_name].data.foreach_get("uv",uvs_array.ravel())
                        uvs_array[:,1] = 1.0 - uvs_array[:,1]

                        if d3d11_element.Format == 'R16G16_FLOAT':
                            uvs_array = uvs_array.astype(numpy.float16)
                        
                        # 重塑 uvs_array 成 (mesh_loops_length, 2) 形状的二维数组
                        # uvs_array = uvs_array.reshape(-1, 2)

                        self.original_elementname_data_dict[d3d11_element_name] = uvs_array 
                # TimerUtils.End("GET TEXCOORD")
            
                        
            elif d3d11_element_name.startswith('BLENDINDICES'):
                blendindices = blendindices_dict.get(d3d11_element.SemanticIndex,None)
                # print("blendindices: " + str(len(blendindices_dict)))
                # 如果当前索引对应的 blendindices 为 None，则使用索引0的数据并全部置0
                if blendindices is None:
                    blendindices_0 = blendindices_dict.get(0, None)
                    if blendindices_0 is not None:
                        # 创建一个与 blendindices_0 形状相同的全0数组，保持相同的数据类型
                        blendindices = numpy.zeros_like(blendindices_0)
                    else:
                        raise Fatal("Cannot find any valid BLENDINDICES data in this model, Please check if your model's Vertex Group is correct.")
                # print(len(blendindices))
                if d3d11_element.Format == "R32G32B32A32_SINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R16G16B16A16_UINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32B32A32_UINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32_UINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32G32_SINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32_UINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == "R32_SINT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendindices)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(blendindices)
                elif d3d11_element.Format == 'R8G8B8A8_UINT':
                    # TODO 这里类型截断错了吧，假如我们的全局顶点组索引是256或者300呢？
                    # 这里截断直接没了，后续我们还怎么去和remap里进行映射？
                    # 帮我在这里新加一个判断，如果blendindices里有大于255的值就不能转换为uint8
                    # print("uint8")
                    max_index = numpy.max(blendindices)
                    if max_index > 255:
                        print("BLENDINDICES大于255了,最大值是：" + str(max_index))
                    else:
                        blendindices.astype(numpy.uint8)
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                    # print(self.original_elementname_data_dict[d3d11_element_name].dtype)
                elif d3d11_element.Format == "R8_UINT" and d3d11_element.ByteWidth == 8:
                    max_index = numpy.max(blendindices)
                    if max_index > 255:
                        print("BLENDINDICES大于255了,最大值是：" + str(max_index))
                    else:
                        blendindices.astype(numpy.uint8)

                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                    # print(self.original_elementname_data_dict[d3d11_element_name].dtype)
                    # print("WWMI R8_UINT特殊处理")
                elif d3d11_element.Format == "R16_UINT" and d3d11_element.ByteWidth == 16:
                    blendindices.astype(numpy.uint16)
                    self.original_elementname_data_dict[d3d11_element_name] = blendindices
                    # print("WWMI R16_UINT特殊处理")
                else:
                    # print(blendindices.shape)
                    raise Fatal("未知的BLENDINDICES格式")
                
            elif d3d11_element_name.startswith('BLENDWEIGHT'):
                blendweights = blendweights_dict.get(d3d11_element.SemanticIndex, None)
                if blendweights is None:
                    # print("遇到了为None的情况！")
                    blendweights_0 = blendweights_dict.get(0, None)
                    if blendweights_0 is not None:
                        # 创建一个与 blendweights_0 形状相同的全0数组，保持相同的数据类型
                        blendweights = numpy.zeros_like(blendweights_0)
                    else:
                        raise Fatal("Cannot find any valid BLENDWEIGHT data in this model, Please check if your model's Vertex Group is correct.")
                # print(len(blendweights))
                if d3d11_element.Format == "R32G32B32A32_FLOAT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendweights
                elif d3d11_element.Format == "R32G32_FLOAT":
                    self.original_elementname_data_dict[d3d11_element_name] = blendweights[:, :2]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # print("BLENDWEIGHT R8G8B8A8_SNORM")
                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendweights)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    # print("BLENDWEIGHT R8G8B8A8_UNORM")
                    self.original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                elif d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    self.original_elementname_data_dict[d3d11_element_name] = blendweights.astype(numpy.float16)
                elif d3d11_element.Format == "R8_UNORM" and d3d11_element.ByteWidth == 8:
                    # TimerUtils.Start("WWMI BLENDWEIGHT R8_UNORM特殊处理")
                    blendweights = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                    self.original_elementname_data_dict[d3d11_element_name] = blendweights
                    print("WWMI R8_UNORM特殊处理")
                    # TimerUtils.End("WWMI BLENDWEIGHT R8_UNORM特殊处理")

                else:
                    print(blendweights.shape)
                    raise Fatal("未知的BLENDWEIGHTS格式")



        