import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils
from ..utils.obj_utils import ObjUtils
from ..utils.performance_stats import start_operation, end_operation, print_performance_report, save_performance_report_to_editor, reset_performance_stats, set_performance_stats_enabled, is_performance_stats_enabled
from ..utils.preprocess_cache import get_cache_manager, FingerprintCalculator, reset_cache_manager

from ..config.main_config import GlobalConfig, LogicName
from ..base.m_global_key_counter import M_GlobalKeyCounter

from ..config.properties_generate_mod import Properties_GenerateMod
from ..config.properties_import_model import Properties_ImportModel

from .blueprint_model import BluePrintModel
from .blueprint_export_helper import BlueprintExportHelper


'''
TODO 

1.现在咱们不是有一个可以选择生成Mod的目标文件夹的按钮嘛
后续改成输出节点的一个属性，这样用户就可以在蓝图里动态控制Mod生成路径了
这样每个工作空间都可以指定独特的生成Mod位置

2.对于之前用户说的生成mod要有备份的问题，也可以在输出节点新增一个备份文件夹的属性
'''
class SSMTSelectGenerateModFolder(bpy.types.Operator):
    '''
    来一个按钮来选择生成Mod的位置,部分用户有这个需求但是这个设计是不优雅的
    正常流程就是应该生成在Mods文件夹中,以便于游戏内F10刷新可以直接生效
    后续观察如果使用人数过少就移除掉
    '''
    bl_idname = "ssmt.select_generate_mod_folder"
    bl_label = "选择生成Mod的位置文件夹"
    bl_description = "选择生成Mod的位置文件夹"

    directory: bpy.props.StringProperty(
        subtype='DIR_PATH'
    ) # type: ignore

    def execute(self, context):
        # 将选择的文件夹路径保存到属性组中
        context.scene.properties_generate_mod.generate_mod_folder_path = self.directory
        self.report({'INFO'}, f"已选择文件夹: {self.directory}")
        return {'FINISHED'}

    def invoke(self, context, event):
        # 打开文件浏览器，只允许选择文件夹
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}


class SSMTClearPreprocessCache(bpy.types.Operator):
    """清理预处理缓存"""
    bl_idname = "ssmt.clear_preprocess_cache"
    bl_label = "清理预处理缓存"
    bl_description = "清理所有预处理缓存，释放磁盘空间"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        from ..utils.preprocess_cache import get_cache_manager
        
        blend_file = bpy.data.filepath
        cache_manager = get_cache_manager(blend_file)
        stats = cache_manager.get_cache_stats()
        
        cache_manager.clear_cache()
        reset_cache_manager()
        
        self.report({'INFO'}, f"已清理 {stats['total_entries']} 个缓存文件，释放 {stats['total_size_mb']:.2f} MB")
        return {'FINISHED'}


class SSMTGenerateModBlueprint(bpy.types.Operator):
    bl_idname = "ssmt.generate_mod_blueprint"
    bl_label = TR.translate("生成Mod(蓝图架构)")
    bl_description = "根据当前工作空间对应的蓝图架构生成对应的Mod文件"
    bl_options = {'REGISTER','UNDO'}

    # 允许通过属性传入指定的蓝图树名称
    node_tree_name: bpy.props.StringProperty(name="Node Tree Name", default="") # type: ignore

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")
        
        # 根据配置设置性能统计开关
        set_performance_stats_enabled(Properties_GenerateMod.enable_performance_stats())
        
        # 重置性能统计
        reset_performance_stats()
        start_operation("GenerateMod_Total")
        
        wm = context.window_manager

        target_tree_name = self.node_tree_name

        # Fallback: 如果没有通过参数传递树名，尝试从当前上下文推断
        if not target_tree_name:
            # 尝试获取当前编辑器中的 NodeTree
            space_data = getattr(context, "space_data", None)
            if space_data and (space_data.type == 'NODE_EDITOR'):
                 # 优先检查 edit_tree (这通常是用户正在查看的 Group 或 Tree)
                 tree = getattr(space_data, "edit_tree", None)
                 if not tree:
                     tree = getattr(space_data, "node_tree", None)
                 
                 if tree:
                     target_tree_name = tree.name

        # Config Override Logic
        if target_tree_name:
            print(f"Generating Mod from specified Node Tree: {target_tree_name}")
            BlueprintExportHelper.forced_target_tree_name = target_tree_name
        else:
            print("Warning: No Node Tree specified for Mod Generation. Using default workspace name logic.")
            BlueprintExportHelper.forced_target_tree_name = None

        # 获取所有要导出的物体及其对应的节点/项目
        start_operation("GetExportObjects")
        obj_node_mapping = self._get_export_objects_with_nodes()
        total_objects = len(obj_node_mapping)
        end_operation("GetExportObjects")
        
        if total_objects == 0:
            self.report({'WARNING'}, "没有找到要导出的物体")
            end_operation("GenerateMod_Total")
            return {'CANCELLED'}
        
        use_parallel = Properties_ImportModel.use_parallel_export()
        blend_file_saved = bpy.data.is_saved
        blend_file_dirty = bpy.data.is_dirty
        blend_file = bpy.data.filepath
        mirror_workflow_enabled = Properties_ImportModel.use_mirror_workflow()
        
        preview_export_only = Properties_GenerateMod.preview_export_only()
        
        if preview_export_only:
            print("[PreviewExport] 配置表预导出模式：跳过物体处理，仅生成 INI")
            wm.progress_begin(0, 100)
            wm.progress_update(0)
            copy_mapping = {}
        else:
            if use_parallel:
                if not blend_file_saved:
                    self.report({'ERROR'}, "并行导出需要先保存项目文件")
                    end_operation("GenerateMod_Total")
                    return {'CANCELLED'}
                if blend_file_dirty:
                    self.report({'ERROR'}, "项目有未保存的修改，请先保存后再进行并行导出")
                    end_operation("GenerateMod_Total")
                    return {'CANCELLED'}
            
            wm.progress_begin(0, 100)
            wm.progress_update(0)
            print(f"开始处理 {total_objects} 个物体...")
            
            copy_mapping = {}
            
            if use_parallel and blend_file_saved and not blend_file_dirty and total_objects >= 4:
                print(f"[ParallelPreprocess] 启用并行预处理，物体数量: {total_objects}")
                start_operation("ParallelPreprocess")
                copy_mapping = self._parallel_preprocess(context, obj_node_mapping, mirror_workflow_enabled)
                end_operation("ParallelPreprocess")
                if not copy_mapping:
                    print("[ParallelPreprocess] 并行预处理失败，回退到单进程模式")
                    start_operation("SequentialPreprocess")
                    copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file)
                    end_operation("SequentialPreprocess")
            else:
                start_operation("SequentialPreprocess")
                copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file)
                end_operation("SequentialPreprocess")
        
        try:
            # 计算最大导出次数
            max_export_count = BlueprintExportHelper.calculate_max_export_count()
            print(f"最大导出次数: {max_export_count}")
            
            # 重置导出状态
            BlueprintExportHelper.reset_export_state()
            
            # 循环执行多次导出
            for export_index in range(1, max_export_count + 1):
                BlueprintExportHelper.current_export_index = export_index
                print(f"开始第 {export_index}/{max_export_count} 次导出")
                
                # 更新进度 (50-90%)
                progress = 50 + int(export_index / max_export_count * 40)
                wm.progress_update(progress)
                
                # 更新多文件导出节点的当前物体
                BlueprintExportHelper.update_multifile_export_nodes(export_index)
                
                # 更新导出路径
                BlueprintExportHelper.update_export_path(export_index)
                
                M_GlobalKeyCounter.initialize()

                # 调用对应游戏的生成Mod逻辑
                start_operation(f"GenerateMod_Export_{export_index}")
                if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
                    from ..games.wwmi import ModModelWWMI
                    migoto_mod_model = ModModelWWMI()
                    migoto_mod_model.generate_unreal_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.YYSLS:
                    from ..games.yysls import ModModelYYSLS
                    migoto_mod_model = ModModelYYSLS()
                    migoto_mod_model.generate_unity_vs_config_ini()

                elif GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.IdentityV2 or GlobalConfig.logic_name == LogicName.NierR:
                    from ..games.identityv import ModModelIdentityV
                    migoto_mod_model = ModModelIdentityV()

                    migoto_mod_model.generate_unity_vs_config_ini()
                
                # 老米四件套
                elif GlobalConfig.logic_name == LogicName.HIMI:
                    from ..games.himi import ModModelHIMI
                    migoto_mod_model = ModModelHIMI()
                    migoto_mod_model.generate_unity_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.GIMI:
                    from ..games.gimi import ModModelGIMI
                    migoto_mod_model = ModModelGIMI()
                    migoto_mod_model.generate_unity_vs_config_ini()
                elif GlobalConfig.logic_name == LogicName.SRMI:
                    from ..games.srmi import ModModelSRMI
                    migoto_mod_model = ModModelSRMI()
                    migoto_mod_model.generate_unity_cs_config_ini()
                elif GlobalConfig.logic_name == LogicName.ZZMI:
                    from ..games.zzmi import ModModelZZMI
                    migoto_mod_model = ModModelZZMI(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 强兼支持
                elif GlobalConfig.logic_name == LogicName.EFMI:
                    from ..games.efmi import ModModelEFMI
                    migoto_mod_model = ModModelEFMI(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 终末地测试AEMI，到时候老外的EFMI发布之后，再开一套新逻辑兼容他们的，咱们用这个先测试
                elif GlobalConfig.logic_name == LogicName.AEMI:
                    from ..games.yysls import ModModelYYSLS
                    migoto_mod_model = ModModelYYSLS(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()
                # UnityVS
                elif GlobalConfig.logic_name == LogicName.UnityVS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()

                # AILIMIT
                elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_cs_config_ini()
                
                # UnityCPU 例如少女前线2、虚空之眼等等，绝大部分手游都是UnityCPU
                elif GlobalConfig.logic_name == LogicName.UnityCPU:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_vs_config_ini()
                
                # UnityCSM
                elif GlobalConfig.logic_name == LogicName.UnityCSM:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity(skip_buffer_export=preview_export_only)
                    migoto_mod_model.generate_unity_cs_config_ini()

                # 尘白禁区、卡拉比丘
                elif GlobalConfig.logic_name == LogicName.SnowBreak:
                    from ..games.snowbreak import ModModelSnowBreak
                    migoto_mod_model = ModModelSnowBreak()
                    migoto_mod_model.generate_ini()
                else:
                    self.report({'ERROR'},"当前逻辑暂不支持生成Mod")
                    return {'FINISHED'}
                end_operation(f"GenerateMod_Export_{export_index}")

                print(f"第 {export_index}/{max_export_count} 次导出完成")
            
            # 更新进度到 90%
            wm.progress_update(90)
            
            self.report({'INFO'},TR.translate("Generate Mod Success!"))
            TimerUtils.End("GenerateMod Mod")
            
            mod_export_path = GlobalConfig.path_generate_mod_folder()
            print(f"Mod导出路径: {mod_export_path}")
            
            start_operation("PostProcessNodes")
            BlueprintExportHelper.execute_postprocess_nodes(mod_export_path)
            end_operation("PostProcessNodes")
            
            # 完成进度
            wm.progress_update(100)
            wm.progress_end()
            
            CommandUtils.OpenGeneratedModFolder()
        finally:
            # Clean up override
            BlueprintExportHelper.forced_target_tree_name = None
            # 恢复原始导出路径
            BlueprintExportHelper.restore_export_path()
            
            if preview_export_only:
                print("[PreviewExport] 配置表预导出完成，跳过清理步骤")
            else:
                # 恢复节点引用并删除副本
                if copy_mapping:
                    print("恢复节点引用并删除三角化副本...")
                    start_operation("CleanupCopies")
                    for original_name, (copy_obj, node_or_item) in copy_mapping.items():
                        # 恢复节点/项目引用到原始物体
                        node_or_item.object_name = original_name
                        
                        # 删除副本
                        if copy_obj:
                            mesh_data = copy_obj.data
                            bpy.data.objects.remove(copy_obj, do_unlink=True)
                            if mesh_data:
                                bpy.data.meshes.remove(mesh_data, do_unlink=True)
                            
                    print(f"已清理 {len(copy_mapping)} 个三角化副本")
                    end_operation("CleanupCopies")
            
            # 打印性能报告到控制台和文本编辑器
            end_operation("GenerateMod_Total")
            print_performance_report()
            save_performance_report_to_editor("性能统计报告")
        
        return {'FINISHED'}
    
    def _get_export_objects_with_nodes(self):
        """获取当前蓝图中所有要导出的物体及其对应的节点，支持递归扫描嵌套蓝图"""
        result = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return result
        
        output_nodes = [node for node in tree.nodes if node.bl_idname == 'SSMTNode_Result_Output']
        
        if not output_nodes:
            return result
        
        valid_nodes = set()
        visited_blueprints = set()
        
        def collect_valid_nodes(node, current_tree):
            """递归收集所有有效连接的节点，包括嵌套蓝图中的节点"""
            if node in valid_nodes:
                return
            
            if node.mute:
                return
            
            valid_nodes.add(node)
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    from_node = link.from_node
                    if from_node:
                        collect_valid_nodes(from_node, current_tree)
        
        def collect_nested_blueprint_nodes(nest_node, current_tree):
            """递归收集嵌套蓝图中的所有节点"""
            blueprint_name = getattr(nest_node, 'blueprint_name', '')
            if not blueprint_name:
                return
            
            if blueprint_name in visited_blueprints:
                return
            
            visited_blueprints.add(blueprint_name)
            
            nested_tree = bpy.data.node_groups.get(blueprint_name)
            if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
                return
            
            print(f"[Blueprint Nest] 扫描嵌套蓝图: {blueprint_name}")
            
            nested_output_nodes = [n for n in nested_tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
            
            if not nested_output_nodes:
                print(f"[Blueprint Nest] 警告: 嵌套蓝图 {blueprint_name} 没有输出节点")
                return
            
            for nested_output_node in nested_output_nodes:
                collect_valid_nodes(nested_output_node, nested_tree)
            
            for nested_node in nested_tree.nodes:
                if nested_node in valid_nodes and nested_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    collect_nested_blueprint_nodes(nested_node, nested_tree)
        
        for output_node in output_nodes:
            collect_valid_nodes(output_node, tree)
        
        for node in tree.nodes:
            if node not in valid_nodes:
                continue
            if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                collect_nested_blueprint_nodes(node, tree)
        
        for node in valid_nodes:
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.type == 'MESH':
                        result.append((obj, node))
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj and obj.type == 'MESH':
                            result.append((obj, item))
        
        print(f"[Blueprint Nest] 共扫描 {len(visited_blueprints)} 个嵌套蓝图，找到 {len(result)} 个物体")
        return result
    
    def _sequential_preprocess(self, obj_node_mapping, mirror_workflow_enabled, wm, total_objects, blend_file=None):
        """
        顺序预处理（单进程模式，支持缓存）
        
        Args:
            obj_node_mapping: 物体-节点映射列表
            mirror_workflow_enabled: 是否启用非镜像工作流
            wm: window_manager
            total_objects: 物体总数
            blend_file: blend 文件路径（用于缓存目录）
        
        Returns:
            copy_mapping: {原始物体名: (副本物体, 节点/项目)}
        """
        from ..utils.obj_utils import mesh_triangulate_beauty
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        
        cache_manager = get_cache_manager(blend_file)
        use_cache = Properties_ImportModel.use_preprocess_cache() if hasattr(Properties_ImportModel, 'use_preprocess_cache') else True
        
        copy_mapping = {}
        cache_hits = 0
        cache_misses = 0
        
        print(f"开始创建三角化副本（缓存: {'启用' if use_cache else '禁用'}）...")
        
        for i, (original_obj, node_or_item) in enumerate(obj_node_mapping):
            progress = int((i + 1) / total_objects * 50)
            wm.progress_update(progress)
            
            if original_obj and original_obj.type == 'MESH':
                obj_name = original_obj.name
                
                fingerprint = FingerprintCalculator.calculate_fingerprint(original_obj, mirror_workflow_enabled)
                print(f"[Cache] 物体 {obj_name} 指纹: v={fingerprint.vertex_count}, vh={fingerprint.vertex_hash[:8]}...")
                
                original_name = original_obj.name
                if original_name.endswith("-Original"):
                    copy_name = original_name.replace("-Original", "-copy_Original")
                else:
                    copy_name = f"{original_name}_copy"
                
                copy_obj = None
                cache_used = False
                
                if use_cache:
                    start_operation("CacheCheck", obj_name)
                    cached_obj = cache_manager.load_cache(obj_name, fingerprint, bpy.context.scene)
                    end_operation("CacheCheck")
                    
                    if cached_obj:
                        cached_obj.name = copy_name
                        copy_obj = cached_obj
                        cache_used = True
                        cache_hits += 1
                        print(f"[Cache] 命中: {obj_name}")
                
                if not copy_obj:
                    cache_misses += 1
                    
                    start_operation("CreateCopy", obj_name)
                    copy_obj = original_obj.copy()
                    copy_obj.data = original_obj.data.copy()
                    end_operation("CreateCopy")
                    
                    start_operation("LinkCopy", obj_name)
                    copy_obj.name = copy_name
                    bpy.context.scene.collection.objects.link(copy_obj)
                    end_operation("LinkCopy")
                    
                    has_armature = any(mod.type == 'ARMATURE' for mod in copy_obj.modifiers)
                    
                    if mirror_workflow_enabled:
                        start_operation("MirrorWorkflow_Pre", obj_name)
                        ObjUtils.prepare_copy_for_mirror_workflow(copy_obj)
                        end_operation("MirrorWorkflow_Pre")
                    elif has_armature:
                        start_operation("ApplyArmature", obj_name)
                        ObjUtils._apply_all_modifiers(copy_obj)
                        end_operation("ApplyArmature")
                    
                    start_operation("Triangulate", obj_name)
                    mesh_triangulate_beauty(copy_obj)
                    end_operation("Triangulate")
                    
                    if mirror_workflow_enabled:
                        start_operation("MirrorWorkflow_Post", obj_name)
                        ObjUtils.apply_mirror_transform(copy_obj)
                        ObjUtils.flip_face_normals(copy_obj)
                        end_operation("MirrorWorkflow_Post")
                    
                    if use_cache:
                        start_operation("CacheStore", obj_name)
                        cache_manager.store_cache(obj_name, fingerprint, copy_obj)
                        end_operation("CacheStore")
                
                node_or_item.original_object_name = original_name
                copy_mapping[original_name] = (copy_obj, node_or_item)
                
                if not cache_used:
                    print(f"创建副本: {original_name} -> {copy_obj.name}")
        
        print(f"[Cache] 统计: 命中={cache_hits}, 未命中={cache_misses}")
        
        if copy_mapping:
            self._execute_processing_chain_for_objects(copy_mapping, tree)
        
        return copy_mapping
    
    def _execute_processing_chain_for_objects(self, copy_mapping, tree):
        """
        按处理链顺序执行所有处理节点（支持多线程）
        
        逻辑：
        1. 收集所有处理节点（顶点组处理节点和名称修改节点），按连接顺序排序
        2. 对于每个处理节点，收集所有连接到它的物体
        3. 按顺序执行每个处理节点
        4. 对于顶点组处理节点，使用多线程处理多个物体
        """
        all_process_nodes = []
        visited = set()
        
        def collect_all_process_nodes(node, current_tree):
            """从输出节点开始，收集所有处理节点（顶点组处理节点和名称修改节点）"""
            if node in visited:
                return
            visited.add(node)
            
            if node.bl_idname == 'SSMTNode_VertexGroupProcess':
                all_process_nodes.append((node, 'vg_process'))
            elif node.bl_idname == 'SSMTNode_Object_Name_Modify':
                all_process_nodes.append((node, 'name_modify'))
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    collect_all_process_nodes(link.from_node, current_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_all_process_nodes(output_node, tree)
        
        all_process_nodes.reverse()
        
        print(f"[ProcessingChain] 收集到 {len(all_process_nodes)} 个处理节点")
        
        for node, node_type in all_process_nodes:
            connected_objects = []
            for original_name, (copy_obj, node_or_item) in copy_mapping.items():
                if self._is_object_connected_to_node(original_name, node, tree):
                    connected_objects.append((original_name, copy_obj, node_or_item))
            
            if not connected_objects:
                continue
            
            if node_type == 'name_modify':
                for original_name, copy_obj, node_or_item in connected_objects:
                    if hasattr(node, 'is_valid') and node.is_valid():
                        current_name = copy_obj.name
                        new_name = node.get_modified_object_name(current_name)
                        if new_name != current_name:
                            copy_obj.name = new_name
                            if hasattr(node_or_item, 'original_object_name'):
                                clean_name = new_name.rstrip('_copy') if new_name.endswith('_copy') else new_name
                                node_or_item.original_object_name = clean_name
                                print(f"[NameModify] {original_name}: {current_name} -> {new_name} (INI: {clean_name})")
            
            elif node_type == 'vg_process':
                start_operation(f"VGProcess_{node.name}", "batch")
                
                objects_to_process = [copy_obj for _, copy_obj, _ in connected_objects]
                
                if len(objects_to_process) > 1:
                    print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objects_to_process)} 个物体")
                    try:
                        all_stats = node.process_objects_batch(objects_to_process, max_workers=4)
                        for obj_name, stats in all_stats.items():
                            if any(v > 0 for v in stats.values()):
                                print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                    except Exception as e:
                        print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                        import traceback
                        traceback.print_exc()
                else:
                    for original_name, copy_obj, _ in connected_objects:
                        try:
                            stats = node.process_object(copy_obj)
                            if any(v > 0 for v in stats.values()):
                                print(f"[VGProcess] {original_name} 节点 {node.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                        except Exception as e:
                            print(f"[VGProcess] 处理物体 {original_name} 时出错: {e}")
                            import traceback
                            traceback.print_exc()
                
                end_operation(f"VGProcess_{node.name}")
        
        for original_name, (copy_obj, node_or_item) in copy_mapping.items():
            node_or_item.object_name = copy_obj.name
    
    def _parallel_preprocess(self, context, obj_node_mapping, mirror_workflow_enabled):
        """
        并行预处理（多进程模式，支持缓存）
        
        仅处理第3步：模型预处理
        预处理完成后将结果加载回当前场景继续后续流程
        
        Args:
            context: Blender 上下文
            obj_node_mapping: 物体-节点映射列表
            mirror_workflow_enabled: 是否启用非镜像工作流
        
        Returns:
            copy_mapping: {原始物体名: (副本物体, 节点/项目)}
        """
        from ..utils.parallel_preprocess import ParallelPreprocessManager, load_preprocessed_objects
        
        wm = context.window_manager
        blend_file = bpy.data.filepath
        
        cache_manager = get_cache_manager(blend_file)
        use_cache = Properties_ImportModel.use_preprocess_cache() if hasattr(Properties_ImportModel, 'use_preprocess_cache') else True
        
        object_names = [obj.name for obj, _ in obj_node_mapping if obj]
        node_mapping = {obj.name: (obj, node) for obj, node in obj_node_mapping if obj}
        
        cached_objects = {}
        objects_to_process = []
        fingerprints = {}
        manager = None
        loaded_objects = None
        
        if use_cache:
            print(f"[ParallelPreprocess] 检查缓存...")
            for obj_name in object_names:
                original_obj = node_mapping[obj_name][0]
                fingerprint = FingerprintCalculator.calculate_fingerprint(original_obj, mirror_workflow_enabled)
                fingerprints[obj_name] = fingerprint
                
                cached_obj = cache_manager.load_cache(obj_name, fingerprint, bpy.context.scene)
                if cached_obj:
                    cached_objects[obj_name] = cached_obj
                    print(f"[Cache] 命中: {obj_name}")
                else:
                    objects_to_process.append(obj_name)
            
            print(f"[Cache] 统计: 命中={len(cached_objects)}, 未命中={len(objects_to_process)}")
        else:
            objects_to_process = object_names[:]
        
        if objects_to_process:
            num_workers = Properties_ImportModel.get_parallel_worker_count()
            manager = ParallelPreprocessManager(num_workers=num_workers)
            
            def progress_callback(progress):
                wm.progress_update(int(progress * 0.5 * len(objects_to_process) / len(object_names)))
            
            print(f"[ParallelPreprocess] 开始并行预处理 {len(objects_to_process)} 个物体...")
            print(f"[ParallelPreprocess] 工作进程数: {num_workers}")
            
            start_operation("CollectVGMapping")
            vg_mapping_texts = self._collect_vg_mapping_texts()
            print(f"[ParallelPreprocess] 收集到 {len(vg_mapping_texts)} 个映射表")
            end_operation("CollectVGMapping")
            
            object_blend_map = manager.preprocess_parallel(
                blend_file=blend_file,
                object_names=objects_to_process,
                mirror_workflow=mirror_workflow_enabled,
                vg_mapping_texts=vg_mapping_texts,
                progress_callback=progress_callback
            )
            
            if not object_blend_map:
                manager.cleanup()
                if cached_objects:
                    pass
                else:
                    return None
            
            if object_blend_map:
                wm.progress_update(45)
                print(f"[ParallelPreprocess] 加载预处理结果...")
                
                try:
                    start_operation("LoadPreprocessedObjects")
                    loaded_objects = load_preprocessed_objects(object_blend_map)
                    print(f"[ParallelPreprocess] loaded_objects: {list(loaded_objects.keys()) if loaded_objects else 'None'}")
                    end_operation("LoadPreprocessedObjects")
                except Exception as e:
                    print(f"[ParallelPreprocess] 加载失败: {e}")
                    import traceback
                    traceback.print_exc()
                    manager.cleanup()
                    if not cached_objects:
                        return None
                    loaded_objects = {}
                
                if use_cache and loaded_objects:
                    print(f"[ParallelPreprocess] 存储缓存...")
                    for obj_name in objects_to_process:
                        if obj_name in fingerprints:
                            original_name = obj_name
                            if original_name.endswith("-Original"):
                                copy_name = original_name.replace("-Original", "-copy_Original")
                            else:
                                copy_name = f"{original_name}_copy"
                            
                            if copy_name in loaded_objects:
                                cache_manager.store_cache(obj_name, fingerprints[obj_name], loaded_objects[copy_name])
                
                manager.cleanup()
        else:
            print(f"[ParallelPreprocess] 所有物体都命中缓存，跳过并行预处理")
        
        wm.progress_update(50)
        
        copy_mapping = {}
        for original_name, (original_obj, node_or_item) in node_mapping.items():
            if original_name.endswith("-Original"):
                copy_name = original_name.replace("-Original", "-copy_Original")
            else:
                copy_name = f"{original_name}_copy"
            
            copy_obj = None
            
            if original_name in cached_objects:
                cached_obj = cached_objects[original_name]
                cached_obj.name = copy_name
                copy_obj = cached_obj
            
            if copy_obj is None and loaded_objects:
                if copy_name in loaded_objects:
                    copy_obj = loaded_objects[copy_name]
            
            if copy_obj:
                
                node_or_item.original_object_name = original_name
                copy_mapping[original_name] = (copy_obj, node_or_item)
                
                print(f"[ParallelPreprocess] 加载预处理结果: {original_name} -> {copy_obj.name}")
            else:
                print(f"[ParallelPreprocess] 警告: 副本 {copy_name} 未在预处理结果中找到")
        
        if not copy_mapping:
            print(f"[ParallelPreprocess] copy_mapping 为空，加载失败")
            manager.cleanup()
            return None
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        
        print(f"[ParallelPreprocess] 开始按处理链执行...")
        
        if copy_mapping:
            self._execute_processing_chain_for_objects(copy_mapping, tree)
        
        if manager:
            start_operation("ParallelCleanup")
            manager.cleanup()
            end_operation("ParallelCleanup")
        wm.progress_update(50)
        
        return copy_mapping
    
    def _get_export_objects(self):
        """获取当前蓝图中所有要导出的物体"""
        objects = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return objects
        
        for node in tree.nodes:
            if node.mute:
                continue
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.type == 'MESH':
                        objects.append(obj)
        
        return objects
    
    def _get_vg_process_nodes(self):
        """获取当前蓝图中所有顶点组处理节点，按照连接顺序排序"""
        nodes = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return nodes
        
        visited_blueprints = set()
        visited_nodes = set()
        
        def collect_vg_process_nodes_in_order(current_node, current_tree):
            """按照连接顺序递归收集顶点组处理节点"""
            if current_node in visited_nodes:
                return
            visited_nodes.add(current_node)
            
            if current_node.mute:
                return
            
            if current_node.bl_idname == 'SSMTNode_VertexGroupProcess':
                nodes.append(current_node)
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name and blueprint_name not in visited_blueprints:
                    visited_blueprints.add(blueprint_name)
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        nested_output = None
                        for n in nested_tree.nodes:
                            if n.bl_idname == 'SSMTNode_Result_Output':
                                nested_output = n
                                break
                        if nested_output:
                            collect_vg_process_nodes_in_order(nested_output, nested_tree)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    collect_vg_process_nodes_in_order(link.from_node, current_tree)
        
        for output_node in tree.nodes:
            if output_node.bl_idname == 'SSMTNode_Result_Output':
                collect_vg_process_nodes_in_order(output_node, tree)
                break
        
        nodes.reverse()
        
        print(f"[VGProcess] 收集到 {len(nodes)} 个顶点组处理节点，顺序: {[n.name for n in nodes]}")
        return nodes
    
    def _collect_vg_mapping_texts(self):
        """收集所有顶点组映射表文本内容"""
        mapping_texts = {}
        
        for text in bpy.data.texts:
            if text.name.startswith('VG_Match_'):
                content = '\n'.join(line.body for line in text.lines)
                mapping_texts[text.name] = content
        
        return mapping_texts
    
    def _get_name_modify_nodes(self):
        """获取所有名称修改节点（按照连接顺序）"""
        result = []
        
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return result
        
        visited = set()
        
        def collect_name_modify_nodes_in_order(node, current_tree):
            """按照连接顺序收集名称修改节点"""
            if node in visited:
                return
            visited.add(node)
            
            # 如果是名称修改节点，添加到结果中
            if node.bl_idname == 'SSMTNode_Object_Name_Modify':
                result.append(node)
                print(f"[NameModify] 找到名称修改节点: {node.name}")
            
            # 递归检查连接的节点
            for input_socket in node.inputs:
                if input_socket.is_linked:
                    for link in input_socket.links:
                        from_node = link.from_node
                        collect_name_modify_nodes_in_order(from_node, current_tree)
        
        def collect_nested_blueprint_nodes(nest_node, current_tree):
            """递归收集嵌套蓝图中的名称修改节点"""
            blueprint_name = getattr(nest_node, 'blueprint_name', '')
            if not blueprint_name:
                return
            
            if blueprint_name in visited:
                return
            
            visited.add(blueprint_name)
            
            nested_tree = bpy.data.node_groups.get(blueprint_name)
            if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
                return
            
            print(f"[NameModify] 扫描嵌套蓝图: {blueprint_name}")
            
            nested_output_nodes = [n for n in nested_tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
            
            if not nested_output_nodes:
                print(f"[NameModify] 警告: 嵌套蓝图 {blueprint_name} 没有输出节点")
                return
            
            for nested_output_node in nested_output_nodes:
                collect_name_modify_nodes_in_order(nested_output_node, nested_tree)
            
            for nested_node in nested_tree.nodes:
                if nested_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    collect_nested_blueprint_nodes(nested_node, nested_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_name_modify_nodes_in_order(output_node, tree)
        
        for node in tree.nodes:
            if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                collect_nested_blueprint_nodes(node, tree)
        
        # 反转结果，因为是从输出节点开始递归的，所以需要反转顺序
        result.reverse()
        
        print(f"[NameModify] 共找到 {len(result)} 个名称修改节点，顺序: {[n.name for n in result]}")
        return result
    
    def _get_vg_process_nodes_for_object(self, obj_name, vg_process_nodes):
        """获取应该应用于指定物体的顶点组处理节点列表"""
        result = []
        
        for node in vg_process_nodes:
            node_tree = node.id_data
            is_connected = self._is_object_connected_to_vg_process(obj_name, node, node_tree)
            print(f"[VGProcess] 检查节点 {node.name} 是否连接到物体 {obj_name}: {is_connected}")
            if is_connected:
                result.append(node)
        
        return result
    
    def _is_object_connected_to_vg_process(self, obj_name, vg_process_node, node_tree):
        """检查物体是否连接到指定的顶点组处理节点（支持嵌套蓝图）"""
        visited = set()
        
        def find_all_object_names_for_vg_process(current_node, current_tree, depth=0):
            """从顶点组处理节点开始，找到所有连接的物体名称"""
            if current_node in visited:
                return []
            visited.add(current_node)
            
            indent = "  " * depth
            print(f"[VGProcess]{indent} 搜索节点: {current_node.name} (类型: {current_node.bl_idname})")
            
            object_names = []
            
            if current_node.bl_idname == 'SSMTNode_Object_Info':
                found_name = getattr(current_node, 'object_name', '')
                if found_name:
                    print(f"[VGProcess]{indent} 找到物体节点: {found_name}")
                    return [found_name]
            
            elif current_node.bl_idname == 'SSMTNode_MultiFile_Export':
                object_list = getattr(current_node, 'object_list', [])
                for item in object_list:
                    item_name = getattr(item, 'object_name', '')
                    if item_name:
                        object_names.append(item_name)
                if object_names:
                    print(f"[VGProcess]{indent} 找到多文件导出节点，包含 {len(object_names)} 个物体")
                    return object_names
            
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                names = find_all_object_names_for_vg_process(nested_node, nested_tree, depth+1)
                                object_names.extend(names)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    names = find_all_object_names_for_vg_process(link.from_node, current_tree, depth+1)
                    object_names.extend(names)
            
            return object_names
        
        def get_connected_object_names(vg_node, tree):
            """获取顶点组处理节点连接的所有物体名称"""
            object_names = []
            for input_socket in vg_node.inputs:
                if input_socket.name == "物体" and input_socket.is_linked:
                    for link in input_socket.links:
                        from_node = link.from_node
                        print(f"[VGProcess] 物体输入连接到: {from_node.name} (类型: {from_node.bl_idname})")
                        names = find_all_object_names_for_vg_process(from_node, tree, 1)
                        object_names.extend(names)
            return list(set(object_names))
        
        connected_objects = get_connected_object_names(vg_process_node, node_tree)
        print(f"[VGProcess] 顶点组处理节点 '{vg_process_node.name}' 连接的物体: {connected_objects}")
        
        return obj_name in connected_objects
    
    def _get_processing_chain_for_object(self, obj_name, tree):
        """
        获取指定物体经过的处理链（按连接顺序）
        返回: [(节点, 节点类型), ...] 其中节点类型为 'name_modify' 或 'vg_process'
        
        新逻辑：从输出节点开始反向收集所有处理节点，然后过滤出连接到当前物体的节点
        """
        result = []
        visited = set()
        all_process_nodes = []
        
        def collect_all_process_nodes(node, current_tree):
            """从输出节点开始，收集所有处理节点（顶点组处理节点和名称修改节点）"""
            if node in visited:
                return
            visited.add(node)
            
            if node.bl_idname == 'SSMTNode_VertexGroupProcess':
                all_process_nodes.append((node, 'vg_process'))
            elif node.bl_idname == 'SSMTNode_Object_Name_Modify':
                all_process_nodes.append((node, 'name_modify'))
            
            for input_socket in node.inputs:
                for link in input_socket.links:
                    collect_all_process_nodes(link.from_node, current_tree)
        
        output_nodes = [n for n in tree.nodes if n.bl_idname == 'SSMTNode_Result_Output']
        for output_node in output_nodes:
            collect_all_process_nodes(output_node, tree)
        
        all_process_nodes.reverse()
        
        for node, node_type in all_process_nodes:
            if self._is_object_connected_to_node(obj_name, node, tree):
                result.append((node, node_type))
        
        print(f"[ProcessingChain] 物体 {obj_name} 的处理链: {[(n.name, t) for n, t in result]}")
        return result
    
    def _is_object_connected_to_node(self, obj_name, target_node, node_tree):
        """检查物体是否连接到指定的节点（支持嵌套蓝图）"""
        visited = set()
        
        def find_all_object_names(current_node, current_tree, depth=0):
            """从节点开始，找到所有连接的物体名称"""
            if current_node in visited:
                return []
            visited.add(current_node)
            
            object_names = []
            
            if current_node.bl_idname == 'SSMTNode_Object_Info':
                found_name = getattr(current_node, 'object_name', '')
                if found_name:
                    return [found_name]
            
            elif current_node.bl_idname == 'SSMTNode_MultiFile_Export':
                object_list = getattr(current_node, 'object_list', [])
                for item in object_list:
                    item_name = getattr(item, 'object_name', '')
                    if item_name:
                        object_names.append(item_name)
                if object_names:
                    return object_names
            
            elif current_node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(current_node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                names = find_all_object_names(nested_node, nested_tree, depth+1)
                                object_names.extend(names)
            
            for input_socket in current_node.inputs:
                for link in input_socket.links:
                    names = find_all_object_names(link.from_node, current_tree, depth+1)
                    object_names.extend(names)
            
            return object_names
        
        object_names = find_all_object_names(target_node, node_tree)
        return obj_name in object_names
    
    def _apply_vg_process_nodes(self, obj, vg_process_nodes):
        """应用顶点组处理节点到物体"""
        if not vg_process_nodes or not obj or obj.type != 'MESH':
            return
        
        applicable_nodes = self._get_vg_process_nodes_for_object(obj.name, vg_process_nodes)
        
        for i, node in enumerate(applicable_nodes):
            try:
                start_operation(f"VGProcess_{node.name}", obj.name)
                stats = node.process_object(obj)
                if any(v > 0 for v in stats.values()):
                    print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                end_operation(f"VGProcess_{node.name}")
            except Exception as e:
                print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                import traceback
                traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
    
    def _apply_vg_process_batch(self, pending_tasks, max_workers=4):
        """批量处理顶点组任务（多线程优化版）
        
        Args:
            pending_tasks: [(obj, node), ...] 待处理的物体-节点对
            max_workers: 最大线程数
        """
        if not pending_tasks:
            return
        
        node_to_objects = {}
        for obj, node in pending_tasks:
            if node not in node_to_objects:
                node_to_objects[node] = []
            node_to_objects[node].append(obj)
        
        for node, objs in node_to_objects.items():
            if len(objs) > 1:
                print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objs)} 个物体")
                try:
                    all_stats = node.process_objects_batch(objs, max_workers=max_workers)
                    for obj_name, stats in all_stats.items():
                        if any(v > 0 for v in stats.values()):
                            print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
            elif len(objs) == 1:
                obj = objs[0]
                try:
                    stats = node.process_object(obj)
                    if any(v > 0 for v in stats.values()):
                        print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
    
    def _apply_vg_process_nodes_batch(self, objects, vg_process_nodes, max_workers=4):
        """批量应用顶点组处理节点到多个物体（多线程优化版）"""
        if not vg_process_nodes or not objects:
            return
        
        mesh_objects = [obj for obj in objects if obj and obj.type == 'MESH']
        if not mesh_objects:
            return
        
        print(f"[VGProcess] 开始批量处理 {len(mesh_objects)} 个网格物体（多线程模式）")
        
        node_to_objects = {}
        for obj in mesh_objects:
            applicable_nodes = self._get_vg_process_nodes_for_object(obj.name, vg_process_nodes)
            for node in applicable_nodes:
                if node not in node_to_objects:
                    node_to_objects[node] = []
                node_to_objects[node].append(obj)
        
        for node, objs in node_to_objects.items():
            if len(objs) > 1:
                print(f"[VGProcess] 节点 {node.name}: 多线程处理 {len(objs)} 个物体")
                start_operation(f"VGProcess_{node.name}", "batch")
                try:
                    all_stats = node.process_objects_batch(objs, max_workers=max_workers)
                    for obj_name, stats in all_stats.items():
                        if any(v > 0 for v in stats.values()):
                            print(f"[VGProcess] {obj_name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[VGProcess] 批量处理节点 {node.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
            elif len(objs) == 1:
                obj = objs[0]
                start_operation(f"VGProcess_{node.name}", obj.name)
                try:
                    stats = node.process_object(obj)
                    if any(v > 0 for v in stats.values()):
                        print(f"[VGProcess] {obj.name}: 重命名={stats['renamed']}, 合并={stats['merged']}, 清理={stats['cleaned']}, 填充={stats['filled']}")
                except Exception as e:
                    print(f"[Process] 处理物体 {obj.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
                end_operation(f"VGProcess_{node.name}")
    

class SSMTQuickPartialExport(bpy.types.Operator):
    bl_idname = "ssmt.quick_partial_export"
    bl_label = TR.translate("快速局部导出")
    bl_description = "对当前选中的物体进行快速导出，自动创建临时蓝图架构"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'WARNING'}, "请先选择要导出的网格物体")
            return {'CANCELLED'}
        
        print(f"[QuickExport] 开始快速局部导出，选中物体数量: {len(selected_objects)}")
        
        GlobalConfig.read_from_main_json()
        
        temp_tree_name = f"_QuickExport_Temp_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "_QuickExport_Temp"
        
        temp_tree = bpy.data.node_groups.get(temp_tree_name)
        if temp_tree:
            bpy.data.node_groups.remove(temp_tree)
        
        temp_tree = bpy.data.node_groups.new(name=temp_tree_name, type='SSMTBlueprintTreeType')
        temp_tree.use_fake_user = False
        
        try:
            output_node = temp_tree.nodes.new('SSMTNode_Result_Output')
            output_node.location = (600, 0)
            
            obj_nodes = []
            y_offset = 0
            
            for obj in selected_objects:
                obj_node = temp_tree.nodes.new('SSMTNode_Object_Info')
                obj_node.object_name = obj.name
                obj_node.location = (0, y_offset)
                obj_nodes.append(obj_node)
                y_offset -= 200
            
            if len(obj_nodes) == 1:
                temp_tree.links.new(obj_nodes[0].outputs[0], output_node.inputs[0])
            else:
                group_node = temp_tree.nodes.new('SSMTNode_Object_Group')
                group_node.location = (300, 0)
                
                for i, obj_node in enumerate(obj_nodes):
                    while len(group_node.inputs) <= i:
                        group_node.inputs.new('SSMTSocketObject', f"Input {len(group_node.inputs) + 1}")
                    temp_tree.links.new(obj_node.outputs[0], group_node.inputs[i])
                
                temp_tree.links.new(group_node.outputs[0], output_node.inputs[0])
            
            print(f"[QuickExport] 临时蓝图树创建完成: {temp_tree_name}")
            print(f"[QuickExport] 节点数量: {len(temp_tree.nodes)}, 连接数量: {len(temp_tree.links)}")
            
            bpy.ops.ssmt.generate_mod_blueprint(node_tree_name=temp_tree_name)
            
            self.report({'INFO'}, f"已导出 {len(selected_objects)} 个物体")
            
        except Exception as e:
            print(f"[QuickExport] 导出失败: {e}")
            import traceback
            traceback.print_exc()
            self.report({'ERROR'}, f"导出失败: {e}")
            
        finally:
            if temp_tree:
                try:
                    bpy.data.node_groups.remove(temp_tree)
                    print(f"[QuickExport] 已清理临时蓝图树: {temp_tree_name}")
                except Exception as e:
                    print(f"[QuickExport] 清理临时蓝图树失败: {e}")
        
        return {'FINISHED'}


def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)
    bpy.utils.register_class(SSMTSelectGenerateModFolder)
    bpy.utils.register_class(SSMTQuickPartialExport)
    bpy.utils.register_class(SSMTClearPreprocessCache)


def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)
    bpy.utils.unregister_class(SSMTSelectGenerateModFolder)
    bpy.utils.unregister_class(SSMTQuickPartialExport)
    bpy.utils.unregister_class(SSMTClearPreprocessCache)

