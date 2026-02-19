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
        
        # 创建三角化副本并更新节点引用
        # original_obj_name -> (copy_obj, node_or_item) 的映射
        copy_mapping = {}
        print(f"开始创建三角化副本...")
        for original_obj, node_or_item in obj_node_mapping:
            if original_obj and original_obj.type == 'MESH':
                # 创建副本
                copy_obj = original_obj.copy()
                copy_obj.data = original_obj.data.copy()
                
                # 命名规范：0b9bd38f-1-Original -> 0b9bd38f-1-copy_Original
                original_name = original_obj.name
                if original_name.endswith("-Original"):
                    copy_obj.name = original_name.replace("-Original", "-copy_Original")
                else:
                    copy_obj.name = f"{original_name}_copy"
                
                # 将副本链接到场景
                bpy.context.scene.collection.objects.link(copy_obj)
                
                # 对副本进行 BEAUTY 三角化
                from ..utils.obj_utils import mesh_triangulate_beauty
                mesh_triangulate_beauty(copy_obj)
                
                # 非镜像工作流：对副本应用镜像变换
                mirror_workflow_enabled = Properties_ImportModel.use_mirror_workflow()
                if mirror_workflow_enabled:
                    print(f"非镜像工作流：对副本 {copy_obj.name} 应用镜像变换")
                    ObjUtils.apply_mirror_workflow(copy_obj)
                
                # 保存原始名称到节点/项目（用于 INI 注释）
                node_or_item.original_object_name = original_name
                
                # 保存原始名称和映射关系
                copy_mapping[original_name] = (copy_obj, node_or_item)
                
                # 更新节点/项目引用到副本
                node_or_item.object_name = copy_obj.name
                print(f"创建副本: {original_name} -> {copy_obj.name}")
        
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
            
            self.report({'INFO'},TR.translate("Generate Mod Success!"))
            TimerUtils.End("GenerateMod Mod")
            
            mod_export_path = GlobalConfig.path_generate_mod_folder()
            print(f"Mod导出路径: {mod_export_path}")
            
            BlueprintExportHelper.execute_postprocess_nodes(mod_export_path)
            
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

