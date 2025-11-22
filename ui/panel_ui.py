'''
基础信息面板
'''
import bpy

from ..config.main_config import GlobalConfig
from ..config.plugin_config import PluginConfig

from ..utils.translate_utils import TR


class PanelBasicInformation(bpy.types.Panel):
    '''
    基础信息面板
    此面板实时刷新并读取全局配置文件中的路径
    '''
    bl_label = TR.translate("基础信息面板")
    bl_idname = "VIEW3D_PT_CATTER_Buttons_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta'

    def draw(self, context):
        layout = self.layout

        GlobalConfig.read_from_main_json()

        self.bl_label =  "TheHerta3 v" +  PluginConfig.get_version_string()
        layout.label(text=TR.translate("SSMT缓存文件夹路径: ") + GlobalConfig.dbmtlocation)
        layout.label(text=TR.translate("当前游戏: ") + GlobalConfig.gamename)
        layout.label(text=TR.translate("当前逻辑: ") + GlobalConfig.logic_name)
        layout.label(text=TR.translate("当前工作空间: ") + GlobalConfig.workspacename)

        # layout.prop(context.scene.properties_import_model,"use_mirror_workflow",text="使用非镜像工作流")

        context = bpy.context  # 直接使用 bpy.context 获取完整上下文
        if len(context.selected_objects) != 0:
            obj = context.selected_objects[0]

            # 获取自定义属性
            gametypename = obj.get("3DMigoto:GameTypeName", None)
            recalculate_tangent = obj.get("3DMigoto:RecalculateTANGENT", None)
            recalculate_color = obj.get("3DMigoto:RecalculateCOLOR", None)

            layout.label(text="GameType: " + gametypename)
            layout.label(text="RecalculateTANGENT: " + str(recalculate_tangent))
            layout.label(text="RecalculateCOLOR: " + str(recalculate_color))
