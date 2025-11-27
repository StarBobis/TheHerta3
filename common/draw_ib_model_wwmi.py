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
        
        # (8) 单独拿出来,方便使用
        merged_obj = self.merged_object.object

        TimerUtils.Start("Obj To Buffer")
        obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11GameType, obj_name=merged_obj.name)

        if getattr(self, 'blend_remap_maps', None):
            self.apply_blendindex_remap(obj_element_model)
        else:
            print("No blend_remap_maps found, skipping BLENDINDICES remap.")

        # Now that any external changes (e.g. remap) have been applied to
        # `elementname_data_dict`, pack into the structured ndarray.
        try:
            obj_element_model.fill_into_element_vertex_ndarray()
        except Exception as e:
            print(f"Failed to pack element arrays into structured ndarray: {e}")

        self.obj_buffer_model_wwmi = ObjBufferModelWWMI(obj_element_model=obj_element_model)
        TimerUtils.End("Obj To Buffer")

        # Write BlendRemapVertexVG aligned to ObjBufferModelWWMI's unique vertex ordering.
        # Build per-unique-vertex VG id array using index_vertex_id_dict (maps unique_index -> original_vertex_id).
        try:
            index_vertex_id_dict = self.obj_buffer_model_wwmi.index_vertex_id_dict
            if index_vertex_id_dict is not None:
                blendindices_element = self.d3d11GameType.ElementNameD3D11ElementDict["BLENDINDICES"]
                num_vgs = 4
                if blendindices_element.Format == "R8_UINT":
                    num_vgs = blendindices_element.ByteWidth

                unique_count = len(index_vertex_id_dict)
                vg_array = numpy.zeros((unique_count, num_vgs), dtype=numpy.uint16)

                # Prepare mapping vertex -> first loop index so we can sample per-loop pre-remap BLENDINDICES
                mesh = self.obj_buffer_model_wwmi.mesh
                try:
                    n_loops = len(mesh.loops)
                    loop_vertex_indices = numpy.empty(n_loops, dtype=int)
                    mesh.loops.foreach_get("vertex_index", loop_vertex_indices)
                except Exception:
                    loop_vertex_indices = None

                vertex_to_first_loop = {}
                if loop_vertex_indices is not None:
                    for li, vid in enumerate(loop_vertex_indices.tolist()):
                        if int(vid) not in vertex_to_first_loop:
                            vertex_to_first_loop[int(vid)] = li

                # For each unique index (0..unique_count-1), get original vertex id and read its pre-remap BLENDINDICES
                # Compute original per-loop BLENDINDICES source on demand (no long-lived copy)
                if hasattr(obj_element_model, 'elementname_data_dict') and 'BLENDINDICES' in obj_element_model.elementname_data_dict and obj_element_model.elementname_data_dict['BLENDINDICES'] is not None:
                    _pre_blend = obj_element_model.elementname_data_dict['BLENDINDICES']
                else:
                    _pre_blend = None

                for uniq_idx in range(unique_count):
                    orig_vid = index_vertex_id_dict.get(uniq_idx, None)
                    if orig_vid is None:
                        continue

                    written = False
                    # Prefer pre-remap BLENDINDICES sampled at a representative loop for this vertex
                    if _pre_blend is not None and vertex_to_first_loop:
                        loop_idx = vertex_to_first_loop.get(int(orig_vid), None)
                        if loop_idx is not None and loop_idx < len(_pre_blend):
                            # _pre_blend may be 1D or 2D
                            if getattr(_pre_blend, 'ndim', 1) == 1:
                                vg_array[uniq_idx, 0] = int(_pre_blend[loop_idx])
                                written = True
                            else:
                                vals = _pre_blend[loop_idx]
                                for i in range(min(num_vgs, len(vals))):
                                    vg_array[uniq_idx, i] = int(vals[i])
                                written = True

                    if written:
                        continue

                    # Fallback: sample vertex groups from merged object
                    try:
                        v = self.merged_object.object.data.vertices[int(orig_vid)]
                        groups = [(g.group, g.weight) for g in v.groups]
                        if groups:
                            groups.sort(key=lambda x: x[1], reverse=True)
                            for i, (gidx, w) in enumerate(groups[:num_vgs]):
                                vg_array[uniq_idx, i] = int(gidx)
                    except Exception:
                        # leave zeros
                        pass

                # Flatten and write as uint16
                ObjWriter.write_buf_blendindices_uint16(vg_array, self.draw_ib + "-BlendRemapVertexVG.buf")
        except Exception as e:
            print(f"Failed to write BlendRemapVertexVG aligned file: {e}")

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
        output_dir = GlobalConfig.path_generatemod_buffer_folder()
        
        num_vgs = 4
        blendindices_element = self.d3d11GameType.ElementNameD3D11ElementDict["BLENDINDICES"]
        if blendindices_element.Format == "R8_UINT":
            num_vgs = blendindices_element.ByteWidth

        blend_remap_forward = numpy.empty(0, dtype=numpy.uint16)
        blend_remap_reverse = numpy.empty(0, dtype=numpy.uint16)
        remapped_vgs_counts = []

        # Per-component remap maps: { component_name: { 'forward': [orig_vg_ids], 'reverse': {orig->local} } }
        remap_maps: dict[str, dict] = {}
        # Per-component boolean indicating whether remap was used for that component
        remap_used: dict[str, bool] = {}

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
            if len(used_vg_set) == 0 or (max(used_vg_set) if len(used_vg_set) else 0) < 256:
                # No remapping required for this component
                remapped_vgs_counts.append(0)
                remap_maps[comp_obj.name] = { 'forward': [], 'reverse': {} }
                remap_used[comp_obj.name] = False
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

 

    def apply_blendindex_remap(self, obj_element_model: ObjElementModel):
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
        # Do NOT mutate the original parsed arrays. Place remapped array into
        # `final_elementname_data_dict` so callers may later call
        # `fill_into_element_vertex_ndarray()` to pack using remapped values.
        if not hasattr(obj_element_model, 'final_elementname_data_dict') or obj_element_model.final_elementname_data_dict is None:
            obj_element_model.final_elementname_data_dict = {}

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


