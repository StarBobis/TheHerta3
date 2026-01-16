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
from ..utils.vertexgroup_utils import VertexGroupUtils
from ..utils.format_utils import FormatUtils

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

    # 是否启用Blend Remap技术
    blend_remap:bool = field(init=False,default=False)
    
    obj_buffer_model_wwmi:ObjBufferModelWWMI = field(init=False,default=False)
    
    blend_remap_maps:dict = field(init=False,default_factory=dict)
    # Per-component boolean: component name -> whether that component uses remap
    blend_remap_used: dict = field(init=False, default_factory=dict)

    # 存储每个Component实际使用的顶点组数量（排除空顶点组后）
    component_real_vg_count_dict: dict[int, int] = field(init=False, default_factory=dict)

    def __post_init__(self):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib_alias = draw_ib_alias_name_dict.get(self.draw_ib,self.draw_ib)
        # (2) 读取工作空间中配置文件的配置项
        self.import_config = ImportConfig(draw_ib=self.draw_ib)
        self.d3d11GameType:D3D11GameType = self.import_config.d3d11GameType
        
        # 读取WWMI专属配置
        self.extracted_object:ExtractedObject = ExtractedObjectHelper.read_metadata(GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=self.d3d11GameType.GameTypeName)  + "Metadata.json")

        # 这里是要得到每个Component对应的obj_data_model列表
        self.ordered_obj_data_model_list:list[ObjDataModel] = self.branch_model.get_obj_data_model_list_by_draw_ib(draw_ib=self.draw_ib)
        
        # (3) 组装成特定格式
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
        
        # 创建obj_element_model
        obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11GameType, obj_name=self.merged_object.object.name)

        # 如果使用了remap技术则替换Remap
        if self.blend_remap:
            self.replace_remapped_blendindices(obj_element_model)

        # 上面替换完了remap这里才填充为最终的ndarray
        obj_element_model.fill_into_element_vertex_ndarray()

        # 然后才能创建ObjBufferModelWWMI
        self.obj_buffer_model_wwmi = ObjBufferModelWWMI(obj_element_model=obj_element_model)

        if self.blend_remap:
            # 写出原始未经任何改动的BLENDINDICES到BlendRemapVertexVG.buf, 格式为uint16_t
            index_vertex_id_dict = self.obj_buffer_model_wwmi.index_vertex_id_dict
            # 获取真实的VG通道数量
            num_vgs = self.d3d11GameType.get_blendindices_count_wwmi()

            # 初始化数组
            vg_array = numpy.zeros((len(index_vertex_id_dict), num_vgs), dtype=numpy.uint16)

            # Reconstruct per-unique-row original (pre-remap) BLENDINDICES by
            # sampling `obj_element_model.original_elementname_data_dict['BLENDINDICES']`
            # at the same loop indices used by ObjBufferModelWWMI when it built
            # `unique_element_vertex_ndarray`.
            # Strict path: require `unique_first_loop_indices` and original parsed BLENDINDICES.
            # If either is missing, skip writing the aligned BlendRemapVertexVG file and log a warning.
            original_blendindices = obj_element_model.original_elementname_data_dict['BLENDINDICES']
            sampled_blendindices = original_blendindices[self.obj_buffer_model_wwmi.unique_first_loop_indices]
            # Always treat sampled_blendindices as 2D (channels in axis=1).
            # If it's 1D (single channel), reshape to (N,1) so the same loop works.
            if getattr(sampled_blendindices, 'ndim', 1) == 1:
                sampled_blendindices = sampled_blendindices.reshape(-1, 1)
            for i in range(min(num_vgs, sampled_blendindices.shape[1])):
                vg_array[:, i] = sampled_blendindices[:, i].astype(numpy.uint16)
            # 写出到文件
            ObjWriter.write_buf_blendindices_uint16(vg_array, self.draw_ib + "-BlendRemapVertexVG.buf")

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
        bpy.data.objects.remove(self.merged_object.object, do_unlink=True)


    def export_blendremap_forward_and_reverse(self, components_objs):
        output_dir = GlobalConfig.path_generatemod_buffer_folder()
        
        # Determine number of VG channels from game type
        num_vgs = self.d3d11GameType.get_blendindices_count_wwmi()

        blend_remap_forward = numpy.empty(0, dtype=numpy.uint16)
        blend_remap_reverse = numpy.empty(0, dtype=numpy.uint16)
        remapped_vgs_counts = []

        # Per-component remap maps: { component_name: { 'forward': [orig_vg_ids], 'reverse': {orig->local} } }
        remap_maps: dict[str, dict] = {}
        # Per-component boolean indicating whether remap was used for that component
        remap_used: dict[str, bool] = {}

        any_overflow = False

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

            # Determine whether remapping is needed for this component
            max_used = (max(used_vg_set) if len(used_vg_set) else 0)
            if len(used_vg_set) == 0 or max_used < 256:
                # No remapping required for this component
                remapped_vgs_counts.append(0)
                remap_maps[comp_obj.name] = { 'forward': [], 'reverse': {} }
                remap_used[comp_obj.name] = False
                continue
            else:
                any_overflow = True

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
            # build simple python mapping structures for later remap usage
            forward_list = [int(x) for x in obj_vg_ids.tolist()]
            reverse_map = { int(v): int(i) for i, v in enumerate(forward_list) }
            remap_maps[comp_obj.name] = { 'forward': forward_list, 'reverse': reverse_map }
            remap_used[comp_obj.name] = True

        if blend_remap_forward.size != 0:
            with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapForward.buf"), 'wb') as f:
                blend_remap_forward.tofile(f)

        if blend_remap_reverse.size != 0:
            with open(os.path.join(output_dir, f"{self.draw_ib}-BlendRemapReverse.buf"), 'wb') as f:
                blend_remap_reverse.tofile(f)

        # Expose the remap maps on the instance for later use (original vg id -> local compact id)
        self.blend_remap_maps = remap_maps
        # also expose which components actually used remapping
        self.blend_remap_used = remap_used

        # If any component used VG ids >= 256, enable global blend_remap
        if any_overflow:
            self.blend_remap = True

 

    def replace_remapped_blendindices(self, obj_element_model: ObjElementModel):
        """
        使用已经生成的 self.blend_remap_maps 将 obj_element_model.element_vertex_ndarray['BLENDINDICES']
        中的全局顶点组索引替换为对应 component 的局部（compact）索引。

        过程：
        - 构建 loop -> polygon 的映射
        - 构建 polygon -> 原始 component object name 的映射（使用 components[*].objects[*].index_offset 和 index_count）
        - 对每个 loop 的 BLENDINDICES 条目，使用对应 component 的 reverse 映射表进行替换
        """
        import numpy as _np

        if not hasattr(self, 'blend_remap_maps') or not self.blend_remap_maps:
            return

        # We prefer to operate on the parsed per-element arrays stored in
        # `original_elementname_data_dict` and write remapped results into
        # `final_elementname_data_dict`. This avoids mutating the original
        # parsed arrays and defers packing until callers call
        # `fill_into_element_vertex_ndarray()`.

        mesh = obj_element_model.mesh
        loops_len = obj_element_model.mesh_loops_length

        # Build loop -> polygon mapping
        loop_to_poly = _np.empty(loops_len, dtype=_np.int32)
        for poly in mesh.polygons:
            start = poly.loop_start
            end = start + poly.loop_total
            loop_to_poly[start:end] = poly.index

        arr = None
        # Source array: original parsed dict if present
        if 'BLENDINDICES' in getattr(obj_element_model, 'original_elementname_data_dict', {}):
            # copy to avoid mutating the original
            src = obj_element_model.original_elementname_data_dict['BLENDINDICES']
            arr = src.copy()
        elif hasattr(obj_element_model, 'element_vertex_ndarray') and 'BLENDINDICES' in obj_element_model.element_vertex_ndarray.dtype.names:
            # If the caller has already packed, take a copy of the packed ndarray
            arr = obj_element_model.element_vertex_ndarray['BLENDINDICES'].copy()

        if arr is None:
            # Nothing to remap
            return

        # 2) polygon -> component object name mapping
        poly_count = len(mesh.polygons)
        polygon_to_objname = [None] * poly_count

        for comp in self.merged_object.components:
            for temp_obj in comp.objects:
                if not hasattr(temp_obj, 'index_offset') or not hasattr(temp_obj, 'index_count'):
                    continue
                poly_start = int(temp_obj.index_offset // 3)
                poly_end = poly_start + int(temp_obj.index_count // 3)
                for p in range(poly_start, poly_end):
                    if 0 <= p < poly_count:
                        polygon_to_objname[p] = temp_obj.name

        # Determine width (number of indices per entry)
        if getattr(arr, 'ndim', 1) == 1:
            width = 1
        else:
            width = arr.shape[1]

        for li in range(loops_len):
            poly_idx = int(loop_to_poly[li])
            comp_obj_name = polygon_to_objname[poly_idx] if (0 <= poly_idx < len(polygon_to_objname)) else None
            if not comp_obj_name:
                continue
            remap_entry = self.blend_remap_maps.get(comp_obj_name, None)
            if not remap_entry:
                continue
            reverse_map = remap_entry.get('reverse', {})

            if width == 1:
                orig = int(arr[li])
                new = reverse_map.get(orig, orig)
                arr[li] = new
            else:
                for j in range(width):
                    orig = int(arr[li, j])
                    new = reverse_map.get(orig, orig)
                    arr[li, j] = new

        obj_element_model.final_elementname_data_dict['BLENDINDICES'] = arr

        print("Applied BLENDINDICES remap and wrote results into final_elementname_data_dict")
 



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
        print("\n====== CHECK 1 / Component 初始化 ======")
        for i, comp in enumerate(extracted_object.components):
            print(f"Metadata Component[{i}] 期望 vg_count = {comp.vg_count}")
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

            print(f"\n====== CHECK 2 / COMPONENT {component_id} → {component_model.component_name} ======")
            print("预期 Obj 列表长度 =", len(component_model.final_ordered_draw_obj_model_list))
            for o in component_model.final_ordered_draw_obj_model_list:
                print("  OBJ:", o.obj_name, "存在？", bpy.data.objects.get(o.obj_name) is not None)
            
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
        # Nico: 修复VGCount不准确的问题
        # 如果使用了REMAP技术，或者发生了顶点组合并现象，也就是把其他的Component合并到这个Component上了
        # 就会导致这里的获取的原始的顶点组数量对不上
        # 一般情况下会小于真实的顶点组数量
        # 所以这里的值需要更新为，每个Compoennt实际使用到的顶点组的数量
        # 所以就需要提前记录所有的Component真实的VGCount，且是排除了空顶点组之后的
        self.component_real_vg_count_dict = {}
        # for component_id, component in enumerate(components):
        #     print("component_id" + str(component_id))
        #     max_vg_count = 0
        #     for temp_object in component.objects:
        #         temp_obj = temp_object.object
                
        #         # 计算实际使用的顶点组数量（排除空顶点组）
        #         # 注意：不能直接修改temp_obj，所以不能用VertexGroupUtils.remove_unused_vertex_groups
        #         used_vg_indices = set()
        #         for v in temp_obj.data.vertices:
        #             for g in v.groups:
        #                 if g.weight > 0.0:
        #                     used_vg_indices.add(g.group)
        #         real_vg_count = len(used_vg_indices)
        #         print(f"Object {temp_obj.name} 真实 vg_count = {real_vg_count}")
        #         if real_vg_count > max_vg_count:
        #             max_vg_count = real_vg_count
        #     print(f"Component {component_id} 真实 vg_count = {max_vg_count}")
        #     self.component_real_vg_count_dict[component_id] = max_vg_count
        #     print(f"Calculated real vg_count for Component {component_id}: {max_vg_count}")

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
        
        print("\n====== CHECK 3 / 对象收集结果 ======")
        for i, comp in enumerate(components):
            print(f"Component[{i}] 对象数 = {len(comp.objects)}")
            if len(comp.objects) == 0:
                print("⚠ 警告：Component[{0}] 没有任何对象，将在合并时跳过。".format(i))

        for component_index, component in enumerate(components):
            # 把每个 component 里所有临时物体收集到一个列表
            component_merged_object: list[bpy.types.Object] = [
                temp_object.object for temp_object in component.objects
            ]

            print("\n====== CHECK 4 / JOIN 前汇总 ======")
            print(f"➡ Component[{component_index}] 物体数 = {len(component_merged_object)}")
            print("内容：", [o.name for o in component_merged_object])

            # ⭐ 关键：如果这个 component 本身就没有任何几何，直接跳过
            if len(component_merged_object) == 0:
                print(f"⚠ Component[{component_index}] 无几何体，跳过 join。")
                # 同时它对全局顶点数 / 索引数也是 0，不需要手动加减
                continue

            # 非空的才真正 merge
            ObjUtils.join_objects(bpy.context, component_merged_object)

            component_obj = component_merged_object[0]

            # 鸣潮导出时整体预处理，比直接操作Buffer文件中的内容方便且规范
            if GlobalConfig.logic_name == LogicName.WWMI:
                ObjUtils.select_obj(component_obj)

                # 鸣潮需要把旋转角度清零
                component_obj.rotation_euler[0] = 0
                component_obj.rotation_euler[1] = 0
                component_obj.rotation_euler[2] = math.radians(180)

                # 鸣潮导出时放大100倍
                component_obj.scale = (100,100,100)
                
                # 应用旋转和缩放
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

            # 如果导入时勾选了忽略空顶点组
            # 那么导出时就得按顺序排列并且添加回来那些空的顶点组以确保不会出问题
            if Properties_WWMI.export_add_missing_vertex_groups():
                ObjUtils.select_obj(component_obj)
                VertexGroupUtils.merge_vertex_groups_with_same_number()
                VertexGroupUtils.fill_vertex_group_gaps()
                component_obj.select_set(False)

            component_obj_list.append(component_obj)
            drawib_merged_object.append(component_obj)

            # Nico: 修复VGCount不准确的问题
            # 此时已经合并了所有的obj，所以可以直接计算真实的VGCount
            used_vg_indices = set()
            for v in component_obj.data.vertices:
                for g in v.groups:
                    if g.weight > 0.0:
                        used_vg_indices.add(g.group)
            real_vg_count = len(used_vg_indices)
            self.component_real_vg_count_dict[component_index] = real_vg_count
            print(f"Calculated real vg_count for Component {component_index}: {real_vg_count}")
            
            # 注意这里 component.vertex_count / index_count 已经在前面统计过
            drawib_vertex_count += component.vertex_count
            drawib_index_count += component.index_count

        # 获取到 component_obj_list 后，导出 BlendRemap forward/reverse
        self.export_blendremap_forward_and_reverse(component_obj_list)

        # 确保选中第一个，否则join_objects会报错
        if drawib_merged_object:
            bpy.ops.object.select_all(action='DESELECT')
            target_active = drawib_merged_object[0]
            target_active.select_set(True)
            bpy.context.view_layer.objects.active = target_active


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


