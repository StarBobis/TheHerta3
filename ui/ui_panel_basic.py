'''
基础信息面板
'''
import bpy

from ..config.main_config import GlobalConfig, LogicName
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
    bl_category = 'TheHerta3'

    def draw(self, context):
        layout = self.layout

        GlobalConfig.read_from_main_json()

        self.bl_label =  "TheHerta3 V" +  PluginConfig.get_version_string() + "  SSMT V" + str(GlobalConfig.ssmt_version_number)
        layout.label(text=TR.translate("SSMT缓存文件夹路径: ") + GlobalConfig.dbmtlocation)
        layout.label(text=TR.translate("当前配置名称: ") + GlobalConfig.gamename)


        layout.label(text=TR.translate("当前执行逻辑: ") + GlobalConfig.logic_name)
        layout.label(text=TR.translate("当前工作空间: ") + GlobalConfig.workspacename)

        if PluginConfig.get_min_ssmt_version() > GlobalConfig.ssmt_version_number:
            layout.label(text=TR.translate("当前SSMT版本过低无法适配"),icon='ERROR')

        # layout.prop(context.scene.properties_import_model,"use_mirror_workflow",text="使用非镜像工作流")
        
        context = bpy.context  # 直接使用 bpy.context 获取完整上下文
        if len(context.selected_objects) != 0:
            obj = context.selected_objects[0]

            # 获取自定义属性
            gametypename = obj.get("3DMigoto:GameTypeName", "")
            recalculate_tangent = obj.get("3DMigoto:RecalculateTANGENT", False)
            recalculate_color = obj.get("3DMigoto:RecalculateCOLOR", False)

            layout.label(text="GameType: " + gametypename)
            layout.label(text="RecalculateTANGENT: " + str(recalculate_tangent))
            layout.label(text="RecalculateCOLOR: " + str(recalculate_color))

        # 导入 ib vb fmt格式文件
        layout.operator("import_mesh.migoto_raw_buffers_mmt",icon='IMPORT')

        # 一键导入当前工作空间为蓝图架构
        layout.operator("ssmt.import_all_from_workspace_blueprint",icon='IMPORT')

        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            layout.prop(context.scene.properties_wwmi,"import_merged_vgmap")
            layout.prop(context.scene.properties_wwmi,"import_skip_empty_vertex_groups")

        # 决定导入时是否调用法线贴图
        layout.prop(context.scene.properties_import_model, "use_normal_map")

def register():
    bpy.utils.register_class(PanelBasicInformation)

def unregister():
    bpy.utils.unregister_class(PanelBasicInformation)