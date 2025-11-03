

import bpy
import os
import numpy
import itertools
import math

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.format_utils import Fatal,FormatUtils
from ..utils.texture_utils import TextureUtils
from ..utils.mesh_utils import MeshUtils
from ..utils.log_utils import LOG

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_wwmi import Properties_WWMI

from ..common.migoto_format import D3D11Element
from ..common.extracted_object import ExtractedObjectHelper

# 用于解决 AttributeError: 'IMPORT_MESH_OT_migoto_raw_buffers_mmt' object has no attribute 'filepath'
from bpy_extras.io_utils import unpack_list, axis_conversion


class FMTFile:
    def __init__(self, fmt_file_path:str):
        self.stride = 0
        self.topology = ""
        self.format = ""
        self.gametypename = ""
        self.prefix = ""
        self.scale = "1.0"
        self.rotate_angle:bool = False
        self.rotate_angle_x:float = 0
        self.rotate_angle_y:float = 0
        self.rotate_angle_z:float = 0
        self.flip_face_orientation:bool = False

        self.elements:list[D3D11Element] = []

        with open(fmt_file_path, 'r') as file:
            lines = file.readlines()

        element_info = {}
        for line in lines:
            parts = line.strip().split(":")
            if len(parts) < 2:
                continue  # 跳过格式不正确的行

            key, value = parts[0].strip(), ":".join(parts[1:]).strip()
            if key == "stride":
                self.stride = int(value)
            elif key == "topology":
                self.topology = value
            elif key == "format":
                self.format = value
            elif key == "gametypename":
                self.gametypename = value
            elif key == "prefix":
                self.prefix = value
            elif key == "scale":
                self.scale = value
            elif key == "rotate_angle":
                self.rotate_angle = value.lower() == "true"
            elif key == "rotate_angle_x":
                self.rotate_angle_x = float(value)
            elif key == "rotate_angle_y":
                self.rotate_angle_y = float(value)
            elif key == "rotate_angle_z":
                self.rotate_angle_z = float(value)
            
            elif key == "flip_face_orientation":
                self.flip_face_orientation = value.lower() == "true"

            elif key.startswith("element"):
                # 处理element块
                if "SemanticName" in element_info:
                    append_d3delement = D3D11Element(
                        SemanticName=element_info["SemanticName"], SemanticIndex=int(element_info["SemanticIndex"]),
                        Format= element_info["Format"],AlignedByteOffset= int(element_info["AlignedByteOffset"]),
                        ByteWidth=0,
                        ExtractSlot="0",ExtractTechnique="",Category="")
                    
                    if "ByteWidth" in element_info:
                        # print("读取到ByteWidth存在: " + element_info["ByteWidth"])
                        append_d3delement.ByteWidth = int(element_info["ByteWidth"])
                    else:
                        append_d3delement.ByteWidth = FormatUtils.format_size(append_d3delement.Format)
                    
                    # 如果已经有一个element信息，则先添加到列表中
                    self.elements.append(append_d3delement)
                    element_info.clear()  # 清空当前element信息

                # 将新的element属性添加到element_info字典中
                element_info[key.split()[0]] = value
            elif key in ["SemanticName", "SemanticIndex", "Format","ByteWidth", "InputSlot", "AlignedByteOffset", "InputSlotClass", "InstanceDataStepRate"]:
                element_info[key] = value

        # 添加最后一个element
        if "SemanticName" in element_info:
            append_d3delement = D3D11Element(
                SemanticName=element_info["SemanticName"], SemanticIndex=int(element_info["SemanticIndex"]),
                Format= element_info["Format"],AlignedByteOffset= int(element_info["AlignedByteOffset"]),
                ByteWidth=0,
                ExtractSlot="0",ExtractTechnique="",Category=""
            )

            if "ByteWidth" in element_info:
                # print("读取到ByteWidth存在: " + element_info["ByteWidth"])
                append_d3delement.ByteWidth = int(element_info["ByteWidth"])
            else:
                append_d3delement.ByteWidth = FormatUtils.format_size(append_d3delement.Format)

            self.elements.append(append_d3delement)

    def __repr__(self):
        return (f"FMTFile(stride={self.stride}, topology='{self.topology}', format='{self.format}', "
                f"gametypename='{self.gametypename}', prefix='{self.prefix}', elements={self.elements})")
    
    def get_dtype(self):
        fields = []
        for elemnt in self.elements:
            # Numpy类型由Format决定，此时即使是WWMI的特殊R8_UINT也能得到正确的numpy.uint8
            numpy_type = FormatUtils.get_nptype_from_format(elemnt.Format)

            # 这里我们用ByteWidth / numpy_type.itemsize 得到总的维度数量，也就是列数
            # XXX 注意这里计算出正常Size的前提是numpy_type确定是对应真实的字节数，且ByteWidth正确，也就是数据类型必须完全正确。
            size = int( elemnt.ByteWidth / numpy.dtype(numpy_type).itemsize)

            # print("element: "+ elemnt.ElementName)
            # print(numpy_type)
            # print(size)
            fields.append((elemnt.ElementName,numpy_type , size))
        dtype = numpy.dtype(fields)
        return dtype


class MigotoBinaryFile:

    '''
    3Dmigoto模型文件

    暂时还没有更好的设计，暂时先沿用旧的ib vb fmt设计
    
    prefix是前缀，比如Body.ib Body.vb Body.fmt 那么此时Body就是prefix
    location_folder_path是存放这些文件的文件夹路径，比如当前工作空间中提取的对应数据类型文件夹

    '''
    def __init__(self, fmt_path:str, mesh_name:str = ""):
        self.fmt_file = FMTFile(fmt_path)
        print("fmt_path: " + fmt_path)
        location_folder_path = os.path.dirname(fmt_path)
        print("location_folder_path: " + location_folder_path)

        if self.fmt_file.prefix == "":
            self.fmt_file.prefix = os.path.basename(fmt_path).split(".fmt")[0]

        if mesh_name == "":
            self.mesh_name = self.fmt_file.prefix
        else:
            self.mesh_name = mesh_name
        

        print("prefix: " + self.fmt_file.prefix)
        self.init_from_prefix(self.fmt_file.prefix, location_folder_path)

    def init_from_prefix(self,prefix:str, location_folder_path:str):

        self.fmt_name = prefix + ".fmt"
        self.vb_name = prefix + ".vb"
        self.ib_name = prefix + ".ib"

        self.location_folder_path = location_folder_path

        self.vb_bin_path = os.path.join(location_folder_path, self.vb_name)
        self.ib_bin_path = os.path.join(location_folder_path, self.ib_name)
        self.fmt_path = os.path.join(location_folder_path, self.fmt_name)

        self.file_sanity_check()

        self.vb_file_size = os.path.getsize(self.vb_bin_path)
        self.ib_file_size = os.path.getsize(self.ib_bin_path)

        self.init_data()

    def init_data(self):
        ib_stride = FormatUtils.format_size(self.fmt_file.format)

        self.ib_count = int(self.ib_file_size / ib_stride)
        self.ib_polygon_count = int(self.ib_count / 3)
        self.ib_data = numpy.fromfile(self.ib_bin_path, dtype=FormatUtils.get_nptype_from_format(self.fmt_file.format), count=self.ib_count)
        
        # 读取fmt文件，解析出后面要用的dtype
        fmt_dtype = self.fmt_file.get_dtype()
        vb_stride = fmt_dtype.itemsize

        self.vb_vertex_count = int(self.vb_file_size / vb_stride)
        self.vb_data = numpy.fromfile(self.vb_bin_path, dtype=fmt_dtype, count=self.vb_vertex_count)

    
    def file_sanity_check(self):
        '''
        检查对应文件是否存在，不存在则抛出异常
        三个文件，必须都存在，缺一不可
        '''
        if not os.path.exists(self.vb_bin_path):
            raise Fatal("Unable to find matching .vb file for : " + self.mesh_name)
        if not os.path.exists(self.ib_bin_path):
            raise Fatal("Unable to find matching .ib file for : " + self.mesh_name)
        # if not os.path.exists(self.fmt_path):
        #     raise Fatal("Unable to find matching .fmt file for : " + self.mesh_name)

    def file_size_check(self) -> bool:
        '''
        检查.ib和.vb文件是否为空，如果为空则弹出错误提醒信息，但不报错。
        '''
        # 如果vb和ib文件不存在，则跳过导入
        # 我们不能直接抛出异常，因为有些.ib文件是空的占位文件
        if self.vb_file_size == 0:
            LOG.warning("Current Import " + self.vb_name +" file is empty, skip import.")
            return False
        
        if self.ib_file_size == 0:
            LOG.warning("Current Import " + self.ib_name + " file is empty, skip import.")
            return False
        
        return True

class MeshImporter:
    '''
    这个类依赖于提供的MigotoBinaryFile进行数据导入和处理
    '''
    @classmethod
    def create_mesh_obj_from_mbf(cls, mbf:MigotoBinaryFile):
        TimerUtils.Start("Import 3Dmigoto Raw")
        print("导入模型: " + mbf.mesh_name)
        
        if not mbf.file_size_check():
            return None

        # 创建mesh和obj
        mesh = bpy.data.meshes.new(mbf.mesh_name)
        obj = bpy.data.objects.new(mesh.name, mesh)

        MeshImporter.set_import_coordinate(obj=obj)
        MeshImporter.set_import_attributes(obj=obj, mbf=mbf)
        MeshImporter.initialize_mesh(mesh, mbf)

        

        blend_indices = {}
        blend_weights = {}
        texcoords = {}
        shapekeys = {}
        use_normals = False
        normals = []


        for element in mbf.fmt_file.elements:
            data = mbf.vb_data[element.ElementName]

            print("当前Element: " + element.ElementName)
            print("当前数据转换前 Shape: " + str(data.shape))
            data = FormatUtils.apply_format_conversion(data, element.Format)
            print("当前数据转换后 Shape: " + str(data.shape))

            if element.SemanticName == "POSITION":
                if len(data[0]) == 4:
                    # Nico: 这里改为只要所有的第四位都是0或1就可以近似看为3D的 POSITION
                    # 这种处理是偷懒，第四位直接不管了，呵呵呵
                    if not all(x[3] in (0, 1) for x in data):
                    # if ([x[3] for x in data] != [1.0] * len(data)) and ([x[3] for x in data] != [0] * len(data)):
                        raise Fatal('Positions are 4D')
                    
                # XXX 翻转X轴，Blender的X轴是左手系，D3D11是右手系
                # 这一步是为了解决导入的模型是镜像的问题
                if Properties_ImportModel.use_mirror_workflow():
                    print("使用非镜像工作流导入模型")
                    positions = [(x[0] * -1, x[1] , x[2] ) for x in data]
                else:
                    positions = [(x[0], x[1] , x[2] ) for x in data]

                mesh.vertices.foreach_set('co', unpack_list(positions))
            elif element.SemanticName.startswith("COLOR"):
                mesh.vertex_colors.new(name=element.ElementName)
                color_layer = mesh.vertex_colors[element.ElementName].data
                for l in mesh.loops:
                    color_layer[l.index].color = list(data[l.vertex_index]) + [0] * (4 - len(data[l.vertex_index]))
                
            elif element.SemanticName == "BLENDINDICES":
                if data.ndim == 1:
                    # 如果data是一维数组，转换为包含元组的2D数组，用于处理只有一个R32_UINT的情况
                    data_2d = numpy.array([(x,) for x in data])
                    blend_indices[element.SemanticIndex] = data_2d
                else:
                    blend_indices[element.SemanticIndex] = data
                # print("Import BLENDINDICES Shape: " + str(blend_indices[element.SemanticIndex].shape))
            
            # 因为历史遗留问题，部分名为BLENDWEIGHT部分名为BLENDWEIGHTS，所以这里俩都判断
            # 而由于YYSLS中出现了BLENDWEIGHTEXT，BLENDINDICESEXT，所以不能用StartsWith("BLENDWEIGHT")来判断
            elif element.SemanticName == "BLENDWEIGHT" or element.SemanticName == "BLENDWEIGHTS":
                blend_weights[element.SemanticIndex] = data
                # print("Import BLENDWEIGHT Shape: " + str(blend_indices[element.SemanticIndex].shape))
            elif element.SemanticName.startswith("TEXCOORD"):
                texcoords[element.SemanticIndex] = data
            elif element.SemanticName.startswith("SHAPEKEY"):
                shapekeys[element.SemanticIndex] = data
            elif element.SemanticName.startswith("NORMAL"):
                use_normals = True
                '''
                燕云十六声在导入法线时，必须先进行处理。
                这里要注意一个点，如果dump出来的法线数据，全部是正数的话，说明导出时进行了归一化
                比如燕云的法线就是R8G8B8A8_UNORM格式的，而正常的法线应该是R8G8B8A8_SNORM，说明这里进行了归一化到[0,1]之间
                所以从游戏里导入这种归一化[0,1]的法线时，要反过来操作一下，也就是乘以2再减1范围变为[-1,1]
                Blender的法线范围就是[-1,1]
                这种归一化后到[0,1]的法线，可以减少Shader的计算消耗。
                # (此处感谢 球球 的代码开发)
                '''
                if GlobalConfig.logic_name == LogicName.YYSLS:
                    print("燕云十六声法线处理")
                    normals = [(x[0] * 2 - 1, x[1] * 2 - 1, x[2] * 2 - 1) for x in data]
                else:
                    normals = [(x[0], x[1], x[2]) for x in data]
            elif element.SemanticName == "TANGENT":
                pass
            elif element.SemanticName == "BINORMAL":
                pass
            else:
                raise Fatal("Unknown ElementName: " + element.ElementName)

        # 导入完之后，如果发现blend_weights是空的，则自动补充默认值为1,0,0,0的BLENDWEIGHTS
        if len(blend_weights) == 0 and len(blend_indices) != 0:
            print("检测到BLENDWEIGHTS为空，但是含有BLENDINDICES数据，特殊情况，默认补充1,0,0,0的BLENDWEIGHTS")
            tmpi = 0
            for blendindices_turple in blend_indices.values():
                # print(blendindices_turple)
                new_dict = []
                for indices in blendindices_turple:
                    new_dict.append((1.0,0,0,0))
                blend_weights[tmpi] = new_dict
                tmpi = tmpi + 1

        MeshImporter.import_uv_layers(mesh, obj, texcoords)

        #  metadata.json, if contains then we can import merged vgmap.
        component = None
        if Properties_WWMI.import_merged_vgmap() and GlobalConfig.logic_name == LogicName.WWMI:
            print("尝试读取Metadata.json")
            metadatajsonpath = os.path.join(os.path.dirname(mbf.fmt_path),'Metadata.json')
            if os.path.exists(metadatajsonpath):
                print("鸣潮读取Metadata.json")
                extracted_object = ExtractedObjectHelper.read_metadata(metadatajsonpath)
                if "-" in mbf.mesh_name:
                    partname_count = int(mbf.mesh_name.split("-")[1]) - 1
                    print("import partname count: " + str(partname_count))
                    component = extracted_object.components[partname_count]
        # print(len(blend_indices))
        # print(len(blend_weights))

        print("导入顶点组")
        MeshImporter.import_vertex_groups(mesh, obj, blend_indices, blend_weights, component)
        print("导入顶点组完毕")


        MeshImporter.import_shapekeys(mesh, obj, shapekeys)

        # Validate closes the loops so they don't disappear after edit mode and probably other important things:
        mesh.validate(verbose=False, clean_customdata=False)  
        mesh.update()
        # XXX 这个方法还必须得在mesh.validate和mesh.update之后调用 3.6和4.2都可以用这个
        if use_normals:
            MeshUtils.set_import_normals(mesh=mesh,normals=normals)
        
        MeshImporter.create_bsdf_with_diffuse_linked(obj, mesh_name=mbf.mesh_name,directory=os.path.dirname(mbf.fmt_path))
        MeshImporter.set_import_rotate_angle(obj=obj, mbf=mbf)
        MeshImporter.set_import_scale(obj=obj, mbf=mbf)

        TimerUtils.End("Import 3Dmigoto Raw")

        return obj
    
    @classmethod
    def set_import_attributes(cls, obj, mbf:MigotoBinaryFile):
        '''
        设置导入时的初始属性
        '''
        # 设置默认不重计算TANGNET和COLOR
        # 这里每个游戏的属性都不一样，所以预设为False，让用户自己选择是否启用
        obj["3DMigoto:RecalculateTANGENT"] = False
        obj["3DMigoto:RecalculateCOLOR"] = False
        # 设置GameTypeName，方便在Catter的Properties面板中查看
        obj['3DMigoto:GameTypeName'] = mbf.fmt_file.gametypename


    @classmethod
    def set_import_coordinate(cls,obj):
        '''
        虽然每个游戏导入时的坐标不一致，导致模型朝向都不同，但是不在这里修改，而是在后面根据具体的游戏进行扶正
        '''
        obj.matrix_world = axis_conversion(from_forward='-Z', from_up='Y').to_4x4()





    @classmethod
    def set_import_scale(cls,obj,mbf:MigotoBinaryFile):
        # 设置导入时模型大小比例，Unreal模型常用
        scalefactor = Properties_ImportModel.model_scale()
        if scalefactor == 1.0:
            if mbf.fmt_file.scale != "1.0":
                obj.scale.x = float(mbf.fmt_file.scale)
                obj.scale.y = float(mbf.fmt_file.scale)
                obj.scale.z = float(mbf.fmt_file.scale)
        else:
            obj.scale = scalefactor,scalefactor,scalefactor

    @classmethod
    def set_import_rotate_angle(cls,obj,mbf:MigotoBinaryFile):
        # 设置导入时的模型旋转角度，每个游戏都不一样，由生成fmt的程序控制。
        if mbf.fmt_file.rotate_angle:
            obj.rotation_euler[0] = math.radians(mbf.fmt_file.rotate_angle_x)
            obj.rotation_euler[1] = math.radians(mbf.fmt_file.rotate_angle_y)
            obj.rotation_euler[2] = math.radians(mbf.fmt_file.rotate_angle_z)

    @classmethod
    def initialize_mesh(cls,mesh, mbf:MigotoBinaryFile):
        # 翻转索引顺序以改变面朝向，只能改变面朝向，模型依然是镜像的
        # print(mbf.ib_data[0],mbf.ib_data[1],mbf.ib_data[2])
        if Properties_ImportModel.use_mirror_workflow():
            if not mbf.fmt_file.flip_face_orientation:  # 假设你有一个标志位控制是否翻转
                flipped_indices = []
                for i in range(0, len(mbf.ib_data), 3):
                    triangle = mbf.ib_data[i:i+3]
                    flipped_triangle = triangle[::-1]
                    flipped_indices.extend(flipped_triangle)
                mbf.ib_data = flipped_indices
        else:
            if mbf.fmt_file.flip_face_orientation:  # 假设你有一个标志位控制是否翻转
                flipped_indices = []
                for i in range(0, len(mbf.ib_data), 3):
                    triangle = mbf.ib_data[i:i+3]
                    flipped_triangle = triangle[::-1]
                    flipped_indices.extend(flipped_triangle)
                mbf.ib_data = flipped_indices
        # print(mbf.ib_data[0],mbf.ib_data[1],mbf.ib_data[2])

        # 导入IB文件设置为mesh的三角形索引
        mesh.loops.add(mbf.ib_count)
        mesh.polygons.add(mbf.ib_polygon_count)
        mesh.loops.foreach_set('vertex_index', mbf.ib_data)
        mesh.polygons.foreach_set('loop_start', [x * 3 for x in range(mbf.ib_polygon_count)])
        mesh.polygons.foreach_set('loop_total', [3] * mbf.ib_polygon_count)

        # 根据vb文件的顶点数设置mesh的顶点数
        mesh.vertices.add(mbf.vb_vertex_count)

        # Blender 5.1 Alpha某次更新后，必须得加这么一句，不然的话导入就是点集，原理未知反正加上就行了，不管那么多了。
        mesh.update()

    @classmethod
    def import_uv_layers(cls,mesh, obj, texcoords):
        # 预先获取所有循环的顶点索引并转换为numpy数组
        loops = mesh.loops
        vertex_indices = numpy.array([l.vertex_index for l in loops], dtype=numpy.int32)
        
        for texcoord, data in sorted(texcoords.items()):
            # 将原始数据转换为numpy数组（只需转换一次）
            data_np = numpy.array(data, dtype=numpy.float32)
            dim = data_np.shape[1]
            
            # 确定需要处理的坐标分量组合
            '''
            XXX DOAV TEXCOORD是4D的问题。
            DOAV中，TEXCOORD的Format是R16G16B16A16_FLOAT，导入进来就会被切成这样的TEXCOORD.xy,TEXCOORD.zw
            然后导出时应该也需要特殊的处理。
            但是我们并不这么做，因为R16G16B16A16_FLOAT可以拆成两个UV，分别为R16G16_FLOAT
            所以在设计数据类型的时候，所有R16G16B16A16_FLOAT这种4D类型的TEXCOORD都应该拆成两个R16G16_FLOAT类型的UV进行处理。
            '''
            if dim == 4:
                components_list = ('xy', 'zw')
            elif dim == 2:
                components_list = ('xy',)
            else:
                raise Fatal(f'Unhandled TEXCOORD dimension: {dim}')
            
            cmap = {'x': 0, 'y': 1, 'z': 2, 'w': 3}
            
            for components in components_list:
                # 创建UV层
                uv_name = f'TEXCOORD{texcoord if texcoord else ""}.{components}'
                mesh.uv_layers.new(name=uv_name)
                blender_uvs = mesh.uv_layers[uv_name]
                
                # 获取分量对应的索引
                c0 = cmap[components[0]]
                c1 = cmap[components[1]]
                
                # 批量计算所有顶点的UV坐标（使用向量化操作）
                uvs = numpy.empty((len(data_np), 2), dtype=numpy.float32)
                uvs[:, 0] = data_np[:, c0]           # U分量
                uvs[:, 1] = 1.0 - data_np[:, c1]     # V分量翻转
                
                # 通过顶点索引获取循环的UV数据并展平为一维数组
                uv_array = uvs[vertex_indices].ravel()
                
                # 批量设置UV数据（自动处理numpy数组）
                blender_uvs.data.foreach_set('uv', uv_array)

    @classmethod
    def import_vertex_groups(cls,mesh, obj, blend_indices, blend_weights,component):
        '''
        component: 如果是一键导入WWMI的模型则不为None，其它情况默认为None
        '''

        # 注意，这里的打印，如果是CPU类型则会直接报错，不是测试时期不要开启
        # if len(blend_indices) > 0:
        #     print(blend_indices[0][0])
        #     print(blend_indices[0][1])
        #     LOG.newline()

        '''
        这里的处理是很必要的，因为如果BLENDINDICES的格式是R16G16B16A16_UINT，那么长度为8
        此时游戏中可能会出现值为FF FF 的无效索引表示，虽然在HLSL中表示无效索引，但是导入进来之后，按照R16G16B16A16_UINT来解析就是65535
        这会导致后面创建顶点组数量时，直接卡死，所以我们要替换为-1才能够正常导入。
        此问题在第五人格公研服Neox3引擎中发现并测试。
        所以在这里要转换为numpy数组处理，方便把所有65535替换为-1
        虽然导出时变为 00 00和原本的FF FF不一样，但是游戏中显示Mod是正常的，所以可以确定这么处理是没问题的
        '''
        for semantic_index, bone_indices_list in blend_indices.items():
            # 转为 NumPy 数组处理
            arr = numpy.array(bone_indices_list)
            arr = numpy.where(arr == 65535, -1, arr)
            blend_indices[semantic_index] = arr  # 或 .tolist() 如果后面要用 list



        assert (len(blend_indices) == len(blend_weights))
        if blend_indices:
            # We will need to make sure we re-export the same blend indices later -
            # that they haven't been renumbered. Not positive whether it is better
            # to use the vertex group index, vertex group name or attach some extra
            # data. Make sure the indices and names match:
            if component is None:
                num_vertex_groups = max(itertools.chain(*itertools.chain(*blend_indices.values()))) + 1
            else:
                num_vertex_groups = max(component.vg_map.values()) + 1
            
            print("num_vertex_groups: " + str(num_vertex_groups))

            if num_vertex_groups > 10000:
                raise Fatal("检测到在当前导入的数据类型" + obj.get('3DMigoto:GameTypeName',"") + "描述下，BLENDINDICES顶点组数量为: " + str(num_vertex_groups) + " 基本不可能是正常情况，请更换其他数据类型重新导入")
            
            for i in range(num_vertex_groups):
                obj.vertex_groups.new(name=str(i))
            for vertex in mesh.vertices:
                for semantic_index in sorted(blend_indices.keys()):
                    for i, w in zip(blend_indices[semantic_index][vertex.index], blend_weights[semantic_index][vertex.index]):
                        if w == 0.0:
                            continue
                        if component is None:
                            obj.vertex_groups[i].add((vertex.index,), w, 'REPLACE')
                        else:
                            # 这里由于C++生成的json文件是无序的，所以我们这里读取的时候要用原始的map而不是转换成列表的索引，避免无序问题
                            obj.vertex_groups[component.vg_map[str(i)]].add((vertex.index,), w, 'REPLACE')

    @classmethod
    def import_shapekeys(cls,mesh, obj, shapekeys):
        if not shapekeys:
            return
        
        # ========== 基础形状键预处理 ==========
        basis = obj.shape_key_add(name='Basis')
        basis.interpolation = 'KEY_LINEAR'
        obj.data.shape_keys.use_relative = True

        # 批量获取基础顶点坐标（约快200倍）
        vert_count = len(obj.data.vertices)
        basis_co = numpy.empty(vert_count * 3, dtype=numpy.float32)
        basis.data.foreach_get('co', basis_co)
        basis_co = basis_co.reshape(-1, 3)  # 转换为(N,3)形状

        # ========== 批量处理所有形状键 ==========
        for sk_id, offsets in shapekeys.items():
            # 添加新形状键
            new_sk = obj.shape_key_add(name=f'Deform {sk_id}')
            new_sk.interpolation = 'KEY_LINEAR'

            # 转换为NumPy数组（假设offsets是列表的列表）
            offset_arr = numpy.array(offsets, dtype=numpy.float32).reshape(-1, 3)

            # 向量化计算新坐标（比循环快100倍）
            new_co = basis_co + offset_arr

            # 批量写入形状键数据（约快300倍）
            new_sk.data.foreach_set('co', new_co.ravel())

            # 强制解除Blender数据块的引用（重要！避免内存泄漏）
            del new_sk

        # 清理临时数组
        del basis_co, offset_arr, new_co

    @classmethod
    def create_bsdf_with_diffuse_linked(cls, obj, mesh_name:str, directory:str):
        '''
        自动上DiffuseMap贴图
        '''
        # Credit to Rayvy
        # Изменим имя текстуры, чтобы оно точно совпадало с шаблоном (Change the texture name to match the template exactly)
        material_name = f"{mesh_name}_Material"

        if "." in mesh_name:
            mesh_name_split = str(mesh_name).split(".")[0].split("-")
        else:
            mesh_name_split = str(mesh_name).split("-")
        
        if len(mesh_name_split) < 2:
            return
        
        texture_prefix = mesh_name_split[0] + "_" + mesh_name_split[1] + "_" # IB Hash
        
        # 查找是否存在满足条件的转换好的tga贴图文件
        texture_path = None
        
        texture_suffix = "_DiffuseMap.dds"
        texture_path = TextureUtils.find_texture(texture_prefix, texture_suffix, directory)

        # Nico: 这里如果没有检测到对应贴图则不创建材质，也不新建BSDF
        # 否则会造成合并模型后，UV编辑界面选择不同材质的UV会跳到不同UV贴图界面导致无法正常编辑的问题
        if texture_path is not None:
            # Создание нового материала (Create new materials)

            # 创建一个材质并且自动创建BSDF节点
            material = bpy.data.materials.new(name=material_name)

            # 启用节点系统。
            material.use_nodes = True

            # Nico: Currently only support EN and ZH-CN
            # 4.2 简体中文是 "原理化 BSDF" 英文是 "Principled BSDF"
            bsdf = material.node_tree.nodes.get("原理化 BSDF")
            if not bsdf: 
                # 3.6 简体中文是原理化BSDF 没空格
                bsdf = material.node_tree.nodes.get("原理化BSDF")
            if not bsdf:
                bsdf = material.node_tree.nodes.get("Principled BSDF")

            if bsdf:
                # Поиск текстуры (Search for textures)
                if texture_path:
                    tex_image = material.node_tree.nodes.new('ShaderNodeTexImage')

                    tex_image.image = bpy.data.images.load(texture_path)

                    # 因为tga格式贴图有alpha通道，所以必须用CHANNEL_PACKED才能显示正常颜色
                    # PxncAcd: 然而材质预览时通道打包/Channel Packed 也会坠机，改用 None
                    tex_image.image.alpha_mode = "NONE"

                    # 放置节点位置
                    tex_image.location.x = bsdf.location.x - 400
                    tex_image.location.y = bsdf.location.y
                
                    # 链接Color到基础色
                    material.node_tree.links.new(bsdf.inputs['Base Color'], tex_image.outputs['Color'])
                    # 链接Alpha到Alpha
                    material.node_tree.links.new(bsdf.inputs['Alpha'], tex_image.outputs['Alpha'])

                # Применение материала к мешу (Materials applied to bags)
                if obj.data.materials:
                    obj.data.materials[0] = material
                else:
                    obj.data.materials.append(material)
