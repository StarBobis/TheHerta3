import bpy
from ..utils.translate_utils import TR
from ..config.main_config import GlobalConfig

class THEHERTA3_OT_OpenPersistentBlueprint(bpy.types.Operator):
    bl_idname = "theherta3.open_persistent_blueprint"
    bl_label = TR.translate("打开蓝图界面")
    bl_description = TR.translate("打开一个独立的蓝图窗口，用于配置Mod逻辑")
    
    def execute(self, context):
        # 1. 获取或创建蓝图树
        GlobalConfig.read_from_main_json()
        tree_name = f"Mod_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "SSMT_Mod_Logic"
        
        # 查找是否存在同名的 NodeGroup
        tree = bpy.data.node_groups.get(tree_name)
        if not tree:
            # 创建新的 NodeTree，类型必须是我们定义的 bl_idname
            tree = bpy.data.node_groups.new(name=tree_name, type='SSMTBlueprintTreeType')
            tree.use_fake_user = True
        
        # 2. 打开新窗口 (复制当前Context)
        old_windows = set(context.window_manager.windows)
        
        bpy.ops.wm.window_new()
        
        new_windows = set(context.window_manager.windows)
        created_window = (new_windows - old_windows).pop() if (new_windows - old_windows) else None
        
        if created_window:
            screen = created_window.screen
            
            target_area = max(screen.areas, key=lambda a: a.width * a.height)
            
            if target_area:
                target_area.ui_type = 'SSMTBlueprintTreeType' # 似乎不起作用，NodeEditor需要指定tree type
                target_area.type = 'NODE_EDITOR'
                
                # 设置空间属性
                for space in target_area.spaces:
                    if space.type == 'NODE_EDITOR':
                        space.tree_type = 'SSMTBlueprintTreeType' # 关键：切换到自定义树类型
                        space.node_tree = tree # 设置要编辑的数据块
                        space.pin = True # 锁定
                        
                        # 尝试调整视图 (可选)
                        
        return {'FINISHED'}


def register():
    bpy.utils.register_class(THEHERTA3_OT_OpenPersistentBlueprint)

def unregister():
    bpy.utils.unregister_class(THEHERTA3_OT_OpenPersistentBlueprint)
