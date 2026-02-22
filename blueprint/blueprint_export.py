import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils
from ..utils.obj_utils import ObjUtils

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



class SSMTGenerateModBlueprint(bpy.types.Operator):
    bl_idname = "ssmt.generate_mod_blueprint"
    bl_label = TR.translate("生成Mod(蓝图架构)")
    bl_description = "根据当前工作空间对应的蓝图架构生成对应的Mod文件"
    bl_options = {'REGISTER','UNDO'}

    # 允许通过属性传入指定的蓝图树名称
    node_tree_name: bpy.props.StringProperty(name="Node Tree Name", default="") # type: ignore

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")
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
        obj_node_mapping = self._get_export_objects_with_nodes()
        total_objects = len(obj_node_mapping)
        
        if total_objects == 0:
            self.report({'WARNING'}, "没有找到要导出的物体")
            return {'CANCELLED'}
        
        use_parallel = Properties_ImportModel.use_parallel_export()
        blend_file_saved = bpy.data.is_saved
        blend_file_dirty = bpy.data.is_dirty
        mirror_workflow_enabled = Properties_ImportModel.use_mirror_workflow()
        
        if use_parallel:
            if not blend_file_saved:
                self.report({'ERROR'}, "并行导出需要先保存项目文件")
                return {'CANCELLED'}
            if blend_file_dirty:
                self.report({'ERROR'}, "项目有未保存的修改，请先保存后再进行并行导出")
                return {'CANCELLED'}
        
        wm.progress_begin(0, 100)
        wm.progress_update(0)
        print(f"开始处理 {total_objects} 个物体...")
        
        copy_mapping = {}
        
        if use_parallel and blend_file_saved and not blend_file_dirty and total_objects >= 4:
            print(f"[ParallelPreprocess] 启用并行预处理，物体数量: {total_objects}")
            copy_mapping = self._parallel_preprocess(context, obj_node_mapping, mirror_workflow_enabled)
            if not copy_mapping:
                print("[ParallelPreprocess] 并行预处理失败，回退到单进程模式")
                copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects)
        else:
            copy_mapping = self._sequential_preprocess(obj_node_mapping, mirror_workflow_enabled, wm, total_objects)
        
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
                    migoto_mod_model = ModModelZZMI()
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 强兼支持
                elif GlobalConfig.logic_name == LogicName.EFMI:
                    from ..games.efmi import ModModelEFMI
                    migoto_mod_model = ModModelEFMI()
                    migoto_mod_model.generate_unity_vs_config_ini()

                # 终末地测试AEMI，到时候老外的EFMI发布之后，再开一套新逻辑兼容他们的，咱们用这个先测试
                elif GlobalConfig.logic_name == LogicName.AEMI:
                    from ..games.yysls import ModModelYYSLS
                    migoto_mod_model = ModModelYYSLS()
                    migoto_mod_model.generate_unity_vs_config_ini()
                # UnityVS
                elif GlobalConfig.logic_name == LogicName.UnityVS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity()
                    migoto_mod_model.generate_unity_vs_config_ini()

                # AILIMIT
                elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity()
                    migoto_mod_model.generate_unity_cs_config_ini()
                
                # UnityCPU 例如少女前线2、虚空之眼等等，绝大部分手游都是UnityCPU
                elif GlobalConfig.logic_name == LogicName.UnityCPU:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity()
                    migoto_mod_model.generate_unity_vs_config_ini()
                
                # UnityCSM
                elif GlobalConfig.logic_name == LogicName.UnityCSM:
                    from ..games.unity import ModModelUnity
                    migoto_mod_model = ModModelUnity()
                    migoto_mod_model.generate_unity_cs_config_ini()

                # 尘白禁区、卡拉比丘
                elif GlobalConfig.logic_name == LogicName.SnowBreak:
                    from ..games.snowbreak import ModModelSnowBreak
                    migoto_mod_model = ModModelSnowBreak()
                    migoto_mod_model.generate_ini()
                else:
                    self.report({'ERROR'},"当前逻辑暂不支持生成Mod")
                    return {'FINISHED'}

                print(f"第 {export_index}/{max_export_count} 次导出完成")
            
            # 更新进度到 90%
            wm.progress_update(90)
            
            self.report({'INFO'},TR.translate("Generate Mod Success!"))
            TimerUtils.End("GenerateMod Mod")
            
            mod_export_path = GlobalConfig.path_generate_mod_folder()
            print(f"Mod导出路径: {mod_export_path}")
            
            BlueprintExportHelper.execute_postprocess_nodes(mod_export_path)
            
            # 完成进度
            wm.progress_update(100)
            wm.progress_end()
            
            CommandUtils.OpenGeneratedModFolder()
        finally:
            # Clean up override
            BlueprintExportHelper.forced_target_tree_name = None
            # 恢复原始导出路径
            BlueprintExportHelper.restore_export_path()
            
            # 恢复节点引用并删除副本
            if copy_mapping:
                print("恢复节点引用并删除三角化副本...")
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
            
        return {'FINISHED'}
    
    def _get_export_objects_with_nodes(self):
        """获取当前蓝图中所有要导出的物体及其对应的节点"""
        result = []
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return result
        
        for node in tree.nodes:
            if node.mute:
                continue
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj and obj.type == 'MESH':
                        result.append((obj, node))
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                # 处理多文件导出节点中的所有物体
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj and obj.type == 'MESH':
                            result.append((obj, item))
        
        return result
    
    def _sequential_preprocess(self, obj_node_mapping, mirror_workflow_enabled, wm, total_objects):
        """
        顺序预处理（单进程模式）
        
        Args:
            obj_node_mapping: 物体-节点映射列表
            mirror_workflow_enabled: 是否启用非镜像工作流
            wm: window_manager
            total_objects: 物体总数
        
        Returns:
            copy_mapping: {原始物体名: (副本物体, 节点/项目)}
        """
        from ..utils.obj_utils import mesh_triangulate_beauty
        
        copy_mapping = {}
        print(f"开始创建三角化副本...")
        
        for i, (original_obj, node_or_item) in enumerate(obj_node_mapping):
            progress = int((i + 1) / total_objects * 50)
            wm.progress_update(progress)
            
            if original_obj and original_obj.type == 'MESH':
                copy_obj = original_obj.copy()
                copy_obj.data = original_obj.data.copy()
                
                original_name = original_obj.name
                if original_name.endswith("-Original"):
                    copy_obj.name = original_name.replace("-Original", "-copy_Original")
                else:
                    copy_obj.name = f"{original_name}_copy"
                
                bpy.context.scene.collection.objects.link(copy_obj)
                
                if mirror_workflow_enabled:
                    print(f"非镜像工作流：对副本 {copy_obj.name} 进行前处理")
                    ObjUtils.prepare_copy_for_mirror_workflow(copy_obj)
                
                mesh_triangulate_beauty(copy_obj)
                
                if mirror_workflow_enabled:
                    print(f"非镜像工作流：对副本 {copy_obj.name} 应用镜像变换")
                    ObjUtils.apply_mirror_transform(copy_obj)
                    ObjUtils.flip_face_normals(copy_obj)
                
                node_or_item.original_object_name = original_name
                copy_mapping[original_name] = (copy_obj, node_or_item)
                node_or_item.object_name = copy_obj.name
                print(f"创建副本: {original_name} -> {copy_obj.name}")
        
        return copy_mapping
    
    def _parallel_preprocess(self, context, obj_node_mapping, mirror_workflow_enabled):
        """
        并行预处理（多进程模式）
        
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
        
        object_names = [obj.name for obj, _ in obj_node_mapping if obj]
        node_mapping = {obj.name: (obj, node) for obj, node in obj_node_mapping if obj}
        
        num_workers = Properties_ImportModel.get_parallel_worker_count()
        manager = ParallelPreprocessManager(num_workers=num_workers)
        
        def progress_callback(progress):
            wm.progress_update(int(progress * 0.5))
        
        print(f"[ParallelPreprocess] 开始并行预处理...")
        print(f"[ParallelPreprocess] 工作进程数: {num_workers}")
        
        object_blend_map = manager.preprocess_parallel(
            blend_file=blend_file,
            object_names=object_names,
            mirror_workflow=mirror_workflow_enabled,
            progress_callback=progress_callback
        )
        
        if not object_blend_map:
            manager.cleanup()
            return None
        
        wm.progress_update(50)
        print(f"[ParallelPreprocess] 加载预处理结果...")
        print(f"[ParallelPreprocess] object_blend_map: {object_blend_map}")
        
        try:
            loaded_objects = load_preprocessed_objects(object_blend_map)
            print(f"[ParallelPreprocess] loaded_objects: {list(loaded_objects.keys()) if loaded_objects else 'None'}")
        except Exception as e:
            print(f"[ParallelPreprocess] 加载失败: {e}")
            import traceback
            traceback.print_exc()
            manager.cleanup()
            return None
        
        copy_mapping = {}
        for original_name, (original_obj, node_or_item) in node_mapping.items():
            if original_name.endswith("-Original"):
                copy_name = original_name.replace("-Original", "-copy_Original")
            else:
                copy_name = f"{original_name}_copy"
            
            if copy_name in loaded_objects:
                copy_obj = loaded_objects[copy_name]
                
                node_or_item.original_object_name = original_name
                copy_mapping[original_name] = (copy_obj, node_or_item)
                node_or_item.object_name = copy_obj.name
                print(f"[ParallelPreprocess] 加载预处理结果: {original_name} -> {copy_obj.name}")
            else:
                print(f"[ParallelPreprocess] 警告: 副本 {copy_name} 未在预处理结果中找到")
        
        if not copy_mapping:
            print(f"[ParallelPreprocess] copy_mapping 为空，加载失败")
            manager.cleanup()
            return None
        
        manager.cleanup()
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
    

def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)
    bpy.utils.register_class(SSMTSelectGenerateModFolder)


def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)
    bpy.utils.unregister_class(SSMTSelectGenerateModFolder)

