import collections
from ..base.d3d11_gametype import D3D11GameType
from ..base.fatal import Fatal


from ..utils.format_utils import FormatUtils
from ..utils.vertexgroup_utils import VertexGroupUtils
from ..utils.timer_utils import TimerUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_generate_mod import Properties_GenerateMod


import bpy
import numpy

class ObjBufferHelper:
    '''
    工具类，由于使用了抽象数据类型
    所以归为Helper类中
    '''

    @staticmethod
    def check_and_verify_attributes(obj:bpy.types.Object, d3d11_game_type:D3D11GameType):
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



    @staticmethod
    def _parse_position(mesh_vertices, mesh_vertices_length, loop_vertex_indices, d3d11_element):
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
        return positions

    @staticmethod
    def _parse_normal(mesh_loops, mesh_loops_length, d3d11_element):
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
            return result

        elif d3d11_element.Format == 'R32G32B32A32_FLOAT':
            
            result = numpy.ones(mesh_loops_length * 4, dtype=numpy.float32)
            result[0::4] = normals[0::3]
            result[1::4] = normals[1::3]
            result[2::4] = normals[2::3]
            result = result.reshape(-1, 4)

            result = result.astype(numpy.float32)
            return result

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

            return FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(result)


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

            return FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)

        elif d3d11_element.Format == "R32_UINT" and GlobalConfig.logic_name == LogicName.AEMI:
             # AEMI Octahedral Normal
             # We need just float3 normals
             raw_normals = normals.reshape(-1, 3)
             # Must reshape to (N, 1) to match structured array shape if expected
             return FormatUtils.convert_normals_to_aemi_octahedral_r32_uint(raw_normals).reshape(-1, 1)
        
        else:
            # 将一维数组 reshape 成 (mesh_loops_length, 3) 形状的二维数组
            result = normals.reshape(-1, 3)

            return result

    @staticmethod
    def _parse_tangent(mesh_loops, mesh_loops_length, d3d11_element):
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
            # print("其它游戏翻转TANGENT的W分量")
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
        
        return result

    @staticmethod
    def _parse_binormal(mesh_loops, mesh_loops_length, d3d11_element):
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
            
        return result

    @staticmethod
    def _parse_color(mesh, mesh_loops_length, d3d11_element_name, d3d11_element):
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
            # TODO 添加八面体压缩法线到R32_UINT的代码

            elif d3d11_element.Format == "R16G16_FLOAT":
                # 
                result = result[:, :2]
            elif d3d11_element.Format == 'R8G8B8A8_UNORM':
                result = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(result)

            print(d3d11_element.Format)
            print(d3d11_element_name)
    
            return result
        return None

    @staticmethod
    def _parse_texcoord(mesh, mesh_loops_length, d3d11_element_name, d3d11_element):
        result = None
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

                result = uvs_array 
        # TimerUtils.End("GET TEXCOORD")
        return result

    @staticmethod
    def _parse_blendindices(blendindices_dict, d3d11_element):
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
            return blendindices
        elif d3d11_element.Format == "R16G16B16A16_UINT":
            return blendindices
        elif d3d11_element.Format == "R32G32B32A32_UINT":
            return blendindices
        elif d3d11_element.Format == "R32G32_UINT":
            return blendindices[:, :2]
        elif d3d11_element.Format == "R32G32_SINT":
            return blendindices[:, :2]
        elif d3d11_element.Format == "R32_UINT":
            return blendindices[:, :1]
        elif d3d11_element.Format == "R32_SINT":
            return blendindices[:, :1]
        elif d3d11_element.Format == 'R8G8B8A8_SNORM':
            return FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendindices)
        elif d3d11_element.Format == 'R8G8B8A8_UNORM':
            return FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm(blendindices)
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
            return blendindices
            # print(original_elementname_data_dict[d3d11_element_name].dtype)
        elif d3d11_element.Format == "R8_UINT" and d3d11_element.ByteWidth == 8:
            max_index = numpy.max(blendindices)
            if max_index > 255:
                print("BLENDINDICES大于255了,最大值是：" + str(max_index))
            else:
                blendindices.astype(numpy.uint8)

            return blendindices
            # print(original_elementname_data_dict[d3d11_element_name].dtype)
            # print("WWMI R8_UINT特殊处理")
        elif d3d11_element.Format == "R16_UINT" and d3d11_element.ByteWidth == 16:
            blendindices.astype(numpy.uint16)
            return blendindices
            # print("WWMI R16_UINT特殊处理")
        else:
            # print(blendindices.shape)
            raise Fatal("未知的BLENDINDICES格式")

    @staticmethod
    def _parse_blendweight(blendweights_dict, d3d11_element):
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
            return blendweights
        elif d3d11_element.Format == "R32G32_FLOAT":
            return blendweights[:, :2]
        elif d3d11_element.Format == 'R8G8B8A8_SNORM':
            # print("BLENDWEIGHT R8G8B8A8_SNORM")
            return FormatUtils.convert_4x_float32_to_r8g8b8a8_snorm(blendweights)
        elif d3d11_element.Format == 'R8G8B8A8_UNORM':
            # print("BLENDWEIGHT R8G8B8A8_UNORM")
            return FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
        elif d3d11_element.Format == 'R16G16B16A16_FLOAT':
            return blendweights.astype(numpy.float16)
        elif d3d11_element.Format == 'R16G16B16A16_UNORM':
            return FormatUtils.convert_4x_float32_to_r16g16b16a16_unorm(blendweights)
        elif d3d11_element.Format == "R8_UNORM" and d3d11_element.ByteWidth == 8:
            # TimerUtils.Start("WWMI BLENDWEIGHT R8_UNORM特殊处理")
            blendweights = FormatUtils.convert_4x_float32_to_r8g8b8a8_unorm_blendweights(blendweights)
            # original_elementname_data_dict[d3d11_element_name] = blendweights
            print("WWMI R8_UNORM特殊处理")
            # TimerUtils.End("WWMI BLENDWEIGHT R8_UNORM特殊处理")
            return blendweights

        else:
            print(blendweights.shape)
            raise Fatal("未知的BLENDWEIGHTS格式")

    @staticmethod
    def parse_elementname_data_dict(mesh:bpy.types.Mesh, d3d11_game_type:D3D11GameType):
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


        # 对每一种Element都获取对应的数据
        for d3d11_element_name in d3d11_game_type.OrderedFullElementList:
            d3d11_element = d3d11_game_type.ElementNameD3D11ElementDict[d3d11_element_name]
            
            data = None

            if d3d11_element_name == 'POSITION':
                data = ObjBufferHelper._parse_position(mesh_vertices, mesh_vertices_length, loop_vertex_indices, d3d11_element)

            elif d3d11_element_name == 'NORMAL':
                data = ObjBufferHelper._parse_normal(mesh_loops, mesh_loops_length, d3d11_element)

            elif d3d11_element_name == 'TANGENT':
                data = ObjBufferHelper._parse_tangent(mesh_loops, mesh_loops_length, d3d11_element)

            elif d3d11_element_name.startswith('BINORMAL'):
                data = ObjBufferHelper._parse_binormal(mesh_loops, mesh_loops_length, d3d11_element)
            
            elif d3d11_element_name.startswith('COLOR'):
                data = ObjBufferHelper._parse_color(mesh, mesh_loops_length, d3d11_element_name, d3d11_element)

            elif d3d11_element_name.startswith('TEXCOORD') and d3d11_element.Format.endswith('FLOAT'):
                data = ObjBufferHelper._parse_texcoord(mesh, mesh_loops_length, d3d11_element_name, d3d11_element)
            
            elif d3d11_element_name.startswith('BLENDINDICES'):
                data = ObjBufferHelper._parse_blendindices(blendindices_dict, d3d11_element)
                
            elif d3d11_element_name.startswith('BLENDWEIGHT'):
                data = ObjBufferHelper._parse_blendweight(blendweights_dict, d3d11_element)

            if data is not None:
                original_elementname_data_dict[d3d11_element_name] = data

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
    

    @staticmethod
    def calc_index_vertex_buffer_wwmi_v2(
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


    @staticmethod
    def average_normal_color(obj,indexed_vertices,d3d11GameType:D3D11GameType,dtype):
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
    


    @staticmethod
    def average_normal_tangent(obj,indexed_vertices,d3d11GameType,dtype):
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

    @staticmethod
    def calc_index_vertex_buffer_universal(element_vertex_ndarray,mesh,obj,d3d11GameType,dtype):
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
        ib = [[indexed_vertices.setdefault(element_vertex_ndarray[blender_lvertex.index].tobytes(), len(indexed_vertices))
                for blender_lvertex in mesh.loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    ]for poly in mesh.polygons] 
            
        flattened_ib = [item for sublist in ib for item in sublist]
        # TimerUtils.End("Calc IB VB")

        # 重计算TANGENT步骤
        indexed_vertices = ObjBufferHelper.average_normal_tangent(obj=obj, indexed_vertices=indexed_vertices, d3d11GameType=d3d11GameType,dtype=dtype)
        
        # 重计算COLOR步骤
        indexed_vertices = ObjBufferHelper.average_normal_color(obj=obj, indexed_vertices=indexed_vertices, d3d11GameType=d3d11GameType,dtype=dtype)

        # print("indexed_vertices:")
        # print(str(len(indexed_vertices)))

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer")
        category_stride_dict = d3d11GameType.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in d3d11GameType.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride

        ib = flattened_ib
        if GlobalConfig.logic_name == LogicName.YYSLS:
            print("导出时翻转面朝向")

            flipped_indices = []
            # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
            for i in range(0, len(flattened_ib), 3):
                triangle = flattened_ib[i:i+3]
                flipped_triangle = triangle[::-1]
                flipped_indices.extend(flipped_triangle)
            # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])
            ib = flipped_indices


        
        category_buffer_dict = category_buffer_dict
        index_vertex_id_dict = None

        return ib,category_buffer_dict,index_vertex_id_dict



    @staticmethod
    def calc_index_vertex_buffer_girlsfrontline2(
        mesh:bpy.types.Mesh, 
        element_vertex_ndarray:numpy.ndarray, 
        d3d11_game_type:D3D11GameType,
        dtype:numpy.dtype):
        '''
        [特殊模式：少前2专用] 强制索引对齐模式
        --------------------------------------------------
        核心逻辑：
        - 强制保持 "游戏引擎顶点数" == "Blender顶点数"。
        - 忽略硬边、UV缝隙导致的数据分裂，强制合并。
        
        适用场景：
        - 少前2等特殊渲染管线，或者模型已经预先处理过（所有硬边/UV缝隙确实就是物理断开的顶点）。
        - 这种模式下生成 ShapeKey 极其简单，因为索引是一一对应的。
        
        缺点：
        - 如果模型存在硬边或UV接缝，数据会被覆盖（合并），可能导致渲染错误（如法线平滑过度、UV错乱）。
        
        1. Blender 的“顶点数”= mesh.vertices 长度，只要位置不同就算一个。
        2. 我们预分配同样长度的盒子列表，盒子下标 == 顶点下标，保证一一对应。
        3. 遍历 loop 时，把真实数据写进对应盒子；没人引用的盒子留 dummy（坐标填对，其余 0）。
        4. 最后按盒子顺序打包成字节数组，长度必然与 mesh.vertices 相同，导出数就能和 Blender 状态栏完全一致。
        '''
        print("calc ivb gf2")

        loops = mesh.loops
        v_cnt = len(mesh.vertices)
        loop_vidx = numpy.empty(len(loops), dtype=int)
        loops.foreach_get("vertex_index", loop_vidx)

        # 1. 预分配：每条 Blender 顶点一条记录，先填“空”
        dummy = numpy.zeros(1, dtype=element_vertex_ndarray.dtype)
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
                data = element_vertex_ndarray[lp.index].copy()
                pn_key = (tuple(data['POSITION']), tuple(data['NORMAL']))
                if pn_key in pos_normal_key:
                    data['TANGENT'] = pos_normal_key[pn_key]
                else:
                    pos_normal_key[pn_key] = data['TANGENT']
                vertex_buffer[v_idx] = data

        # 5. 给“死顶点”也填上 dummy，但位置必须对
        for v_idx in range(v_cnt):
            if not used_mask[v_idx]:
                vertex_buffer[v_idx]['POSITION'] = mesh.vertices[v_idx].co
                # 其余字段保持 0

        # 6. 现在 vertex_buffer 长度 == v_cnt，直接转 bytes 即可
        indexed_vertices = [arr.tobytes() for arr in vertex_buffer]

        # 7. 重建索引缓冲（IB）
        ib = []
        for poly in mesh.polygons:
            ib.append([v_idx for lp in loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    for v_idx in [lp.vertex_index]])

        flattened_ib = [i for sub in ib for i in sub]

        # 8. 拆 CategoryBuffer
        category_stride_dict = d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {name: [] for name in d3d11_game_type.CategoryStrideDict}
        data_matrix = numpy.array([numpy.frombuffer(b, dtype=numpy.uint8) for b in indexed_vertices])
        stride_offset = 0
        for name, stride in category_stride_dict.items():
            category_buffer_dict[name] = data_matrix[:, stride_offset:stride_offset + stride].flatten()
            stride_offset += stride

        # print("长度：", v_cnt)          
        ib = flattened_ib
        index_vertex_id_dict = None

        return ib, category_buffer_dict, index_vertex_id_dict
 


    @staticmethod
    def calc_index_vertex_buffer_unified(
        mesh:bpy.types.Mesh, 
        element_vertex_ndarray:numpy.ndarray, 
        obj:bpy.types.Object, 
        d3d11_game_type:D3D11GameType,
        dtype:numpy.dtype):
        '''
        [通用模式] 标准图形学导出逻辑
        --------------------------------------------------
        核心逻辑：
        - 以 "(数据内容 + Blender原始顶点索引)" 作为唯一标识。
        - 自动处理硬边、UV缝隙：如果同一个顶点在不同 Loop 上的法线/UV不同，会自动分裂成多个游戏顶点。
        - 自动处理 ShapeKey 安全：即使两个点坐标重合，只要 Blender 索引不同，就不会合并。
        
        适用场景：
        - 绝大多数现代游戏的标准导出流程。
        - 保证渲染正确性（法线、UV、顶点色）。
        
        代价：
        - 导出的顶点数通常多于 Blender 顶点数（因为分裂）。
        - 需要返回 index_vertex_id_dict 映射表，以便后续生成 ShapeKey Buffer 时能找回原始对应关系。

        计算IndexBuffer和CategoryBufferDict并返回
        如果模型具有形态键，那么形态键盘的值为0到1的任何值应用后，都不会造成由于顶点合并导致的顶点数改变。
        '''
        # TimerUtils.Start("Calc IB VB")
        
        # 统一逻辑：始终将 (数据 + 顶点索引) 作为唯一标识
        # 1. 彻底解决 ShapeKey 问题：防止 Basis 中重合但在 Morph 中分离的顶点被错误合并。
        # 2. 保持拓扑结构：确保 Blender 中不同的点导出后依然是不同的点。
        unique_map = collections.OrderedDict()
        
        # KEY: unique_vertex_index (buffer index), VALUE: first_loop_index
        # 记录每一个生成的 Buffer 顶点对应的是哪一个原始 Loop
        # 这对于 Shape Key 的法线导出至关重要，因为法线是存储在 Loop 上的
        unique_loop_map = {} 

        ib = []
        for poly in mesh.polygons:
            poly_indices = []
            for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                loop = mesh.loops[loop_index]
                data = element_vertex_ndarray[loop.index].tobytes()
                
                # 核心：Key 始终包含 vertex_index (data, index)
                # 这样只有当 "数据完全一致" 且 "是同一个顶点(仅因硬边/UV断开)" 时才会共用索引
                key = (data, loop.vertex_index)
                
                if key in unique_map:
                    idx = unique_map[key]
                else:
                    idx = len(unique_map)
                    unique_map[key] = idx
                    unique_loop_map[idx] = loop.index
                
                poly_indices.append(idx)
            ib.append(poly_indices)
        
        # 提取 vertex buffer 需要的数据 (也就是 key 中的 data 部分)
        # vertex_data_list = [k[0] for k in unique_map.keys()]

        # 同时构建 index -> blender_loop_index 的映射
        # 这对于后续生成 ShapeKey Buffer 至关重要，因为我们需要知道当前生成的第 i 个点对应 Blender 的哪个 Loop
        # Loop Index 可进一步转换为 Vertex Index，但 Vertex Index 无法反推唯一的 Loop Index (Split Normals)
        vertex_data_list = []
        for i, (data_bytes, blender_v_idx) in enumerate(unique_map.keys()):
            vertex_data_list.append(data_bytes)
        
        index_loop_id_dict = unique_loop_map

        flattened_ib = [item for sublist in ib for item in sublist]
        # TimerUtils.End("Calc IB VB")

        # 重计算TANGENT步骤
        indexed_vertices = ObjBufferHelper.average_normal_tangent(obj=obj, indexed_vertices=vertex_data_list, d3d11GameType=d3d11_game_type,dtype=dtype)
        
        # 重计算COLOR步骤
        indexed_vertices = ObjBufferHelper.average_normal_color(obj=obj, indexed_vertices=indexed_vertices, d3d11GameType=d3d11_game_type,dtype=dtype)

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer")
        category_stride_dict = d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in d3d11_game_type.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride

        # 设置ib，准备返回
        ib = flattened_ib
        # YYSLS是目前除了鸣潮外，唯一需要翻转面朝向的游戏
        if GlobalConfig.logic_name == LogicName.YYSLS:
            flipped_indices = []
            # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
            for i in range(0, len(flattened_ib), 3):
                triangle = flattened_ib[i:i+3]
                flipped_triangle = triangle[::-1]
                flipped_indices.extend(flipped_triangle)
            # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])
            ib = flipped_indices

        return ib, category_buffer_dict,index_loop_id_dict
      