import struct
import numpy



from ..common.migoto_format import *

from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import *
from ..config.main_config import *
from ..utils.json_utils import *
from ..utils.timer_utils import TimerUtils
from ..utils.format_utils import Fatal
from ..utils.obj_utils import *
from ..utils.shapekey_utils import ShapeKeyUtils
from ..utils.log_utils import LOG

from .extracted_object import ExtractedObject, ExtractedObjectHelper
from ..common.migoto_format import M_DrawIndexed
from ..base.obj_data_model import ObjDataModel
from ..base.component_model import ComponentModel

from ..config.import_config import ImportConfig
from .obj_buffer_model import ObjBufferModel

from .branch_model import BranchModel

from ..config.properties_wwmi import Properties_WWMI



class DrawIBModelWWMI:
    '''
    这个代表了一个DrawIB的Mod导出模型
    Mod导出可以调用这个模型来进行业务逻辑部分
    每个游戏的DrawIBModel都是不同的，但是一部分是可以复用的
    (例如WWMI就有自己的一套DrawIBModel) 
    '''

    # 通过default_factory让每个类的实例的变量分割开来，不再共享类的静态变量
    def __init__(self,draw_ib:str,branch_model:BranchModel):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib = draw_ib
        self.draw_ib_alias = draw_ib_alias_name_dict.get(draw_ib,draw_ib)

        # (2) 读取工作空间中配置文件的配置项
        self.import_config = ImportConfig(draw_ib=self.draw_ib)
        self.d3d11GameType:D3D11GameType = self.import_config.d3d11GameType
        # 读取WWMI专属配置
        self.extracted_object:ExtractedObject = ExtractedObjectHelper.read_metadata(GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=self.d3d11GameType.GameTypeName)  + "Metadata.json")

        '''
        这里是要得到每个Component对应的obj_data_model列表
        '''
        self.ordered_obj_data_model_list:list[ObjDataModel] = branch_model.get_obj_data_model_list_by_draw_ib(draw_ib=draw_ib)
        
        # (3) 组装成特定格式？
        self.component_model_list:list[ComponentModel] = []
        self.component_name_component_model_dict:dict[str,ComponentModel] = {}

        for part_name in self.import_config.part_name_list:
            print("part_name: " + part_name)
            component_obj_data_model_list = []
            for obj_data_model in self.ordered_obj_data_model_list:
                if part_name == str(obj_data_model.component_count):
                    component_obj_data_model_list.append(obj_data_model)
                    print("obj_data_model: " + obj_data_model.obj_name)

            component_model = ComponentModel(component_name="Component " + part_name,final_ordered_draw_obj_model_list=component_obj_data_model_list)
            
            self.component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = component_model
        LOG.newline()

        # TODO 在这里遍历获取每个Component的obj列表，然后对这些obj进行统计，统计BLENDINDICES和BLENDWEIGHTS
        # 生成BlendRemapForward.buf中的内容
        # 每个Component 每512个数字为一组，有几个Component就有几组 格式：R16_UINT
        # 对应的位数就是局部顶点索引
        # 对应的位上的内容就是原始的顶点组索引
        
        # 需要一个方法，能够获取指定obj的所有的d3d11Element内容。
        # 其次就是可能要考虑到先声明数据类型，后进行执行的问题，比如WWMI就是把所有的数据类型提前全部声明好
        # 最后需要的时候只执行一次就把所有的内容都拿到了，本质上是数据类型设计的比较好。
        


        # (4) 根据之前解析集合架构的结果，读取obj对象内容到字典中
        self.mesh_vertex_count = 0 # 每个DrawIB都有总的顶点数，对应CategoryBuffer里的顶点数。

        # (5) 对所有obj进行融合，得到一个最终的用于导出的临时obj
        self.merged_object = self.build_merged_object(
            extracted_object=self.extracted_object
        )

        # (6) 填充每个obj的drawindexed值，给每个obj的属性统计好，后面就能直接用了。
        self.obj_name_drawindexed_dict:dict[str,M_DrawIndexed] = {} 
        for comp in self.merged_object.components:
            for comp_obj in comp.objects:
                draw_indexed_obj = M_DrawIndexed()
                draw_indexed_obj.DrawNumber = str(comp_obj.index_count)
                draw_indexed_obj.DrawOffsetIndex = str(comp_obj.index_offset)
                draw_indexed_obj.AliasName = comp_obj.name
                self.obj_name_drawindexed_dict[comp_obj.name] = draw_indexed_obj
        
        # (7) 填充到component_name为key的字典中，方便后续操作
        for component_model in self.component_model_list:
            new_ordered_obj_model_list = []
            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_model.drawindexed_obj = self.obj_name_drawindexed_dict[obj_model.obj_name]
                new_ordered_obj_model_list.append(obj_model)
            component_model.final_ordered_draw_obj_model_list = new_ordered_obj_model_list
            self.component_name_component_model_dict[component_model.component_name] = component_model
        
        # (8) 选中当前融合的obj对象，计算得到ib和category_buffer，以及每个IndexId对应的VertexId
        merged_obj = self.merged_object.object

        merged_obj.name
        
        TimerUtils.Start("构建ObjBufferModel")
        obj_buffer_model = ObjBufferModel(d3d11_game_type=self.d3d11GameType,obj_name=merged_obj.name)
        TimerUtils.End("构建ObjBufferModel")

        # 写出到文件
        self.write_out_index_buffer(ib=obj_buffer_model.ib)
        self.write_out_category_buffer(category_buffer_dict=obj_buffer_model.category_buffer_dict)
        self.write_out_shapekey_buffer(merged_obj=merged_obj, index_vertex_id_dict=obj_buffer_model.index_vertex_id_dict)

        # TODO 如果Merged架构下，顶点组数量超过了255，则必须使用Remap技术
        # 则必须判断每个Component，但是这里已经获取不到每个Component的数据了。
        # 所以必须往前几个步骤去想办法
        
        # 删除临时融合的obj对象
        bpy.data.objects.remove(merged_obj, do_unlink=True)


    def write_out_index_buffer(self,ib):
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        packed_data = struct.pack(f'<{len(ib)}I', *ib)
        with open(buf_output_folder + self.draw_ib + "-Component1.buf", 'wb') as ibf:
            ibf.write(packed_data) 

    def write_out_category_buffer(self,category_buffer_dict):
        __categoryname_bytelist_dict = {} 
        for category_name in self.d3d11GameType.OrderedCategoryNameList:
            if category_name not in __categoryname_bytelist_dict:
                __categoryname_bytelist_dict[category_name] =  category_buffer_dict[category_name]
            else:
                existing_array = __categoryname_bytelist_dict[category_name]
                buffer_array = category_buffer_dict[category_name]

                # 确保两个数组都是NumPy数组
                existing_array = numpy.asarray(existing_array)
                buffer_array = numpy.asarray(buffer_array)

                # 使用 concatenate 连接两个数组，确保传递的是一个序列（如列表或元组）
                concatenated_array = numpy.concatenate((existing_array, buffer_array))

                # 更新字典中的值
                __categoryname_bytelist_dict[category_name] = concatenated_array

        # 顺便计算一下步长得到总顶点数
        position_stride = self.d3d11GameType.CategoryStrideDict["Position"]
        position_bytelength = len(__categoryname_bytelist_dict["Position"])
        self.mesh_vertex_count = int(position_bytelength/position_stride)

        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()
            
        for category_name, category_buf in __categoryname_bytelist_dict.items():
            buf_path = buf_output_folder + self.draw_ib + "-" + category_name + ".buf"
             # 将 list 转换为 numpy 数组
            # category_array = numpy.array(category_buf, dtype=numpy.uint8)
            with open(buf_path, 'wb') as ibf:
                category_buf.tofile(ibf)

    def write_out_shapekey_buffer(self,merged_obj,index_vertex_id_dict):
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        self.shapekey_offsets = []
        self.shapekey_vertex_ids = []
        self.shapekey_vertex_offsets = []

        # (11) 拼接ShapeKey数据
        if merged_obj.data.shape_keys is None or len(getattr(merged_obj.data.shape_keys, 'key_blocks', [])) == 0:
            print(f'No shapekeys found to process!')
        else:
            shapekey_offsets,shapekey_vertex_ids,shapekey_vertex_offsets_np = ShapeKeyUtils.extract_shapekey_data(merged_obj=merged_obj,index_vertex_id_dict=index_vertex_id_dict)
            # extract_shapekey_data_v2
            # shapekey_offsets,shapekey_vertex_ids,shapekey_vertex_offsets_np = ShapeKeyUtils.extract_shapekey_data_v2(mesh=mesh,index_vertex_id_dict=index_vertex_id_dict)

            self.shapekey_offsets = shapekey_offsets
            self.shapekey_vertex_ids = shapekey_vertex_ids
            self.shapekey_vertex_offsets = shapekey_vertex_offsets_np

            # 鸣潮的ShapeKey三个Buffer的导出
            if len(self.shapekey_offsets) != 0:
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyOffset.buf", 'wb') as file:
                    for number in self.shapekey_offsets:
                        # 假设数字是32位整数，使用'i'格式符
                        # 根据实际需要调整数字格式和相应的格式符
                        data = struct.pack('i', number)
                        file.write(data)
            
            if len(self.shapekey_vertex_ids) != 0:
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyVertexId.buf", 'wb') as file:
                    for number in self.shapekey_vertex_ids:
                        # 假设数字是32位整数，使用'i'格式符
                        # 根据实际需要调整数字格式和相应的格式符
                        data = struct.pack('i', number)
                        file.write(data)
            
            if len(self.shapekey_vertex_offsets) != 0:
                # 将列表转换为numpy数组，并改变其数据类型为float16
                float_array = numpy.array(self.shapekey_vertex_offsets, dtype=numpy.float32).astype(numpy.float16)
                with open(buf_output_folder + self.draw_ib + "-" + "ShapeKeyVertexOffset.buf", 'wb') as file:
                    float_array.tofile(file)

    def build_merged_object(self,extracted_object:ExtractedObject):
        '''
        extracted_object 用于读取配置
        
        这个代码有个问题就是，它只是面向一个DrawIB的，所以在调用的时候得在branch_model的drawib循环中调用，对每个drawib都生成临时obj
        然后生成mod
        '''
        print("build_merged_object::")

        # 1.Initialize components
        components = []
        for component in extracted_object.components: 
            components.append(
                MergedObjectComponent(
                    objects=[],
                    index_count=0,
                )
            )
        
        # 2.import_objects_from_collection
        # 这里是获取所有的obj，需要用咱们的方法来进行集合架构的遍历获取所有的obj
        # Nico: 添加缓存机制，一个obj只处理一次
        processed_obj_name_list:list[str] = []
        for component_model in self.component_model_list:
            for obj_data_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_data_model.obj_name
                
                # Nico: 如果已经处理过这个obj，则跳过
                if obj_name in processed_obj_name_list:
                    print(f"Skipping already processed object: {obj_name}")
                    continue

                processed_obj_name_list.append(obj_name)

                obj = bpy.data.objects.get(obj_name)
                # 跳过不满足component开头的对象

                print("obj_name: " + obj_name)
                component_count = str(component_model.component_name)[10:]
                print("ComponentCount: " + component_count)

                component_id = int(component_count) - 1 # 这里减去1是因为我们的Compoennt是从1开始的
                print("component_id: " + str(component_id))

                workspace_collection = bpy.context.collection

                # 这里我们设置collection为None，不链接到任何集合中，防止干扰
                temp_obj = ObjUtils.copy_object(bpy.context, obj, name=f'TEMP_{obj.name}', collection=workspace_collection)

                try:
                    components[component_id].objects.append(TempObject(
                        name=obj.name,
                        object=temp_obj,
                    ))
                except Exception as e:
                    print(f"Error appending object to component: {e}")

        print("准备临时对象::")
        # 3.准备临时对象
        index_offset = 0
        # 这里的component_id是从0开始的，务必注意
        for component_id, component in enumerate(components):

            component.objects.sort(key=lambda x: x.name)

            for temp_object in component.objects:
                temp_obj = temp_object.object
                print("Processing temp_obj: " + temp_obj.name)

                # Remove muted shape keys
                if Properties_WWMI.ignore_muted_shape_keys() and temp_obj.data.shape_keys:
                    print("Removing muted shape keys for object: " + temp_obj.name)
                    muted_shape_keys = []
                    for shapekey_id in range(len(temp_obj.data.shape_keys.key_blocks)):
                        shape_key = temp_obj.data.shape_keys.key_blocks[shapekey_id]
                        if shape_key.mute:
                            muted_shape_keys.append(shape_key)
                    for shape_key in muted_shape_keys:
                        print("Removing shape key: " + shape_key.name)
                        temp_obj.shape_key_remove(shape_key)

                # Apply all modifiers to temporary object
                if Properties_WWMI.apply_all_modifiers():
                    print("Applying all modifiers for object: " + temp_obj.name)
                    with OpenObject(bpy.context, temp_obj) as obj:
                        selected_modifiers = [modifier.name for modifier in get_modifiers(obj)]
                        ShapeKeyUtils.apply_modifiers_for_object_with_shape_keys(bpy.context, selected_modifiers, None)

                # Triangulate temporary object, this step is crucial as export supports only triangles
                triangulate_object(bpy.context, temp_obj)

                # Handle Vertex Groups
                vertex_groups = get_vertex_groups(temp_obj)

                # Remove ignored or unexpected vertex groups
                if Properties_WWMI.import_merged_vgmap():
                    print("Remove ignored or unexpected vertex groups for object: " + temp_obj.name)
                    # Exclude VGs with 'ignore' tag or with higher id VG count from Metadata.ini for current component
                    total_vg_count = sum([component.vg_count for component in extracted_object.components])
                    ignore_list = [vg for vg in vertex_groups if 'ignore' in vg.name.lower() or vg.index >= total_vg_count]
                else:
                    # Exclude VGs with 'ignore' tag or with higher id VG count from Metadata.ini for current component
                    extracted_component = extracted_object.components[component_id]
                    total_vg_count = len(extracted_component.vg_map)
                    ignore_list = [vg for vg in vertex_groups if 'ignore' in vg.name.lower() or vg.index >= total_vg_count]
                remove_vertex_groups(temp_obj, ignore_list)

                # Rename VGs to their indicies to merge ones of different components together
                for vg in get_vertex_groups(temp_obj):
                    vg.name = str(vg.index)

                # Calculate vertex count of temporary object
                temp_object.vertex_count = len(temp_obj.data.vertices)
                # Calculate index count of temporary object, IB stores 3 indices per triangle
                temp_object.index_count = len(temp_obj.data.polygons) * 3
                # Set index offset of temporary object to global index_offset
                temp_object.index_offset = index_offset
                # Update global index_offset
                index_offset += temp_object.index_count
                # Update vertex and index count of custom component
                component.vertex_count += temp_object.vertex_count
                component.index_count += temp_object.index_count

        # build_merged_object:

        merged_object = []
        vertex_count, index_count = 0, 0
        for component in components:
            for temp_object in component.objects:
                merged_object.append(temp_object.object)
            vertex_count += component.vertex_count
            index_count += component.index_count
            
        join_objects(bpy.context, merged_object)

        obj = merged_object[0]

        rename_object(obj, 'TEMP_EXPORT_OBJECT')

        deselect_all_objects()
        select_object(obj)
        set_active_object(bpy.context, obj)

        mesh = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()

        merged_object = MergedObject(
            object=obj,
            mesh=mesh,
            components=components,
            vertex_count=len(obj.data.vertices),
            index_count=len(obj.data.polygons) * 3,
            vg_count=len(get_vertex_groups(obj)),
            shapekeys=MergedObjectShapeKeys(),
        )

        if vertex_count != merged_object.vertex_count:
            raise ValueError('vertex_count mismatch between merged object and its components')

        if index_count != merged_object.index_count:
            raise ValueError('index_count mismatch between merged object and its components')
        
        LOG.newline()
        return merged_object