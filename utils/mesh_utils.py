import bpy
import numpy

from ..config.main_config import GlobalConfig, LogicName

class MeshUtils:

    @classmethod
    def set_import_normals(cls,mesh,normals):
        # Blender4.2 移除了mesh.create_normal_splits()
        if bpy.app.version <= (4, 0, 0):
            # mesh.use_auto_smooth = True

            # 这里直接同步了SpectrumQT的导入代码，方便测试对比细节
            normals = numpy.asarray(normals, dtype=numpy.float32) 
            loop_vertex_idx = numpy.empty(len(mesh.loops), dtype=numpy.int32)
            mesh.loops.foreach_get('vertex_index', loop_vertex_idx)

            # Initialize empty split vertex normals
            mesh.create_normals_split()
            # Write vertex normals, they will be immidiately converted to loop normals
            mesh.loops.foreach_set('normal', normals[loop_vertex_idx].flatten().tolist())
            # Read loop normals
            recalculated_normals = numpy.empty(len(mesh.loops)*3, dtype=numpy.float32)
            mesh.loops.foreach_get('normal', recalculated_normals)
            recalculated_normals = recalculated_normals.reshape((-1, 3))
            # Force usage of custom normals
            mesh.use_auto_smooth = True
            # Force vertex normals interpolation across the polygon (required in older versions)
            mesh.polygons.foreach_set('use_smooth', numpy.ones(len(mesh.polygons), dtype=numpy.int8))
            # Write loop normals to permanent storage
            mesh.normals_split_custom_set(recalculated_normals.tolist())
        
        # if GlobalConfig.logic_name != LogicName.UnityCPU:
        mesh.normals_split_custom_set_from_vertices(normals)
    
    # Nico: 使用下面的代码，可以确保在Blender3.6中导入的内容看起来和Blender 4.2或以上版本中一致，并且边缘不再锐利
    # 这玩意太坑了，花了很久才搞明白，Blender不同版本的法线处理差异
    @classmethod
    def set_import_normals_v2(cls, mesh, normals):
        import bpy
        import numpy as np

        normals = np.asarray(normals, dtype=np.float32)
        n_verts = len(mesh.vertices)
        
        # 安全检查：确保 normals 数量匹配顶点数
        if normals.shape[0] != n_verts:
            raise ValueError(f"Expected {n_verts} vertex normals, got {normals.shape[0]}")

        # Blender 4.1+ 推荐路径：直接从顶点设置，自动插值得到丝滑效果
        if bpy.app.version >= (4, 1, 0):
            # mesh.use_auto_smooth = True  # 确保启用 auto smooth
            mesh.normals_split_custom_set_from_vertices(normals)
            return

        # === Blender <= 4.0（如 3.6）的兼容路径 ===
        # 步骤：
        # 1. 启用 auto smooth（必须）
        # 2. 创建 split normals
        # 3. 将顶点法线广播到每个 loop
        # 4. 提交为自定义法线

        mesh.use_auto_smooth = True

        # 获取每个 loop 对应的顶点索引
        loop_vertex_indices = np.empty(len(mesh.loops), dtype=np.int32)
        mesh.loops.foreach_get("vertex_index", loop_vertex_indices)

        # 将顶点法线映射到 loop 法线（每个 loop 使用其顶点的法线）
        loop_normals = normals[loop_vertex_indices].flatten()

        # 创建 split normals 数据结构（Blender <=4.0 需要）
        mesh.create_normals_split()

        # 设置 loop 法线（临时）
        mesh.loops.foreach_set("normal", loop_normals.tolist())

        # 读回以确保数据对齐（可选但保险）
        recalculated = np.empty(len(mesh.loops) * 3, dtype=np.float32)
        mesh.loops.foreach_get("normal", recalculated)
        recalculated = recalculated.reshape((-1, 3))

        # 应用自定义法线
        mesh.normals_split_custom_set(recalculated.tolist())

        # 可选：强制所有面为平滑（避免硬边干扰）
        mesh.polygons.foreach_set("use_smooth", np.ones(len(mesh.polygons), dtype=np.bool_))