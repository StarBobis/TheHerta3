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

from .migoto_format import D3D11GameType,ObjDataModel

@dataclass
class ObjBufferModel:
    # 初始化时必须填的字段
    d3d11_game_type:D3D11GameType
    obj_name:str

    # 其它后来生成的字段
    dtype:numpy.dtype = field(init=False, repr=False)
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    ib:list = field(init=False,repr=False)
    category_buffer_dict:dict = field(init=False,repr=False)
    index_vertex_id_dict:dict = field(init=False,repr=False) # 仅用于WWMI的索引顶点ID字典，key是顶点索引，value是顶点ID，默认可以为None

    obj:bpy.types.Object = field(init=False,repr=False)
    mesh:bpy.types.Mesh = field(init=False,repr=False)

    def __post_init__(self) -> None:
        '''
        使用Numpy直接从指定名称的obj的mesh中转换数据到目标格式Buffer

        TODO 目前这个函数分别在BranchModel和DrawIBModelWWMI中被调用，
        这是因为我们对indexid_vertexid_dict的组合还没有搞清楚导致的
        实际上全部都应该在BranchModel中进行调用。

        TODO 且获取indexid_vertexid_dict很明显导致导出速度变慢，算法仍然有问题
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
    
        # 读取并解析数据
        self.parse_elementname_ravel_ndarray_dict()

        # 因为只有存在TANGENT时，顶点数才会增加，所以如果是GF2并且存在TANGENT才使用共享TANGENT防止增加顶点数
        if GlobalConfig.logic_name == LogicName.UnityCPU and "TANGENT" in self.d3d11_game_type.OrderedFullElementList:
            self.calc_index_vertex_buffer_girlsfrontline2()
        elif GlobalConfig.logic_name == LogicName.WWMI:
            print("calc_index_vertex_buffer_wwmi::")
            self.calc_index_vertex_buffer_wwmi_v2()
        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            self.calc_index_vertex_buffer_wwmi()
        else:
            # 计算IndexBuffer和CategoryBufferDict
            self.calc_index_vertex_buffer_universal()
        
        # TODO 鸣潮普通模型总耗时4.7秒，但是WWMITools 0.2秒就搞定了，说明我们的代码还是存在认知上的问题。
        # 必须继续优化直到持平为止
        # TODO 比如每个方法里都频繁的获取mesh的各种数据，每个地方都获取都有开销，为什么不能在一个地方统一获取，然后后面都使用呢

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

    def parse_elementname_ravel_ndarray_dict(self) -> dict:
        '''
        - 注意这里是从mesh.loops中获取数据，而不是从mesh.vertices中获取数据
        - 所以后续使用的时候要用mesh.loop里的索引来进行获取数据
        '''

        mesh_loops = self.mesh.loops
        mesh_loops_length = len(mesh_loops)
        mesh_vertices = self.mesh.vertices
        mesh_vertices_length = len(self.mesh.vertices)

        loop_vertex_indices = numpy.empty(mesh_loops_length, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)

        self.dtype = numpy.dtype([])

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
                self.dtype = numpy.dtype(self.dtype.descr + [(d3d11_element_name, (np_type, (1,)))])
            else:
                self.dtype = numpy.dtype(self.dtype.descr + [(d3d11_element_name, (np_type, format_len))])
            
            # print("d3d11Element: " + d3d11_element_name + "  Dtype" + str(self.dtype))

        self.element_vertex_ndarray = numpy.zeros(mesh_loops_length,dtype=self.dtype)



        normalize_weights = "Blend" in self.d3d11_game_type.OrderedCategoryNameList

        # normalize_weights = False


        if GlobalConfig.logic_name == LogicName.WWMI:
            print("鸣潮专属测试版权重处理：")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=self.mesh,normalize_weights = normalize_weights,blend_size=blend_size)

        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            print("尘白禁区权重处理")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=self.mesh,normalize_weights = normalize_weights,blend_size=blend_size)
        else:
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v3(mesh=self.mesh,normalize_weights = normalize_weights)


        # 对每一种Element都获取对应的数据
        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            d3d11_element = self.d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]

            if d3d11_element_name == 'POSITION':
                # TimerUtils.Start("Position Get")
                vertex_coords = numpy.empty(mesh_vertices_length * 3, dtype=numpy.float32)
                # Notice: 'undeformed_co' is static, don't need dynamic calculate like 'co' so it is faster.
                # mesh_vertices.foreach_get('undeformed_co', vertex_coords)
                mesh_vertices.foreach_get('co', vertex_coords)
                
                positions = vertex_coords.reshape(-1, 3)[loop_vertex_indices]
                # print("Position Length: " + str(len(positions)))
                
                # XXX 翻转X轴，Blender的X轴是左手系，D3D11是右手系
                # 这一步是为了解决导入的模型是镜像的问题
                if Properties_ImportModel.use_mirror_workflow():
                    positions[:, 0] *= -1 

                if d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    positions = positions.astype(numpy.float16)
                    new_array = numpy.zeros((positions.shape[0], 4))
                    new_array[:, :3] = positions
                    positions = new_array
                if d3d11_element.Format == 'R32G32B32A32_FLOAT':
                    positions = positions.astype(numpy.float32)
                    new_array = numpy.zeros((positions.shape[0], 4))
                    new_array[:, :3] = positions
                    positions = new_array
                
                self.element_vertex_ndarray[d3d11_element_name] = positions
                # TimerUtils.End("Position Get") # 0:00:00.057535 

            elif d3d11_element_name == 'NORMAL':
                if d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    normals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                    mesh_loops.foreach_get('normal', normals)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    result = result.astype(numpy.float16)
                    self.element_vertex_ndarray[d3d11_element_name] = result
                elif d3d11_element.Format == 'R32G32B32A32_FLOAT':
                    
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    normals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                    mesh_loops.foreach_get('normal', normals)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    result = result.astype(numpy.float32)
                    self.element_vertex_ndarray[d3d11_element_name] = result
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # WWMI 这里已经确定过NORMAL没问题

                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    normals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                    mesh_loops.foreach_get('normal', normals)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    

                    if GlobalConfig.logic_name == LogicName.WWMI:
                        bitangent_signs = numpy.empty(mesh_loops_length, dtype=numpy.float32)
                        mesh_loops.foreach_get("bitangent_sign", bitangent_signs)
                        result[3::4] = bitangent_signs * -1
                        # print("Unreal: Set NORMAL.W to bitangent_sign")
                    
                    result = result.reshape(-1, 4)

                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(result)


                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    # 因为法线数据是[-1,1]如果非要导出成UNORM，那一定是进行了归一化到[0,1]
                    
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    

                    # 燕云十六声的最后一位w固定为0
                    if GlobalConfig.logic_name == LogicName.YYSLS:
                        result = numpy.zeros(mesh_loops_length * 4, dtype=numpy.float32)
                        
                    normals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                    mesh_loops.foreach_get('normal', normals)
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

                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)
                
                else:
                    result = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                    mesh_loops.foreach_get('normal', result)
                    # 将一维数组 reshape 成 (mesh_loops_length, 3) 形状的二维数组
                    result = result.reshape(-1, 3)
                    self.element_vertex_ndarray[d3d11_element_name] = result


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
                elif GlobalConfig.logic_name == LogicName.WWMI:
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
                    

                self.element_vertex_ndarray[d3d11_element_name] = result

            #  YYSLS需要BINORMAL导出，前提是先把这些代码差分简化，因为YYSLS的TANGENT和NORMAL的.w都是固定的1
            elif d3d11_element_name.startswith('BINORMAL'):
                result = numpy.empty(mesh_loops_length * 4, dtype=numpy.float32)

                # 使用 foreach_get 批量获取切线和副切线符号数据
                binormals = numpy.empty(mesh_loops_length * 3, dtype=numpy.float32)
                mesh_loops.foreach_get("bitangent", binormals)
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
                    
                self.element_vertex_ndarray[d3d11_element_name] = result
            elif d3d11_element_name.startswith('COLOR'):
                if d3d11_element_name in self.mesh.vertex_colors:
                    # 因为COLOR属性存储在Blender里固定是float32类型所以这里只能用numpy.float32
                    result = numpy.zeros(mesh_loops_length, dtype=(numpy.float32, 4))
                    # result = numpy.zeros((mesh_loops_length,4), dtype=(numpy.float32))

                    self.mesh.vertex_colors[d3d11_element_name].data.foreach_get("color", result.ravel())
                    
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
                    # print(result.shape)
                    # print(self.element_vertex_ndarray[d3d11_element_name].shape)
                    self.element_vertex_ndarray[d3d11_element_name] = result

            elif d3d11_element_name.startswith('TEXCOORD') and d3d11_element.Format.endswith('FLOAT'):
                # TimerUtils.Start("GET TEXCOORD")
                for uv_name in ('%s.xy' % d3d11_element_name, '%s.zw' % d3d11_element_name):
                    if uv_name in self.mesh.uv_layers:
                        uvs_array = numpy.empty(mesh_loops_length ,dtype=(numpy.float32,2))
                        self.mesh.uv_layers[uv_name].data.foreach_get("uv",uvs_array.ravel())
                        uvs_array[:,1] = 1.0 - uvs_array[:,1]

                        if d3d11_element.Format == 'R16G16_FLOAT':
                            uvs_array = uvs_array.astype(numpy.float16)
                        
                        # 重塑 uvs_array 成 (mesh_loops_length, 2) 形状的二维数组
                        # uvs_array = uvs_array.reshape(-1, 2)

                        self.element_vertex_ndarray[d3d11_element_name] = uvs_array 
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
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R16G16B16A16_UINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32B32A32_UINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32_UINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32G32_SINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32_UINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == "R32_SINT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendindices)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(blendindices)
                elif d3d11_element.Format == 'R8G8B8A8_UINT':
                    # print("uint8")
                    blendindices.astype(numpy.uint8)
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R8_UINT" and d3d11_element.ByteWidth == 8:
                    blendindices.astype(numpy.uint8)
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                    print("WWMI R8_UINT特殊处理")
                elif d3d11_element.Format == "R16_UINT" and d3d11_element.ByteWidth == 16:
                    blendindices.astype(numpy.uint16)
                    self.element_vertex_ndarray[d3d11_element_name] = blendindices
                    print("WWMI R16_UINT特殊处理")
                else:
                    print(blendindices.shape)
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
                    self.element_vertex_ndarray[d3d11_element_name] = blendweights
                elif d3d11_element.Format == "R32G32_FLOAT":
                    self.element_vertex_ndarray[d3d11_element_name] = blendweights[:, :2]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # print("BLENDWEIGHT R8G8B8A8_SNORM")
                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendweights)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    # print("BLENDWEIGHT R8G8B8A8_UNORM")
                    self.element_vertex_ndarray[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                elif d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    self.element_vertex_ndarray[d3d11_element_name] = blendweights.astype(numpy.float16)
                elif d3d11_element.Format == "R8_UNORM" and d3d11_element.ByteWidth == 8:
                    blendweights = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                    self.element_vertex_ndarray[d3d11_element_name] = blendweights
                    print("WWMI R8_UNORM特殊处理")
                else:
                    print(blendweights.shape)
                    raise Fatal("未知的BLENDWEIGHTS格式")
    def calc_index_vertex_buffer_girlsfrontline2(self):
        '''
        1. Blender 的“顶点数”= mesh.vertices 长度，只要位置不同就算一个。
        2. 我们预分配同样长度的盒子列表，盒子下标 == 顶点下标，保证一一对应。
        3. 遍历 loop 时，把真实数据写进对应盒子；没人引用的盒子留 dummy（坐标填对，其余 0）。
        4. 最后按盒子顺序打包成字节数组，长度必然与 mesh.vertices 相同，导出数就能和 Blender 状态栏完全一致。
        '''
        print("calc ivb gf2")

        loops = self.mesh.loops
        v_cnt = len(self.mesh.vertices)
        loop_vidx = numpy.empty(len(loops), dtype=int)
        loops.foreach_get("vertex_index", loop_vidx)

        # 1. 预分配：每条 Blender 顶点一条记录，先填“空”
        dummy = numpy.zeros(1, dtype=self.element_vertex_ndarray.dtype)
        vertex_buffer = [dummy.copy() for _ in range(v_cnt)]   # list[ndarray]
        # 2. 标记哪些顶点被 loop 真正用到
        used_mask = numpy.zeros(v_cnt, dtype=bool)
        used_mask[loop_vidx] = True

        # 3. 共享 TANGENT 字典
        pos_normal_key = {}   # (position_tuple, normal_tuple) -> tangent

        # 4. 先给“被用到”的顶点填真实数据
        for lp in loops:
            v_idx = lp.vertex_index
            if used_mask[v_idx]:          # 其实恒为 True，留着可读性
                data = self.element_vertex_ndarray[lp.index].copy()
                pn_key = (tuple(data['POSITION']), tuple(data['NORMAL']))
                if pn_key in pos_normal_key:
                    data['TANGENT'] = pos_normal_key[pn_key]
                else:
                    pos_normal_key[pn_key] = data['TANGENT']
                vertex_buffer[v_idx] = data

        # 5. 给“死顶点”也填上 dummy，但位置必须对
        for v_idx in range(v_cnt):
            if not used_mask[v_idx]:
                vertex_buffer[v_idx]['POSITION'] = self.mesh.vertices[v_idx].co
                # 其余字段保持 0

        # 6. 现在 vertex_buffer 长度 == v_cnt，直接转 bytes 即可
        indexed_vertices = [arr.tobytes() for arr in vertex_buffer]

        # 7. 重建索引缓冲（IB）
        ib = []
        for poly in self.mesh.polygons:
            ib.append([v_idx for lp in loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    for v_idx in [lp.vertex_index]])

        flattened_ib = [i for sub in ib for i in sub]

        # 8. 拆 CategoryBuffer
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {name: [] for name in self.d3d11_game_type.CategoryStrideDict}
        data_matrix = numpy.array([numpy.frombuffer(b, dtype=numpy.uint8) for b in indexed_vertices])
        stride_offset = 0
        for name, stride in category_stride_dict.items():
            category_buffer_dict[name] = data_matrix[:, stride_offset:stride_offset + stride].flatten()
            stride_offset += stride

        print("长度：", v_cnt)          # 这里一定是 21668
        self.ib = flattened_ib
        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = None
 

    def calc_index_vertex_buffer_wwmi_v2(self):
        '''
        优点：
        - 用 numpy 将结构化顶点视图为一行字节，避免逐顶点 bytes() 与 dict 哈希。
        - 使用 numpy.unique(..., axis=0, return_index=True, return_inverse=True) 在 C 层完成唯一化与逆映射。
        - 仅在构建 per-polygon IB 时使用少量 Python 切片，整体效率大幅提高。

        注意：
        - 当 structured dtype 非连续时，内部会做一次拷贝（ascontiguousarray）；通常开销小于逐顶点哈希开销。
        - 若模型非常大且内存受限，可改为分块实现（我可以后续提供）。
        '''
        import numpy as np

        # (1) loop -> vertex mapping
        loops = self.mesh.loops
        n_loops = len(loops)
        loop_vertex_indices = np.empty(n_loops, dtype=int)
        loops.foreach_get("vertex_index", loop_vertex_indices)

        # (2) 将 element_vertex_ndarray 保证为连续，并视为 (n_loops, row_bytes) uint8 矩阵
        vb = np.ascontiguousarray(self.element_vertex_ndarray)
        row_size = vb.dtype.itemsize
        try:
            row_bytes = vb.view(np.uint8).reshape(n_loops, row_size)
        except Exception:
            raw = vb.tobytes()
            row_bytes = np.frombuffer(raw, dtype=np.uint8).reshape(n_loops, row_size)

        # (3) unique + inverse 映射
        unique_rows, unique_first_indices, inverse = np.unique(
            row_bytes, axis=0, return_index=True, return_inverse=True
        )

        # 构建 index -> original vertex id（使用每个 unique 行的第一个 loop 对应的 vertex）
        index_vertex_id_dict = {
            int(uid): int(loop_vertex_indices[int(pos)])
            for uid, pos in enumerate(unique_first_indices)
        }

        # (4) 为每个 polygon 构建 IB（使用 inverse 映射）
        ib_lists = []
        for poly in self.mesh.polygons:
            s = poly.loop_start
            t = poly.loop_total
            ib_lists.append(inverse[s:s + t].tolist())

        flattened_ib = [int(x) for sub in ib_lists for x in sub]

        # (5) 按 category 从 unique_rows 切分 bytes 序列
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {}
        stride_offset = 0
        for cname, cstride in category_stride_dict.items():
            category_buffer_dict[cname] = unique_rows[:, stride_offset:stride_offset + cstride].flatten()
            stride_offset += cstride

        # (6) 翻转三角形方向（高效）
        flat_arr = np.array(flattened_ib, dtype=int)
        if flat_arr.size % 3 == 0:
            flipped = flat_arr.reshape(-1, 3)[:, ::-1].flatten().tolist()
        else:
            flipped = []
            for i in range(0, len(flattened_ib), 3):
                tri = flattened_ib[i:i + 3]
                flipped.extend(tri[::-1])

        # (7) 写回到 self（与原函数一致的字段）
        self.ib = flipped
        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = index_vertex_id_dict

    def calc_index_vertex_buffer_wwmi(self):
        '''
        计算IndexBuffer和CategoryBufferDict并返回

        这里是速度瓶颈，23万顶点情况下测试，前面的获取mesh数据只用了1.5秒
        但是这里两个步骤加起来用了6秒，占了4/5运行时间。
        不过暂时也够用了，先不管了。
        '''
        TimerUtils.Start("Calc IB VB") # TODO 这里消耗了所有的时间，必须严查
        # (1) 统计模型的索引和唯一顶点

        # 创建一个空列表用于存储最终的结果
        # print("calc ivb wwmi")
        index_vertex_id_dict = {}
        ib = []
        indexed_vertices = collections.OrderedDict()
        # 一个字典确保每个符合条件的position只出现过一次
        # 遍历每个多边形（polygon）
        for poly in self.mesh.polygons:
            # 创建一个临时列表用于存储当前多边形的索引
            vertex_indices = []
            
            # 遍历当前多边形中的每一个环（loop），根据多边形的起始环和环总数
            for blender_lvertex in self.mesh.loops[poly.loop_start:poly.loop_start + poly.loop_total]:
                vertex_data_get = self.element_vertex_ndarray[blender_lvertex.index].copy()
                vertex_data = vertex_data_get.tobytes()
                index = indexed_vertices.setdefault(vertex_data, len(indexed_vertices))
                vertex_indices.append(index)
                index_vertex_id_dict[index] = blender_lvertex.vertex_index
            
            # 将当前多边形的顶点索引列表添加到最终结果列表中
            ib.append(vertex_indices)

        # print("长度：")
        # print(len(position_normal_sharedtangent_dict))
            
        flattened_ib = [item for sublist in ib for item in sublist]
        TimerUtils.End("Calc IB VB")

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer") # 几乎不消耗时间
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in self.d3d11_game_type.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride

        # TimerUtils.End("Calc CategoryBuffer")
        print("导出时翻转面朝向")
        flipped_indices = []
        # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
        for i in range(0, len(flattened_ib), 3):
            triangle = flattened_ib[i:i+3]
            flipped_triangle = triangle[::-1]
            flipped_indices.extend(flipped_triangle)
        # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])

        self.ib = flipped_indices

        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = index_vertex_id_dict

    def calc_index_vertex_buffer_universal(self):
        '''
        计算IndexBuffer和CategoryBufferDict并返回

        这里是速度瓶颈，23万顶点情况下测试，前面的获取mesh数据只用了1.5秒
        但是这里两个步骤加起来用了6秒，占了4/5运行时间。
        不过暂时也够用了，先不管了。
        '''
        # TimerUtils.Start("Calc IB VB")
        # (1) 统计模型的索引和唯一顶点
        '''
        不保持相同顶点时，仍然使用经典而又快速的方法
        '''
        # print("calc ivb universal")
        indexed_vertices = collections.OrderedDict()
        ib = [[indexed_vertices.setdefault(self.element_vertex_ndarray[blender_lvertex.index].tobytes(), len(indexed_vertices))
                for blender_lvertex in self.mesh.loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    ]for poly in self.mesh.polygons] 
            
        flattened_ib = [item for sublist in ib for item in sublist]
        # TimerUtils.End("Calc IB VB")

        # 重计算TANGENT步骤
        indexed_vertices = self.average_normal_tangent(obj=self.obj, indexed_vertices=indexed_vertices, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)
        
        # 重计算COLOR步骤
        indexed_vertices = self.average_normal_color(obj=self.obj, indexed_vertices=indexed_vertices, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)

        # print("indexed_vertices:")
        # print(str(len(indexed_vertices)))

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer")
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in self.d3d11_game_type.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride


        

        self.ib = flattened_ib

        flip_face_direction = False

        if Properties_ImportModel.use_mirror_workflow():
            flip_face_direction = True
            if GlobalConfig.logic_name == LogicName.YYSLS:
                flip_face_direction = False
        else:
            if GlobalConfig.logic_name == LogicName.YYSLS:
                flip_face_direction = True

        if flip_face_direction:
            print("导出时翻转面朝向")

            flipped_indices = []
            # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
            for i in range(0, len(flattened_ib), 3):
                triangle = flattened_ib[i:i+3]
                flipped_triangle = triangle[::-1]
                flipped_indices.extend(flipped_triangle)
            # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])
            self.ib = flipped_indices



        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = None


    def average_normal_tangent(self,obj,indexed_vertices,d3d11GameType,dtype):
        '''
        Nico: 米游所有游戏都能用到这个，还有曾经的GPU-PreSkinning的GF2也会用到这个，崩坏三2.0新角色除外。
        尽管这个可以起到相似的效果，但是仍然无法完美获取模型本身的TANGENT数据，只能做到身体轮廓线99%近似。
        经过测试，头发轮廓线部分并不是简单的向量归一化，也不是算术平均归一化。
        '''
        # TimerUtils.Start("Recalculate TANGENT")

        if "TANGENT" not in d3d11GameType.OrderedFullElementList:
            return indexed_vertices
        allow_calc = False
        if Properties_GenerateMod.recalculate_tangent():
            allow_calc = True
        elif obj.get("3DMigoto:RecalculateTANGENT",False): 
            allow_calc = True
        
        if not allow_calc:
            return indexed_vertices
        
        # 不用担心这个转换的效率，速度非常快
        vb = bytearray()
        for vertex in indexed_vertices:
            vb += bytes(vertex)
        vb = numpy.frombuffer(vb, dtype = dtype)

        # 开始重计算TANGENT
        positions = numpy.array([val['POSITION'] for val in vb])
        normals = numpy.array([val['NORMAL'] for val in vb], dtype=float)

        # 对位置进行排序，以便相同的位置会相邻
        sort_indices = numpy.lexsort(positions.T)
        sorted_positions = positions[sort_indices]
        sorted_normals = normals[sort_indices]

        # 找出位置变化的地方，即我们需要分组的地方
        group_indices = numpy.flatnonzero(numpy.any(sorted_positions[:-1] != sorted_positions[1:], axis=1))
        group_indices = numpy.r_[0, group_indices + 1, len(sorted_positions)]

        # 累加法线和计算计数
        unique_positions = sorted_positions[group_indices[:-1]]
        accumulated_normals = numpy.add.reduceat(sorted_normals, group_indices[:-1], axis=0)
        counts = numpy.diff(group_indices)

        # 归一化累积法线向量
        normalized_normals = accumulated_normals / numpy.linalg.norm(accumulated_normals, axis=1)[:, numpy.newaxis]
        normalized_normals[numpy.isnan(normalized_normals)] = 0  # 处理任何可能出现的零向量导致的除零错误

        # 构建结果字典
        position_normal_dict = dict(zip(map(tuple, unique_positions), normalized_normals))

        # TimerUtils.End("Recalculate TANGENT")

        # 获取所有位置并转换为元组，用于查找字典
        positions = [tuple(pos) for pos in vb['POSITION']]

        # 从字典中获取对应的标准化法线
        normalized_normals = numpy.array([position_normal_dict[pos] for pos in positions])

        # 计算 w 并调整 tangent 的第四个分量
        w = numpy.where(vb['TANGENT'][:, 3] >= 0, -1.0, 1.0)

        # 更新 TANGENT 分量，注意这里的切片操作假设 TANGENT 有四个分量
        vb['TANGENT'][:, :3] = normalized_normals
        vb['TANGENT'][:, 3] = w

        # TimerUtils.End("Recalculate TANGENT")

        return vb


    def average_normal_color(self,obj,indexed_vertices,d3d11GameType,dtype):
        '''
        Nico: 算数平均归一化法线，HI3 2.0角色使用的方法
        '''
        if "COLOR" not in d3d11GameType.OrderedFullElementList:
            return indexed_vertices
        allow_calc = False
        if Properties_GenerateMod.recalculate_color():
            allow_calc = True
        elif obj.get("3DMigoto:RecalculateCOLOR",False): 
            allow_calc = True
        if not allow_calc:
            return indexed_vertices

        # 开始重计算COLOR
        TimerUtils.Start("Recalculate COLOR")

        # 不用担心这个转换的效率，速度非常快
        vb = bytearray()
        for vertex in indexed_vertices:
            vb += bytes(vertex)
        vb = numpy.frombuffer(vb, dtype = dtype)

        # 首先提取所有唯一的位置，并创建一个索引映射
        unique_positions, position_indices = numpy.unique(
            [tuple(val['POSITION']) for val in vb], 
            return_inverse=True, 
            axis=0
        )

        # 初始化累积法线和计数器为零
        accumulated_normals = numpy.zeros((len(unique_positions), 3), dtype=float)
        counts = numpy.zeros(len(unique_positions), dtype=int)

        # 累加法线并增加计数（这里假设vb是一个list）
        for i, val in enumerate(vb):
            accumulated_normals[position_indices[i]] += numpy.array(val['NORMAL'], dtype=float)
            counts[position_indices[i]] += 1

        # 对所有位置的法线进行一次性规范化处理
        mask = counts > 0
        average_normals = numpy.zeros_like(accumulated_normals)
        average_normals[mask] = (accumulated_normals[mask] / counts[mask][:, None])

        # 归一化到[0,1]，然后映射到颜色值
        normalized_normals = ((average_normals + 1) / 2 * 255).astype(numpy.uint8)

        # 更新颜色信息
        new_color = []
        for i, val in enumerate(vb):
            color = [0, 0, 0, val['COLOR'][3]]  # 保留原来的Alpha通道
            
            if mask[position_indices[i]]:
                color[:3] = normalized_normals[position_indices[i]]

            new_color.append(color)

        # 将新的颜色列表转换为NumPy数组
        new_color_array = numpy.array(new_color, dtype=numpy.uint8)

        # 更新vb中的颜色信息
        for i, val in enumerate(vb):
            val['COLOR'] = new_color_array[i]

        TimerUtils.End("Recalculate COLOR")
        return vb

        