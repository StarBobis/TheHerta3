import struct
import numpy
import os


from dataclasses import dataclass, field

from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import *
from ..utils.timer_utils import TimerUtils
from ..config.main_config import *
# removed unused imports: json utils, timer utilities and Fatal formatter
from ..utils.obj_utils import *
from ..utils.shapekey_utils import ShapeKeyUtils
from ..utils.log_utils import LOG

from .extracted_object import ExtractedObject, ExtractedObjectHelper
from ..base.obj_data_model import ObjDataModel
from ..base.component_model import ComponentModel
from ..base.d3d11_gametype import D3D11GameType
from ..base.m_draw_indexed import M_DrawIndexed

from ..config.properties_wwmi import Properties_WWMI
from ..config.import_config import ImportConfig

from .obj_element_model import ObjElementModel
from .obj_buffer_model_wwmi import ObjBufferModelWWMI
from .branch_model import BranchModel
from .obj_writer import ObjWriter



@dataclass
class DrawIBModelWWMI:
    '''
    这个代表了一个DrawIB的Mod导出模型
    Mod导出可以调用这个模型来进行业务逻辑部分
    每个游戏的DrawIBModel都是不同的，但是一部分是可以复用的
    (例如WWMI就有自己的一套DrawIBModel) 

    TODO 仍然有问题未解决

    1.使用ReMap技术时，Blend.buf中的顶点索引要替换为局部索引。
    2.使用ReMap技术时，生成的BlendRemapVertexVG.buf大小应该是和Blend.buf大小相同的。
    3.生成的Mod的大小不同，尤其是在使用了Remap技术时，Blend.buf的大小和WWMI-Tools明显不一致。
    4.生成的Mod光照不一致

    在当前架构下，要替换最终生成的Blend.buf中的BLENDINDICES的内容十分困难
    在此之前必须解决我们生成的Blend.buf和WWMI-Tools生成的Blend.buf大小不一致的问题
    否则就无法进行测试对比
    这侧面反应了我们的架构设计是不合理的，因为不能随意做到修改局部以及整体的每一处细节数据

    '''
    draw_ib: str
    branch_model: BranchModel

    draw_ib_alias: str = field(init=False)
    # ImportConfig 需要传入 draw_ib 参数，因此不要在这里用 default_factory 自动实例化
    import_config: ImportConfig = field(init=False)
    d3d11GameType: D3D11GameType = field(init=False)
    extracted_object: ExtractedObject = field(init=False)

    # 仅类的内部使用
    _component_model_list: list[ObjDataModel] = field(init=False,default_factory=list)
    
    component_name_component_model_dict: dict[str, ComponentModel] = field(init=False,default_factory=dict)

    # 每个DrawIB都有总的顶点数，对应CategoryBuffer里的顶点数。
    mesh_vertex_count:int = field(init=False,default=0)

    merged_object:MergedObject = field(init=False)
    obj_name_drawindexed_dict:dict[str,M_DrawIndexed] = field(init=False,default_factory=dict)

    blend_remap:bool = field(init=False,default=False)
    # NOTE: local remap rows are computed during export but not persisted on the instance
    
    obj_buffer_model_wwmi:ObjBufferModelWWMI = field(init=False,default=False)

    def __post_init__(self):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib_alias = draw_ib_alias_name_dict.get(self.draw_ib,self.draw_ib)
        # (2) 读取工作空间中配置文件的配置项
        self.import_config = ImportConfig(draw_ib=self.draw_ib)
        self.d3d11GameType:D3D11GameType = self.import_config.d3d11GameType
        # 读取WWMI专属配置
        self.extracted_object:ExtractedObject = ExtractedObjectHelper.read_metadata(GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=self.d3d11GameType.GameTypeName)  + "Metadata.json")

        '''
        这里是要得到每个Component对应的obj_data_model列表
        '''
        self.ordered_obj_data_model_list:list[ObjDataModel] = self.branch_model.get_obj_data_model_list_by_draw_ib(draw_ib=self.draw_ib)
        
        # (3) 组装成特定格式？
        self._component_model_list:list[ComponentModel] = []
        self.component_name_component_model_dict:dict[str,ComponentModel] = {}

        for part_name in self.import_config.part_name_list:
            print("part_name: " + part_name)
            component_obj_data_model_list = []
            for obj_data_model in self.ordered_obj_data_model_list:
                if part_name == str(obj_data_model.component_count):
                    component_obj_data_model_list.append(obj_data_model)
                    print("obj_data_model: " + obj_data_model.obj_name)

            component_model = ComponentModel(component_name="Component " + part_name,final_ordered_draw_obj_model_list=component_obj_data_model_list)
            
            self._component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = component_model
        LOG.newline()

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
        for component_model in self._component_model_list:
            new_ordered_obj_model_list = []
            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_model.drawindexed_obj = self.obj_name_drawindexed_dict[obj_model.obj_name]
                new_ordered_obj_model_list.append(obj_model)
            component_model.final_ordered_draw_obj_model_list = new_ordered_obj_model_list
            self.component_name_component_model_dict[component_model.component_name] = component_model
        
        # (8) 选中当前融合的obj对象，计算得到ib和category_buffer，以及每个IndexId对应的VertexId
        merged_obj = self.merged_object.object

        # 构建ObjBufferModel
        TimerUtils.Start("ObjElementModel")
        obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11GameType,obj_name=merged_obj.name)
        TimerUtils.End("ObjElementModel")

        TimerUtils.Start("ObjBufferModelWWMI")
        self.obj_buffer_model_wwmi = ObjBufferModelWWMI(obj_element_model=obj_element_model)
        TimerUtils.End("ObjBufferModelWWMI")

        # 写出Index.buf
        ObjWriter.write_buf_ib_r32_uint(self.obj_buffer_model_wwmi.ib,self.draw_ib + "-Component1.buf")

        # 传入 index_vertex_id_dict 以便在需要 remap 时能够知道每个唯一顶点对应的原始顶点 id
        self.write_out_category_buffer(category_buffer_dict=self.obj_buffer_model_wwmi.category_buffer_dict)
        
        # 写出ShapeKey相关Buffer文件
        if self.obj_buffer_model_wwmi.export_shapekey:
            ObjWriter.write_buf_shapekey_offsets(self.obj_buffer_model_wwmi.shapekey_offsets,self.draw_ib + "-" + "ShapeKeyOffset.buf")
            ObjWriter.write_buf_shapekey_vertex_ids(self.obj_buffer_model_wwmi.shapekey_vertex_ids,self.draw_ib + "-" + "ShapeKeyVertexId.buf")
            ObjWriter.write_buf_shapekey_vertex_offsets(self.obj_buffer_model_wwmi.shapekey_vertex_offsets,self.draw_ib + "-" + "ShapeKeyVertexOffset.buf")

        # 删除临时融合的obj对象
        bpy.data.objects.remove(merged_obj, do_unlink=True)


    def export_blendremap_forward_and_reverse(self, components_objs):
        '''
        TODO 完善代码，仿照项目中references目录下的WWMI-Tools下所有代码里的生成如下文件的逻辑
        BlendRemapForward.buf
        BlendRemapReverse.buf
        BlendRemapVertexVG.buf
        来生成这几个文件，要求和WWMI-Tools生成的一模一样，你可以随便抄WWMI-Tools的代码
        要求代码全部在此方法中完成，生成文件的目录在output_dir
        你可以任意翻看所有的代码文件
        '''
        output_dir = GlobalConfig.path_generatemod_buffer_folder()
        
        # Number of vertex-group slots per-vertex used by WWMI Blend layout (usually 4)

        blendindices_element = self.d3d11GameType.ElementNameD3D11ElementDict["BLENDINDICES"]
        
        # 一般情况下使用ReMap的话，这里都是8
        num_vgs = 4
        if blendindices_element.Format == "R8_UINT" and blendindices_element.ByteWidth == 8:
            num_vgs = 8

        blend_remap_forward = numpy.empty(0, dtype=numpy.uint16)
        blend_remap_reverse = numpy.empty(0, dtype=numpy.uint16)
        remapped_vgs_counts = []

        # Collect per-vertex VG ids for the whole drawib (flattened as uint16)
        all_vg_ids = []

        for comp_obj in components_objs:
            # Ensure we have the evaluated mesh/obj available
            obj = comp_obj

            # Build per-vertex VG id array for this component
            vert_vg_ids = numpy.zeros((len(obj.data.vertices), num_vgs), dtype=numpy.uint16)

            # For remap calculation collect used VG ids for vertices referenced by this component
            used_vg_set = set()

            for vi, v in enumerate(obj.data.vertices):
                # vertex.groups is a sequence of group assignments (group index, weight)
                groups = [(g.group, g.weight) for g in v.groups]
                # sort by weight descending and keep top `num_vgs`
                if len(groups) > 0:
                    groups.sort(key=lambda x: x[1], reverse=True)
                    for i, (gidx, w) in enumerate(groups[:num_vgs]):
                        vert_vg_ids[vi, i] = int(gidx)
                        if w > 0:
                            used_vg_set.add(int(gidx))

            # Append this component's per-vertex VG ids to global list (flatten row-major)
            all_vg_ids.append(vert_vg_ids.ravel())

            # Determine whether remapping is needed for this component
            if len(used_vg_set) == 0 or (max(used_vg_set) if len(used_vg_set) else 0) < 256:
                # No remapping required for this component
                remapped_vgs_counts.append(0)
                continue

            # Create forward and reverse remap arrays (512 entries each, uint16)
            obj_vg_ids = numpy.array(sorted(used_vg_set), dtype=numpy.uint16)

            forward = numpy.zeros(512, dtype=numpy.uint16)
            forward[:len(obj_vg_ids)] = obj_vg_ids

            reverse = numpy.zeros(512, dtype=numpy.uint16)
            # reverse maps original vg id -> compact id (index in obj_vg_ids)
            reverse[obj_vg_ids] = numpy.arange(len(obj_vg_ids), dtype=numpy.uint16)

            blend_remap_forward = numpy.concatenate((blend_remap_forward, forward), axis=0)
            blend_remap_reverse = numpy.concatenate((blend_remap_reverse, reverse), axis=0)
            remapped_vgs_counts.append(len(obj_vg_ids))

        # If there are per-component VG arrays, concatenate into single array
        if len(all_vg_ids) > 0:
            vg_concat = numpy.concatenate(all_vg_ids).astype(numpy.uint16)
        else:
            vg_concat = numpy.empty(0, dtype=numpy.uint16)

        # Write files if there is data
        try:
            if blend_remap_forward.size != 0:
                with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapForward.buf"), 'wb') as f:
                    blend_remap_forward.tofile(f)

            if blend_remap_reverse.size != 0:
                with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapReverse.buf"), 'wb') as f:
                    blend_remap_reverse.tofile(f)

            # BlendRemapVertexVG: per-vertex VG ids flattened (uint16)
            with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapVertexVG.buf"), 'wb') as f:
                vg_concat.tofile(f)

            # Optionally write a layout buffer (counts per component) matching WWMI-Tools naming
            if len(remapped_vgs_counts) > 0:
                layout_arr = numpy.array(remapped_vgs_counts, dtype=numpy.uint32)
                with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapLayout.buf"), 'wb') as f:
                    layout_arr.tofile(f)

        except Exception as e:
            print(f"Failed to write BlendRemap files: {e}")




    def write_out_category_buffer(self, category_buffer_dict):
        __categoryname_bytelist_dict = {}
        for category_name in self.d3d11GameType.OrderedCategoryNameList:
            if category_name not in __categoryname_bytelist_dict:
                __categoryname_bytelist_dict[category_name] = category_buffer_dict[category_name]
            else:
                existing_array = __categoryname_bytelist_dict[category_name]
                buffer_array = category_buffer_dict[category_name]

                existing_array = numpy.asarray(existing_array)
                buffer_array = numpy.asarray(buffer_array)

                concatenated_array = numpy.concatenate((existing_array, buffer_array))
                __categoryname_bytelist_dict[category_name] = concatenated_array

        position_stride = self.d3d11GameType.CategoryStrideDict["Position"]
        position_bytelength = len(__categoryname_bytelist_dict["Position"])
        self.mesh_vertex_count = int(position_bytelength / position_stride)

        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()

        for category_name, category_buf in __categoryname_bytelist_dict.items():
            buf_path = buf_output_folder + self.draw_ib + "-" + category_name + ".buf"
            with open(buf_path, 'wb') as ibf:
                category_buf.tofile(ibf)


            


    def build_merged_object(self,extracted_object:ExtractedObject):
        '''
        extracted_object 用于读取配置
        
        此方法用于为当前DrawIB构建MergedObj对象
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
        workspace_collection = bpy.context.collection

        processed_obj_name_list:list[str] = []
        for component_model in self._component_model_list:
            component_count = str(component_model.component_name)[10:]
            print("ComponentCount: " + component_count)

            # 这里减去1是因为我们的Compoennt是从1开始的,但是WWMITools的逻辑是从0开始的
            component_id = int(component_count) - 1 
            print("component_id: " + str(component_id))
            
            for obj_data_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_data_model.obj_name
                print("obj_name: " + obj_name)
                
                # Nico: 如果已经处理过这个obj，则跳过
                if obj_name in processed_obj_name_list:
                    print(f"Skipping already processed object: {obj_name}")
                    continue
                processed_obj_name_list.append(obj_name)

                obj = ObjUtils.get_obj_by_name(obj_name)

                # 复制出一个TEMP_为前缀的obj出来
                # 这里我们设置collection为None，不链接到任何集合中，防止干扰
                temp_obj = ObjUtils.copy_object(bpy.context, obj, name=f'TEMP_{obj.name}', collection=workspace_collection)

                # 添加到当前component的objects列表中，添加的是复制出来的TEMP_的obj
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
            
            # 排序以确保obj的命名符合规范而不是根据集合中的位置来进行
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
                ObjUtils.triangulate_object(bpy.context, temp_obj)

                # Handle Vertex Groups
                vertex_groups = ObjUtils.get_vertex_groups(temp_obj)

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
                for vg in ObjUtils.get_vertex_groups(temp_obj):
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
        drawib_merged_object = []
        drawib_vertex_count, drawib_index_count = 0, 0

        component_obj_list = []
        for component in components:
            
            component_merged_object:list[bpy.types.Object] = []

            # for temp_object in component.objects:
            #     drawib_merged_object.append(temp_object.object)
            # 改为先把component的obj组合在一起，得到当前component的obj
            # 然后就能获取每个component是否使用remap技术的信息了
            # 然后最后再融合到drawib级别的mergedobj中，也不影响最终结果
            for temp_object in component.objects:
                component_merged_object.append(temp_object.object)

            ObjUtils.join_objects(bpy.context, component_merged_object)

            component_obj = component_merged_object[0]
            component_obj_list.append(component_obj)
            
            drawib_merged_object.append(component_obj)

            drawib_vertex_count += component.vertex_count
            drawib_index_count += component.index_count
        
        # 获取到component_obj_list后，直接就能导出BlendRemap的Forward和Reverse了
        self.export_blendremap_forward_and_reverse(component_obj_list)

        ObjUtils.join_objects(bpy.context, drawib_merged_object)

        obj = drawib_merged_object[0]

        ObjUtils.rename_object(obj, 'TEMP_EXPORT_OBJECT')

        deselect_all_objects()
        select_object(obj)
        set_active_object(bpy.context, obj)

        mesh = ObjUtils.get_mesh_evaluate_from_obj(obj)

        drawib_merged_object = MergedObject(
            object=obj,
            mesh=mesh,
            components=components,
            vertex_count=len(obj.data.vertices),
            index_count=len(obj.data.polygons) * 3,
            vg_count=len(ObjUtils.get_vertex_groups(obj)),
            shapekeys=MergedObjectShapeKeys(),
        )

        if drawib_vertex_count != drawib_merged_object.vertex_count:
            raise ValueError('vertex_count mismatch between merged object and its components')

        if drawib_index_count != drawib_merged_object.index_count:
            raise ValueError('index_count mismatch between merged object and its components')
        
        LOG.newline()
        return drawib_merged_object


