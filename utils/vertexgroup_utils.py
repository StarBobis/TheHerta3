import bpy
import itertools
import numpy
import math

from mathutils import Vector,Matrix

from .format_utils import Fatal


class VertexGroupUtils:
    @classmethod
    def remove_unused_vertex_groups(cls,obj):
        '''
        移除给定obj的未使用的顶点组
        '''
        if obj.type == "MESH":
            # obj = bpy.context.active_object
            obj.update_from_editmode()
            vgroup_used = {i: False for i, k in enumerate(obj.vertex_groups)}

            for v in obj.data.vertices:
                for g in v.groups:
                    if g.weight > 0.0:
                        vgroup_used[g.group] = True

            for i, used in sorted(vgroup_used.items(), reverse=True):
                if not used:
                    obj.vertex_groups.remove(obj.vertex_groups[i])

    @classmethod
    def remove_all_vertex_groups(cls,obj):
        '''
        移除给定obj的未使用的顶点组
        '''
        if obj.type == "MESH":
            for x in obj.vertex_groups:
                obj.vertex_groups.remove(x)

    # @classmethod
    # def merge_vertex_groups_with_same_number(cls):
    #     # Author: SilentNightSound#7430
    #     # Combines vertex groups with the same prefix into one, a fast alternative to the Vertex Weight Mix that works for multiple groups
    #     # You will likely want to use blender_fill_vg_gaps.txt after this to fill in any gaps caused by merging groups together
    #     # Nico: we only need mode 3 here.

    #     selected_obj = [obj for obj in bpy.context.selected_objects]
    #     vgroup_names = []

    #     ##### USAGE INSTRUCTIONS
    #     # MODE 1: Runs the merge on a specific list of vertex groups in the selected object(s). Can add more names or fewer to the list - change the names to what you need
    #     # MODE 2: Runs the merge on a range of vertex groups in the selected object(s). Replace smallest_group_number with the lower bound, and largest_group_number with the upper bound
    #     # MODE 3 (DEFAULT): Runs the merge on ALL vertex groups in the selected object(s)

    #     # Select the mode you want to run:
    #     mode = 3

    #     # Required data for MODE 1:
    #     vertex_groups = ["replace_with_first_vertex_group_name", "second_vertex_group_name", "third_name_etc"]

    #     # Required data for MODE 2:
    #     smallest_group_number = 000
    #     largest_group_number = 999

    #     ######

    #     if mode == 1:
    #         vgroup_names = [vertex_groups]
    #     elif mode == 2:
    #         vgroup_names = [[f"{i}" for i in range(smallest_group_number, largest_group_number + 1)]]
    #     elif mode == 3:
    #         vgroup_names = [[x.name.split(".")[0] for x in y.vertex_groups] for y in selected_obj]
    #     else:
    #         raise Fatal("Mode not recognized, exiting")

    #     if not vgroup_names:
    #         raise Fatal(
    #             "No vertex groups found, please double check an object is selected and required data has been entered")

    #     for cur_obj, cur_vgroup in zip(selected_obj, itertools.cycle(vgroup_names)):
    #         for vname in cur_vgroup:
    #             relevant = [x.name for x in cur_obj.vertex_groups if x.name.split(".")[0] == f"{vname}"]

    #             if relevant:

    #                 vgroup = cur_obj.vertex_groups.new(name=f"x{vname}")

    #                 for vert_id, vert in enumerate(cur_obj.data.vertices):
    #                     available_groups = [v_group_elem.group for v_group_elem in vert.groups]

    #                     combined = 0
    #                     for v in relevant:
    #                         if cur_obj.vertex_groups[v].index in available_groups:
    #                             combined += cur_obj.vertex_groups[v].weight(vert_id)

    #                     if combined > 0:
    #                         vgroup.add([vert_id], combined, 'ADD')

    #                 for vg in [x for x in cur_obj.vertex_groups if x.name.split(".")[0] == f"{vname}"]:
    #                     cur_obj.vertex_groups.remove(vg)

    #                 for vg in cur_obj.vertex_groups:
    #                     if vg.name[0].lower() == "x":
    #                         vg.name = vg.name[1:]

    #         bpy.context.view_layer.objects.active = cur_obj
    #         bpy.ops.object.vertex_group_sort()

    @classmethod
    def merge_vertex_groups_with_same_number_v2(cls):
        '''
        merge_vertex_groups_with_same_number 的 Mode 3 优化版本
        大幅提升执行速度 (Differential Update Strategy)

        
        '''
        selected_objs = [obj for obj in bpy.context.selected_objects if obj.type == 'MESH']
        if not selected_objs:
             raise Fatal("No mesh objects selected")

        for obj in selected_objs:
            # 1. Group by prefix
            groups_by_prefix = {}
            for vg in obj.vertex_groups:
                prefix = vg.name.split(".")[0]
                if prefix not in groups_by_prefix:
                    groups_by_prefix[prefix] = []
                groups_by_prefix[prefix].append(vg)
            
            # 2. Identify merge targets and sources
            # merge_actions stores: (target_vg_name, [source_vg_indices])
            # We store indices/names because pointers might be risky if we renamed things, usually ok though.
            merge_actions = [] 
            all_source_vgs = []
            
            for prefix, vgs in groups_by_prefix.items():
                if len(vgs) < 2:
                    # Rename single groups just in case
                    if vgs[0].name != prefix:
                        vgs[0].name = prefix
                    continue
                
                # Pick target: prefer exact match or first
                target = next((g for g in vgs if g.name == prefix), vgs[0])
                if target.name != prefix:
                    target.name = prefix
                
                sources = [g for g in vgs if g != target]
                merge_actions.append( (target.name, sources) )
                all_source_vgs.extend(sources)
            
            if not merge_actions:
                continue

            # 3. Create mapping for fast lookup
            # index -> target_name
            # obj.vertex_groups can be non-contiguous in memory but indices are 0..N-1 usually? 
            # VertexGroup.index is the index in the list.
            max_idx = max(vg.index for vg in obj.vertex_groups)
            idx_to_target = [None] * (max_idx + 1)
            
            for t_name, sources in merge_actions:
                for s in sources:
                    idx_to_target[s.index] = t_name

            # 4. Collect weight updates
            # target_name -> { vertex_idx: accumulated_weight }
            updates = {}

            # Iterate vertices
            for v in obj.data.vertices:
                for g in v.groups:
                    if g.group <= max_idx:
                        t_name = idx_to_target[g.group]
                        if t_name:
                            # Accumulate
                            if t_name not in updates:
                                updates[t_name] = {}
                            
                            u_dict = updates[t_name]
                            if v.index in u_dict:
                                u_dict[v.index] += g.weight
                            else:
                                u_dict[v.index] = g.weight

            # 5. Apply updates
            for t_name, w_dict in updates.items():
                vg = obj.vertex_groups.get(t_name)
                if not vg: continue

                for v_idx, w in w_dict.items():
                    if w > 0:
                        vg.add([v_idx], w, 'ADD')
            
            # 6. Remove source groups
            for vg in all_source_vgs:
                try:
                    obj.vertex_groups.remove(vg)
                except:
                    pass # Already removed?
            
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.vertex_group_sort()


    @classmethod
    def fill_vertex_group_gaps(cls):
        # Author: SilentNightSound#7430
        # Fills in missing vertex groups for a model so there are no gaps, and sorts to make sure everything is in order
        # Works on the currently selected object
        # e.g. if the selected model has groups 0 1 4 5 7 2 it adds an empty group for 3 and 6 and sorts to make it 0 1 2 3 4 5 6 7
        # Very useful to make sure there are no gaps or out-of-order vertex groups

        # Can change this to another number in order to generate missing groups up to that number
        # e.g. setting this to 130 will create 0,1,2...130 even if the active selected object only has 90
        # Otherwise, it will use the largest found group number and generate everything up to that number
        largest = 0

        ob = bpy.context.active_object
        ob.update_from_editmode()

        for vg in ob.vertex_groups:
            try:
                if int(vg.name.split(".")[0]) > largest:
                    largest = int(vg.name.split(".")[0])
            except ValueError:
                print("Vertex group not named as integer, skipping")

        missing = set([f"{i}" for i in range(largest + 1)]) - set([x.name.split(".")[0] for x in ob.vertex_groups])
        for number in missing:
            ob.vertex_groups.new(name=f"{number}")

        bpy.ops.object.vertex_group_sort()


    # 由虹汐哥改进的版本，骨骼位置放到了几何中心
    @classmethod
    def create_armature_from_vertex_groups(cls,bone_length=0.1):
        # 验证选择对象
        obj = bpy.context.active_object
        if not obj or obj.type != 'MESH':
            raise Exception("请先选择一个网格物体")
        
        if not obj.vertex_groups:
            raise Exception("目标物体没有顶点组")

        # 预计算世界变换矩阵
        matrix = obj.matrix_world

        # 创建骨架物体
        armature = bpy.data.armatures.new("AutoRig_Armature")
        armature_obj = bpy.data.objects.new("AutoRig", armature)
        bpy.context.scene.collection.objects.link(armature_obj)

        # 设置活动对象
        bpy.context.view_layer.objects.active = armature_obj
        armature_obj.select_set(True)

        # 预收集顶点组数据 {顶点组索引: [顶点列表]}
        vg_verts = {vg.index: [] for vg in obj.vertex_groups}
        for v in obj.data.vertices:
            for g in v.groups:
                if g.group in vg_verts:
                    vg_verts[g.group].append(v)

        # 进入编辑模式创建骨骼
        bpy.ops.object.mode_set(mode='EDIT')
        try:
            for vg in obj.vertex_groups:
                verts = vg_verts.get(vg.index)
                if not verts:
                    continue

                # 计算几何中心（世界坐标）
                coords = [matrix @ v.co for v in verts]
                center = sum(coords, Vector()) / len(coords)

                # 创建垂直方向骨骼
                bone = armature.edit_bones.new(vg.name)
                bone.head = center
                bone.tail = center + Vector((0, 0, 0.1))  # 固定Z轴方向

        finally:
            bpy.ops.object.mode_set(mode='OBJECT')

    @classmethod
    def remove_not_number_vertex_groups(cls,obj):
        for vg in reversed(obj.vertex_groups):
            if vg.name.isdecimal():
                continue
            # print('Removing vertex group', vg.name)
            obj.vertex_groups.remove(vg)

    @classmethod
    def split_mesh_by_vertex_group(cls,obj):
        '''
        Code copied and modified from @Kail_Nethunter, very useful in some special meets.
        https://blenderartists.org/t/split-a-mesh-by-vertex-groups/438990/11
        '''
        origin_name = obj.name
        keys = obj.vertex_groups.keys()
        real_keys = []
        for gr in keys:
            bpy.ops.object.mode_set(mode="EDIT")
            # Set the vertex group as active
            bpy.ops.object.vertex_group_set_active(group=gr)

            # Deselect all verts and select only current VG
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.vertex_group_select()
            # bpy.ops.mesh.select_all(action='INVERT')
            try:
                bpy.ops.mesh.separate(type="SELECTED")
                real_keys.append(gr)
            except:
                pass
        for i in range(1, len(real_keys) + 1):
            bpy.data.objects['{}.{:03d}'.format(origin_name, i)].name = '{}.{}'.format(
                origin_name, real_keys[i - 1])
            
    @classmethod
    def get_vertex_group_weight(cls,vgroup, vertex):
        '''
        Credit to @Comilarex
        https://gamebanana.com/tools/19057
        '''
        for group in vertex.groups:
            if group.group == vgroup.index:
                return group.weight
        return 0.0

    @classmethod
    def calculate_vertex_influence_area(cls,obj):
        '''
        Credit to @Comilarex
        https://gamebanana.com/tools/19057
        '''
        vertex_area = [0.0] * len(obj.data.vertices)
        
        for face in obj.data.polygons:
            # Assuming the area is evenly distributed among the vertices
            area_per_vertex = face.area / len(face.vertices)
            for vert_idx in face.vertices:
                vertex_area[vert_idx] += area_per_vertex

        return vertex_area

    @classmethod
    def get_weighted_center(cls, obj, vgroup):
        '''
        Credit to @Comilarex
        https://gamebanana.com/tools/19057
        '''
        total_weight_area = 0.0
        weighted_position_sum = Vector((0.0, 0.0, 0.0))

        # Calculate the area influenced by each vertex
        vertex_influence_area = cls.calculate_vertex_influence_area(obj)

        for vertex in obj.data.vertices:
            weight = cls.get_vertex_group_weight(vgroup, vertex)
            influence_area = vertex_influence_area[vertex.index]
            weight_area = weight * influence_area

            if weight_area > 0:
                weighted_position_sum += obj.matrix_world @ vertex.co * weight_area
                total_weight_area += weight_area

        if total_weight_area > 0:
            return weighted_position_sum / total_weight_area
        else:
            return None

    @classmethod
    def match_vertex_groups(cls, base_obj, target_obj):
        '''
        Credit to @Comilarex
        https://gamebanana.com/tools/19057
        '''
        # Rename all vertex groups in base_obj to "unknown"
        for base_group in base_obj.vertex_groups:
            base_group.name = "unknown"

        # Precompute centers for all target vertex groups
        target_centers = {}
        for target_group in target_obj.vertex_groups:
            target_centers[target_group.name] = cls.get_weighted_center(target_obj, target_group)

        # Perform the matching and renaming process
        for base_group in base_obj.vertex_groups:
            base_center = cls.get_weighted_center(base_obj, base_group)
            if base_center is None:
                continue

            best_match = None
            best_distance = float('inf')

            for target_group_name, target_center in target_centers.items():
                if target_center is None:
                    continue

                distance = (base_center - target_center).length
                if distance < best_distance:
                    best_distance = distance
                    best_match = target_group_name

            if best_match:
                base_group.name = best_match


    @classmethod
    def get_blendweights_blendindices_v1(cls,mesh,normalize_weights:bool = False):
        mesh_loops = mesh.loops
        mesh_loops_length = len(mesh_loops)
        mesh_vertices = mesh.vertices

        loop_vertex_indices = numpy.empty(mesh_loops_length, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)

        max_groups = 4

        # Extract and sort the top 4 groups by weight for each vertex.
        sorted_groups = [
            sorted(v.groups, key=lambda x: x.weight, reverse=True)[:max_groups]
            for v in mesh_vertices
        ]

        # Initialize arrays to hold all groups and weights with zeros.
        all_groups = numpy.zeros((len(mesh_vertices), max_groups), dtype=int)
        all_weights = numpy.zeros((len(mesh_vertices), max_groups), dtype=numpy.float32)


        # Fill the pre-allocated arrays with group indices and weights.
        for v_index, groups in enumerate(sorted_groups):
            num_groups = min(len(groups), max_groups)
            all_groups[v_index, :num_groups] = [g.group for g in groups][:num_groups]
            all_weights[v_index, :num_groups] = [g.weight for g in groups][:num_groups]

        # Initialize the blendindices and blendweights with zeros.
        blendindices = numpy.zeros((mesh_loops_length, max_groups), dtype=numpy.uint32)
        blendweights = numpy.zeros((mesh_loops_length, max_groups), dtype=numpy.float32)

        # Map from loop_vertex_indices to precomputed data using advanced indexing.
        valid_mask = (0 <= numpy.array(loop_vertex_indices)) & (numpy.array(loop_vertex_indices) < len(mesh_vertices))
        valid_indices = loop_vertex_indices[valid_mask]

        blendindices[valid_mask] = all_groups[valid_indices]
        blendweights[valid_mask] = all_weights[valid_indices]

        # XXX 必须对当前obj对象执行权重规格化，否则模型细分后会导致模型坑坑洼洼
        
        blendweights = blendweights / numpy.sum(blendweights, axis=1)[:, None]

        blendweights_dict = {}
        blendindices_dict = {}

        blendweights_dict[0] = blendweights
        blendindices_dict[0] = blendindices
        return blendweights_dict, blendindices_dict
    
    @classmethod
    def get_blendweights_blendindices_v3(cls,mesh, normalize_weights: bool = False):
        print("get_blendweights_blendindices_v3")
        print(normalize_weights)

        mesh_loops = mesh.loops
        mesh_loops_length = len(mesh_loops)
        mesh_vertices = mesh.vertices
        
        # 获取循环顶点的顶点索引
        loop_vertex_indices = numpy.empty(mesh_loops_length, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)
        
        # 计算每个顶点的最大组数（向上取整到最近的4的倍数）
        max_groups_per_vertex = 0
        for v in mesh_vertices:
            group_count = len(v.groups)
            if group_count > max_groups_per_vertex:
                max_groups_per_vertex = group_count
        
        # 将最大组数对齐到4的倍数（每个语义索引包含4个权重）
        max_groups_per_vertex = ((max_groups_per_vertex + 3) // 4) * 4
        num_sets = max_groups_per_vertex // 4  # 需要的语义索引数量

        # print("num_sets: " + str(num_sets))
        
        # 如果最大组数小于4，至少需要1组
        if num_sets == 0 and max_groups_per_vertex > 0:
            num_sets = 1
        
        groups_per_set = 4
        total_groups = num_sets * groups_per_set

        # 提取并排序顶点组（取前 total_groups 个）
        sorted_groups = [
            sorted(v.groups, key=lambda x: x.weight, reverse=True)[:total_groups]
            for v in mesh_vertices
        ]

        # 初始化存储数组
        all_groups = numpy.zeros((len(mesh_vertices), total_groups), dtype=int)
        all_weights = numpy.zeros((len(mesh_vertices), total_groups), dtype=numpy.float32)

        # 填充权重和索引数据
        for v_idx, groups in enumerate(sorted_groups):
            count = min(len(groups), total_groups)
            all_groups[v_idx, :count] = [g.group for g in groups][:count]
            all_weights[v_idx, :count] = [g.weight for g in groups][:count]

        # 关键步骤：整体归一化所有权重
        if normalize_weights:
            # 计算每个顶点的权重总和
            weight_sums = numpy.sum(all_weights, axis=1)
            # 避免除以零（将总和为0的顶点设置为1，这样权重保持为0）
            weight_sums[weight_sums == 0] = 1
            # 归一化权重
            all_weights = all_weights / weight_sums[:, numpy.newaxis]


        # 将数据重塑为 [顶点数, 组数, 4]
        all_weights_reshaped = all_weights.reshape(len(mesh_vertices), num_sets, groups_per_set)
        all_groups_reshaped = all_groups.reshape(len(mesh_vertices), num_sets, groups_per_set)

        # 初始化输出字典
        blendweights_dict = {}
        blendindices_dict = {}


        # 为每组数据创建独立数组
        for set_idx in range(num_sets):
            # 初始化当前组的存储
            blendweights = numpy.zeros((mesh_loops_length, groups_per_set), dtype=numpy.float32)
            blendindices = numpy.zeros((mesh_loops_length, groups_per_set), dtype=numpy.uint32)
            
            # 创建有效索引掩码
            valid_mask = (0 <= loop_vertex_indices) & (loop_vertex_indices < len(mesh_vertices))
            valid_indices = loop_vertex_indices[valid_mask]
            
            # 映射数据到循环顶点
            blendweights[valid_mask] = all_weights_reshaped[valid_indices, set_idx, :]
            blendindices[valid_mask] = all_groups_reshaped[valid_indices, set_idx, :]

            
            # 3. 关键：再把每行 4 个权重重新归一化到 1（和 v1 最后一行等价）
            if normalize_weights:
                row_sum = numpy.sum(blendweights, axis=1, keepdims=True)
                # 避免 0 除
                numpy.putmask(row_sum, row_sum == 0, 1.0)
                blendweights = blendweights / row_sum

            
            # 存储到字典（使用SemanticIndex作为键）
            blendweights_dict[set_idx] = blendweights
            blendindices_dict[set_idx] = blendindices

        # blendweights = blendweights / numpy.sum(blendweights, axis=1)[:, None]
        # print("blendweights_dict: " + str(blendweights_dict[2][0]))
        # print("blendindices_dict: " + str(blendindices_dict[2][0]))

        return blendweights_dict, blendindices_dict
    



    @classmethod
    def get_blendweights_blendindices_v4_fast(cls, mesh, normalize_weights: bool = False, blend_size=4):
        '''
        Collects flat triplets (vertex_idx, group_id, weight) once, then uses numpy to
        compute per-vertex top-K (K = aligned_max_groups) and maps to per-loop arrays.
        Returns same shape: (blendweights_dict, blendindices_dict) with SemanticIndex 0.

        目前只有鸣潮在使用，尚未在其它游戏中进行测试
        TODO 需要测试其它游戏是否兼容。
        '''
        import numpy as np

        mesh_loops = mesh.loops
        mesh_verts = mesh.vertices
        n_loops = len(mesh_loops)
        n_verts = len(mesh_verts)

        # get loop->vertex indices (will be used later)
        loop_vertex_indices = np.empty(n_loops, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)

        # 1) collect flat lists of (v_idx, group_id, weight)
        v_idx_list = []
        g_id_list = []
        w_list = []
        for v in mesh_verts:
            # v.groups is typically small; we collect all triplets into flat lists
            for g in v.groups:
                if g.weight > 0:
                    v_idx_list.append(v.index)
                    g_id_list.append(g.group)
                    w_list.append(g.weight)

        if len(v_idx_list) == 0:
            # no weights at all: return zeros compatible with old interface
            aligned_max_groups = max(4, blend_size)
            blendweights = np.zeros((n_loops, aligned_max_groups), dtype=np.float32)
            blendindices = np.zeros((n_loops, aligned_max_groups), dtype=np.uint32)
            return {0: blendweights}, {0: blendindices}

        v_idx_arr = np.asarray(v_idx_list, dtype=np.int32)
        g_arr = np.asarray(g_id_list, dtype=np.int32)
        w_arr = np.asarray(w_list, dtype=np.float32)

        # 2) figure out aligned_max_groups (multiple of 4, at least blend_size)
        # real_max_groups = max groups any vertex has
        # we can compute counts via bincount
        counts = np.bincount(v_idx_arr, minlength=n_verts)
        real_max_groups = int(counts.max()) if counts.size > 0 else 0
        aligned_max_groups = 4 * math.ceil(real_max_groups / 4) if real_max_groups else 4
        if aligned_max_groups < blend_size:
            aligned_max_groups = blend_size
        M = aligned_max_groups

        # 3) we want for each vertex the top-M groups sorted by weight
        # Strategy:
        # - stable sort global entries by (vertex_index asc, weight desc)
        # - compute per-vertex offsets and build index positions for top-M
        order = np.lexsort(( -w_arr, v_idx_arr ))  # sorted by vertex asc, weight desc
        v_sorted = v_idx_arr[order]
        g_sorted = g_arr[order]
        w_sorted = w_arr[order]

        # offsets: start index in sorted arrays for each vertex
        # counts already known; offsets = cumsum(counts) shifted
        offsets = np.zeros(n_verts, dtype=np.int64)
        if n_verts > 0:
            offsets[1:] = np.cumsum(counts)[:-1]

        # build positions matrix: shape (n_verts, M)
        # pos = offsets[:,None] + np.arange(M)
        arange_M = np.arange(M, dtype=np.int64)
        pos = offsets[:, None] + arange_M[None, :]   # may point beyond end
        # mask valid positions
        valid_mask = pos < (offsets[:, None] + counts[:, None])

        # clip positions to last index to avoid OOB (we'll zero invalid later)
        pos_clipped = np.minimum(pos, order.size - 1)
        # pick group ids and weights for these positions
        picked_g = g_sorted[pos_clipped]    # shape (n_verts, M)
        picked_w = w_sorted[pos_clipped]    # shape (n_verts, M)

        # zero out invalid slots
        picked_g[~valid_mask] = 0
        picked_w[~valid_mask] = 0.0

        # 4) optionally ensure per-vertex normalization (per original code behavior)
        if normalize_weights:
            # sum across M and avoid divide by zero
            sums = picked_w.sum(axis=1, keepdims=True)
            sums[sums == 0] = 1.0
            picked_w = picked_w / sums

        # 5) map per-vertex data to per-loop arrays using loop_vertex_indices
        # valid_mask_loop: guard against malformed loops
        valid_loop_mask = (0 <= loop_vertex_indices) & (loop_vertex_indices < n_verts)
        blendindices = np.zeros((n_loops, M), dtype=np.uint32)
        blendweights = np.zeros((n_loops, M), dtype=np.float32)
        if np.any(valid_loop_mask):
            valid_vidx = loop_vertex_indices[valid_loop_mask]
            blendindices[valid_loop_mask] = picked_g[valid_vidx]
            blendweights[valid_loop_mask] = picked_w[valid_vidx]

        # return in old interface: semantic index 0 only (v4 implementation style)
        return {0: blendweights}, {0: blendindices}

    @classmethod
    def get_blendweights_blendindices_v4(cls, mesh, normalize_weights: bool = False,blend_size = 4):
        """
        注意这个先别删留着备用防止新的出问题，新的fast是这个的好几倍速度，所以这个弃用了。
        """
        # -------------------- 基础数据 --------------------
        mesh_loops = mesh.loops
        mesh_verts = mesh.vertices
        n_loops = len(mesh_loops)

        # 提前把每条 loop 对应的顶点索引抓出来
        loop_vertex_indices = numpy.empty(n_loops, dtype=int)
        mesh_loops.foreach_get("vertex_index", loop_vertex_indices)

        # -------------------- 1. 收集每个顶点的所有非零权重组 --------------------
        # 用 Python list 先存，因为每组数量不固定
        vert_groups_weights = []   # [[(group_id, weight), ...], ...] 长度 = 顶点数
        for v in mesh_verts:
            # 只保留 weight > 0 的组，防止空数据
            gw = [(g.group, g.weight) for g in v.groups if g.weight > 0]
            # 按权重从大到小排序，方便后续直接取前 N 个
            gw.sort(key=lambda x: x[1], reverse=True)
            vert_groups_weights.append(gw)

        # -------------------- 2. 计算“真实最大组数”并补齐到 4 的倍数 --------------------
        # 先找所有顶点里真实存在的最大组数
        real_max_groups = max(len(gw) for gw in vert_groups_weights) if vert_groups_weights else 0
        # 补齐到 4 的倍数
        aligned_max_groups = 4 * math.ceil(real_max_groups / 4) if real_max_groups else 4

        if aligned_max_groups < blend_size:
            aligned_max_groups = blend_size

        # -------------------- 3. 一次性申请对齐后的 ndarray --------------------
        # 所有顶点一起存，方便后面用高级索引一次性映射到 loop
        all_groups = numpy.zeros((len(mesh_verts), aligned_max_groups), dtype=int)
        all_weights = numpy.zeros((len(mesh_verts), aligned_max_groups), dtype=numpy.float32)

        # -------------------- 4. 填充数据 & 可选归一化 --------------------
        for v_idx, gw in enumerate(vert_groups_weights):
            # 把真实数据写进去
            for col, (g_id, w) in enumerate(gw):
                all_groups[v_idx, col] = g_id
                all_weights[v_idx, col] = w

            # 如果 normalize_weights=True，对该顶点权重归一化（保留 0 的位置仍为 0）
            weight_sum = all_weights[v_idx].sum()
            if weight_sum > 0:
                all_weights[v_idx] /= weight_sum

        # -------------------- 5. 把“逐顶点”数据映射到“逐 loop” --------------------
        # 先检查索引合法性，防止越界
        valid_mask = (0 <= loop_vertex_indices) & (loop_vertex_indices < len(mesh_verts))
        valid_vidx = loop_vertex_indices[valid_mask]

        blendindices = numpy.zeros((n_loops, aligned_max_groups), dtype=numpy.uint32)
        blendweights = numpy.zeros((n_loops, aligned_max_groups), dtype=numpy.float32)

        # 高级索引一次性拷贝
        blendindices[valid_mask] = all_groups[valid_vidx]
        blendweights[valid_mask] = all_weights[valid_vidx]

        # -------------------- 6. 返回兼容旧接口的字典 --------------------
        return {0: blendweights}, {0: blendindices}