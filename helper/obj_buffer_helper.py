from ..base.d3d11_gametype import D3D11GameType
from ..base.fatal import Fatal

from ..utils.format_utils import FormatUtils
from ..utils.vertexgroup_utils import VertexGroupUtils

from ..config.main_config import GlobalConfig, LogicName


import bpy
import numpy

class ObjBufferHelper:
    '''
    工具类，由于使用了抽象数据类型
    所以归为Helper类中
    '''

    @classmethod
    def check_and_verify_attributes(cls, obj:bpy.types.Object, d3d11_game_type:D3D11GameType):
        '''
        校验并补全部分元素
        COLOR
        TEXCOORD、TEXCOORD1、TEXCOORD2、TEXCOORD3
        '''
        for d3d11_element_name in d3d11_game_type.OrderedFullElementList:
            d3d11_element = d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]
            # 校验并补全所有COLOR的存在
            if d3d11_element_name.startswith("COLOR"):
                if d3d11_element_name not in obj.data.vertex_colors:
                    obj.data.vertex_colors.new(name=d3d11_element_name)
                    print("当前obj ["+ obj.name +"] 缺少游戏渲染所需的COLOR: ["+  "COLOR" + "]，已自动补全")
            
            # 校验TEXCOORD是否存在
            if d3d11_element_name.startswith("TEXCOORD"):
                if d3d11_element_name + ".xy" not in obj.data.uv_layers:
                    # 此时如果只有一个UV，则自动改名为TEXCOORD.xy
                    if len(obj.data.uv_layers) == 1 and d3d11_element_name == "TEXCOORD":
                            obj.data.uv_layers[0].name = d3d11_element_name + ".xy"
                    else:
                        # 否则就自动补一个UV，防止后续calc_tangents失败
                        obj.data.uv_layers.new(name=d3d11_element_name + ".xy")
            
            # Check if BLENDINDICES exists
            if d3d11_element_name.startswith("BLENDINDICES"):
                if not obj.vertex_groups:
                    raise Fatal("your object [" +obj.name + "] need at leat one valid Vertex Group, Please check if your model's Vertex Group is correct.")



    @classmethod
    def parse_elementname_data_dict(cls,mesh:bpy.types.Mesh, d3d11_game_type:D3D11GameType):
        '''
        - 注意这里是从mesh.loops中获取数据，而不是从mesh.vertices中获取数据
        - 所以后续使用的时候要用mesh.loop里的索引来进行获取数据
        '''

        original_elementname_data_dict: dict = {}

        mesh_loops = mesh.loops
        mesh_loops_length = len(mesh.loops)
        mesh_vertices = mesh.vertices
        mesh_vertices_length = len(mesh.vertices)

        loop_vertex_indices = numpy.empty(mesh_loops_length, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)

        # 预设的权重个数，也就是每个顶点组受多少个权重影响
        blend_size = 4

        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            blend_size = d3d11_game_type.get_blendindices_count_wwmi()

        normalize_weights = "Blend" in d3d11_game_type.OrderedCategoryNameList

        # normalize_weights = False
        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            # print("鸣潮专属测试版权重处理：")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=mesh,normalize_weights = normalize_weights,blend_size=blend_size)

        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            print("尘白禁区权重处理")
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v4_fast(mesh=mesh,normalize_weights = normalize_weights,blend_size=blend_size)
        else:
            blendweights_dict, blendindices_dict = VertexGroupUtils.get_blendweights_blendindices_v3(mesh=mesh,normalize_weights = normalize_weights)

        # The per-loop BLENDINDICES values are available in `blendindices_dict`
        # (one entry per semantic index). We intentionally do NOT keep a
        # separate `raw_blendindices` attribute here — the extracted per-
        # element data will be placed into `original_elementname_data_dict['BLENDINDICES']`.
        # Note: callers that need to remap BLENDINDICES should operate on
        # `self.final_elementname_data_dict['BLENDINDICES']` after
        # `parse_elementname_data_dict()` and before
        # `fill_into_element_vertex_ndarray()`.


        # 对每一种Element都获取对应的数据
        for d3d11_element_name in d3d11_game_type.OrderedFullElementList:
            d3d11_element = d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]

            if d3d11_element_name == 'POSITION':
                vertex_coords = numpy.empty(mesh_vertices_length * 3, dtype=numpy.float32)
                # Follow WWMI-Tools: fetch the undeformed vertex coordinates and do
                # not apply mirroring or dtype conversion at extraction stage.

                # mesh_vertices.foreach_get('undeformed_co', vertex_coords)
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

                original_elementname_data_dict[d3d11_element_name] = positions

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
                    original_elementname_data_dict[d3d11_element_name] = result

                elif d3d11_element.Format == 'R32G32B32A32_FLOAT':
                    
                    result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
                    result[0::4] = normals[0::3]
                    result[1::4] = normals[1::3]
                    result[2::4] = normals[2::3]
                    result = result.reshape(-1, 4)

                    result = result.astype(numpy.float32)
                    original_elementname_data_dict[d3d11_element_name] = result

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

                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(result)


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

                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)
                
                else:
                    # 将一维数组 reshape 成 (mesh_loops_length, 3) 形状的二维数组
                    result = normals.reshape(-1, 3)

                    original_elementname_data_dict[d3d11_element_name] = result


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
                    

                original_elementname_data_dict[d3d11_element_name] = result

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
                    
                original_elementname_data_dict[d3d11_element_name] = result
            elif d3d11_element_name.startswith('COLOR'):
                if d3d11_element_name in mesh.vertex_colors:
                    # 因为COLOR属性存储在Blender里固定是float32类型所以这里只能用numpy.float32
                    result = numpy.zeros(mesh_loops_length, dtype=(numpy.float32, 4))
                    # result = numpy.zeros((mesh_loops_length,4), dtype=(numpy.float32))

                    mesh.vertex_colors[d3d11_element_name].data.foreach_get("color", result.ravel())
                    
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
           
                    original_elementname_data_dict[d3d11_element_name] = result

            elif d3d11_element_name.startswith('TEXCOORD') and d3d11_element.Format.endswith('FLOAT'):
                # TimerUtils.Start("GET TEXCOORD")
                for uv_name in ('%s.xy' % d3d11_element_name, '%s.zw' % d3d11_element_name):
                    if uv_name in mesh.uv_layers:
                        uvs_array = numpy.empty(mesh_loops_length ,dtype=(numpy.float32,2))
                        mesh.uv_layers[uv_name].data.foreach_get("uv",uvs_array.ravel())
                        uvs_array[:,1] = 1.0 - uvs_array[:,1]

                        if d3d11_element.Format == 'R16G16_FLOAT':
                            uvs_array = uvs_array.astype(numpy.float16)
                        
                        # 重塑 uvs_array 成 (mesh_loops_length, 2) 形状的二维数组
                        # uvs_array = uvs_array.reshape(-1, 2)

                        original_elementname_data_dict[d3d11_element_name] = uvs_array 
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
                    original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R16G16B16A16_UINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32B32A32_UINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices
                elif d3d11_element.Format == "R32G32_UINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32G32_SINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices[:, :2]
                elif d3d11_element.Format == "R32_UINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == "R32_SINT":
                    original_elementname_data_dict[d3d11_element_name] = blendindices[:, :1]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendindices)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(blendindices)
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
                    original_elementname_data_dict[d3d11_element_name] = blendindices
                    # print(original_elementname_data_dict[d3d11_element_name].dtype)
                elif d3d11_element.Format == "R8_UINT" and d3d11_element.ByteWidth == 8:
                    max_index = numpy.max(blendindices)
                    if max_index > 255:
                        print("BLENDINDICES大于255了,最大值是：" + str(max_index))
                    else:
                        blendindices.astype(numpy.uint8)

                    original_elementname_data_dict[d3d11_element_name] = blendindices
                    # print(original_elementname_data_dict[d3d11_element_name].dtype)
                    # print("WWMI R8_UINT特殊处理")
                elif d3d11_element.Format == "R16_UINT" and d3d11_element.ByteWidth == 16:
                    blendindices.astype(numpy.uint16)
                    original_elementname_data_dict[d3d11_element_name] = blendindices
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
                    original_elementname_data_dict[d3d11_element_name] = blendweights
                elif d3d11_element.Format == "R32G32_FLOAT":
                    original_elementname_data_dict[d3d11_element_name] = blendweights[:, :2]
                elif d3d11_element.Format == 'R8G8B8A8_SNORM':
                    # print("BLENDWEIGHT R8G8B8A8_SNORM")
                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendweights)
                elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                    # print("BLENDWEIGHT R8G8B8A8_UNORM")
                    original_elementname_data_dict[d3d11_element_name] = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                elif d3d11_element.Format == 'R16G16B16A16_FLOAT':
                    original_elementname_data_dict[d3d11_element_name] = blendweights.astype(numpy.float16)
                elif d3d11_element.Format == "R8_UNORM" and d3d11_element.ByteWidth == 8:
                    # TimerUtils.Start("WWMI BLENDWEIGHT R8_UNORM特殊处理")
                    blendweights = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
                    original_elementname_data_dict[d3d11_element_name] = blendweights
                    print("WWMI R8_UNORM特殊处理")
                    # TimerUtils.End("WWMI BLENDWEIGHT R8_UNORM特殊处理")

                else:
                    print(blendweights.shape)
                    raise Fatal("未知的BLENDWEIGHTS格式")

        return original_elementname_data_dict


    @classmethod
    def convert_to_element_vertex_ndarray(
        cls,
        d3d11_game_type:D3D11GameType, 
        mesh:bpy.types.Mesh,
        original_elementname_data_dict:dict,
        final_elementname_data_dict:dict):

        total_structured_dtype:numpy.dtype = d3d11_game_type.get_total_structured_dtype()

        # Create the element array with the original dtype (matching ByteWidth)
        element_vertex_ndarray = numpy.zeros(len(mesh.loops), dtype=total_structured_dtype)
        # For each expected element, prefer the remapped/modified value in
        # `final_elementname_data_dict` if present; otherwise use the parsed
        # value from `original_elementname_data_dict`.
        for d3d11_element_name in d3d11_game_type.OrderedFullElementList:
            if d3d11_element_name in final_elementname_data_dict:
                data = final_elementname_data_dict[d3d11_element_name]
            else:
                data = original_elementname_data_dict.get(d3d11_element_name, None)

            if data is None:
                # Missing data is a fatal condition — better to raise so caller
                # can diagnose than to silently write zeros for an expected
                # element (which would corrupt downstream buffers).
                raise Fatal(f"Missing element data for '{d3d11_element_name}' when packing vertex ndarray")
            print("尝试赋值 Element: " + d3d11_element_name)
            element_vertex_ndarray[d3d11_element_name] = data
        
        return element_vertex_ndarray
    

    @classmethod
    def calc_index_vertex_buffer_wwmi_v2(
        cls,
        mesh:bpy.types.Mesh, 
        element_vertex_ndarray:numpy.ndarray, 
        dtype:numpy.dtype,
        d3d11_game_type:D3D11GameType):
        '''
        - 用 numpy 将结构化顶点视图为一行字节，避免逐顶点 bytes() 与 dict 哈希。
        - 使用 numpy.unique(..., axis=0, return_index=True, return_inverse=True) 在 C 层完成唯一化与逆映射。
        - 仅在构建 per-polygon IB 时使用少量 Python 切片，整体效率大幅提高。
        - 当 structured dtype 非连续时，内部会做一次拷贝（ascontiguousarray）；通常开销小于逐顶点哈希开销。
        '''

        # (1) loop -> vertex mapping
        loops = mesh.loops
        n_loops = len(loops)
        loop_vertex_indices = numpy.empty(n_loops, dtype=int)
        loops.foreach_get("vertex_index", loop_vertex_indices)

        # (2) 将 element_vertex_ndarray 保证为连续，并视为 (n_loops, row_bytes) uint8 矩阵
        vb = numpy.ascontiguousarray(element_vertex_ndarray)
        row_size = vb.dtype.itemsize
        try:
            row_bytes = vb.view(numpy.uint8).reshape(n_loops, row_size)
        except Exception:
            raw = vb.tobytes()
            row_bytes = numpy.frombuffer(raw, dtype=numpy.uint8).reshape(n_loops, row_size)

        # WWMI-Tools deduplicates loop rows including the loop's VertexId -> they
        # effectively perform uniqueness on loop attributes + VertexId treated as
        # a field. To replicate that reliably (preserving structured field layout
        # and alignment) we build a structured array that copies all existing
        # fields and appends a 'VERTEXID' uint32 field, then call numpy.unique on it.
        # Afterwards we select unique rows from the original `row_bytes` using
        # the indices returned by numpy.unique to preserve exact original layout.

        # Build 4-byte vertex index array (little-endian) and concatenate to row bytes
        # to form combined rows: [row_bytes | vid_bytes]. Use numpy.unique on combined
        # rows to get uniqueness, then reorder unique results to match insertion
        # order (first occurrence). This vectorized path keeps behavior identical
        # to the OrderedDict+bytes approach but runs much faster in numpy.
        # Build 4-byte vertex index array (little-endian)
        vid_bytes = loop_vertex_indices.astype(numpy.uint32).view(numpy.uint8).reshape(n_loops, 4)

        # Combine row bytes + vid bytes, but to make numpy.unique faster we pad the
        # combined row to a multiple of 8 bytes and view it as uint64 blocks.
        total_bytes = row_size + 4
        pad = (-total_bytes) % 8
        padded_width = total_bytes + pad

        # Allocate padded combined buffer and fill
        combined_padded = numpy.zeros((n_loops, padded_width), dtype=numpy.uint8)
        combined_padded[:, :row_size] = row_bytes
        combined_padded[:, row_size:row_size+4] = vid_bytes

        # View as uint64 blocks (shape: n_loops x n_blocks)
        n_blocks = padded_width // 8
        combined_u64 = combined_padded.view(numpy.uint64).reshape(n_loops, n_blocks)

        # Create a structured view so numpy.unique treats each row as a single record
        dtype_descr = [(f'f{i}', numpy.uint64) for i in range(n_blocks)]
        structured = combined_u64.view(numpy.dtype(dtype_descr)).reshape(n_loops)

        unique_struct, unique_first_indices, inverse = numpy.unique(
            structured, return_index=True, return_inverse=True
        )

        # Remap unique ids to insertion order (first occurrence order)
        order = numpy.argsort(unique_first_indices)
        new_id = numpy.empty_like(order)
        new_id[order] = numpy.arange(len(order), dtype=new_id.dtype)
        inverse = new_id[inverse]

        unique_first_indices_insertion = unique_first_indices[order]

        # Pick original unique rows from row_bytes using insertion-ordered indices
        unique_rows = row_bytes[unique_first_indices_insertion]

        # Expose the loop indices (first-occurrence loop indices) used to select
        # the unique rows. Callers can sample per-loop original arrays using
        # these indices to reconstruct per-unique-row original element values.
        unique_first_loop_indices = unique_first_indices_insertion

        # Reconstruct a structured ndarray of the unique element rows.
        # This lets callers access element fields by name for the unique
        # vertex set (useful for debugging or further processing).
        # Ensure the byte width matches the dtype itemsize.
        if unique_rows.shape[1] != dtype.itemsize:
            raise Fatal(f"Unique row byte-size ({unique_rows.shape[1]}) does not match structured dtype itemsize ({dtype.itemsize})")

        n_unique = unique_rows.shape[0]
        unique_rows_contig = numpy.ascontiguousarray(unique_rows)
        try:
            # Zero-copy view where possible
            unique_element_vertex_ndarray = unique_rows_contig.view(dtype).reshape(n_unique)
        except Exception:
            # Fallback to a safe copy-based reconstruction
            unique_element_vertex_ndarray = numpy.frombuffer(unique_rows_contig.tobytes(), dtype=dtype).reshape(n_unique)

        # Expose for downstream use: structure-aligned unique vertex records
        # self.unique_element_vertex_ndarray = unique_element_vertex_ndarray

        # 构建 index -> original vertex id（使用每个 unique 行的第一个 loop 对应的 vertex）
        original_vertex_ids = loop_vertex_indices[unique_first_indices_insertion]
        index_vertex_id_dict = dict(enumerate(original_vertex_ids.astype(int).tolist()))

        # (4) 为每个 polygon 构建 IB（使用 inverse 映射）
        # inverse is already ordered by loops; concatenating polygon slices in
        # polygon order is equivalent to taking inverse in sequence.
        flattened_ib_arr = inverse.astype(numpy.int32)

        # (5) 按 category 从 unique_rows 切分 bytes 序列
        category_stride_dict = d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {}
        stride_offset = 0
        for cname, cstride in category_stride_dict.items():
            category_buffer_dict[cname] = unique_rows[:, stride_offset:stride_offset + cstride].flatten()
            stride_offset += cstride

        # (6) 翻转三角形方向（高效）
        # 鸣潮需要翻转这一下
        flat_arr = flattened_ib_arr
        if flat_arr.size % 3 == 0:
            flipped = flat_arr.reshape(-1, 3)[:, ::-1].flatten().tolist()
        else:
            # Rare irregular case: fallback to python loop on numpy array
            flipped = []
            iarr = flat_arr.tolist()
            for i in range(0, len(iarr), 3):
                tri = iarr[i:i + 3]
                flipped.extend(tri[::-1])

        ib = flipped
        return ib, category_buffer_dict, index_vertex_id_dict, unique_element_vertex_ndarray,unique_first_loop_indices





