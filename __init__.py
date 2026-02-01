import bpy

# UI界面
from .ui import ui_panel_basic
from .ui import ui_panel_model
from .ui import ui_panel_sword
from .ui import ui_panel_import
from .ui import ui_panel_fast_texture
from .blueprint import blueprint_node_obj
from .blueprint import blueprint_import
from .blueprint import blueprint_export
from .blueprint import blueprint_node_base
from .blueprint import blueprint_node_menu
from .blueprint import blueprint_node_shapekey
from .blueprint import blueprint_node_datatype
from .blueprint import blueprint_node_multifile_export
from .blueprint import blueprint_drag_drop
from .blueprint import blueprint_node_postprocess_vertex_attrs
from .blueprint import blueprint_node_postprocess_shapekey
from .blueprint import blueprint_node_postprocess_multifile
from .blueprint import blueprint_node_postprocess_buffer_cleanup
from .blueprint import blueprint_node_postprocess_resource_merge
from .blueprint import blueprint_node_postprocess_material
from .blueprint import blueprint_node_postprocess_health
from .blueprint import blueprint_node_postprocess_slider

# 自动更新功能
from . import addon_updater_ops

# 开发时确保同时自动更新 addon_updater_ops
import importlib
importlib.reload(addon_updater_ops)

from bpy.types import SpaceView3D

# 全局配置
from .config import properties_import_model
from .config import properties_generate_mod
from .config import properties_wwmi
from .config import properties_extract_model
from .config.plugin_config import PluginConfig

bl_info = {
    "name": "TheHerta3",
    "description": "SSMT3.0 Series's Blender Plugin.",
    "blender": (4, 5, 0),
    "version": (3, 5, 3),
    "location": "View3D",
    "min_ssmt_version": 353, # 确保TheHerta3正确工作的SSMT最低版本号
    "category": "Generic"
}


PluginConfig.set_bl_info(bl_info)


class UpdaterPanel(bpy.types.Panel):
    """Update Panel"""
    bl_label = "检查版本更新"
    bl_idname = "HERTA_PT_UpdaterPanel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_context = "objectmode"
    bl_category = "TheHerta3"
    bl_order = 99
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        # Call to check for update in background.
        # Note: built-in checks ensure it runs at most once, and will run in
        # the background thread, not blocking or hanging blender.
        # Internally also checks to see if auto-check enabled and if the time
        # interval has passed.
        # addon_updater_ops.check_for_update_background()
        col = layout.column()
        col.scale_y = 0.7
        # Could also use your own custom drawing based on shared variables.
        if addon_updater_ops.updater.update_ready:
            layout.label(text="存在可用更新！", icon="INFO")

        # Call built-in function with draw code/checks.
        # addon_updater_ops.update_notice_box_ui(self, context)
        addon_updater_ops.update_settings_ui(self, context)


class HertaUpdatePreference(bpy.types.AddonPreferences):
    # Addon updater preferences.
    bl_label = "TheHerta 更新器"
    bl_idname = __package__


    auto_check_update: bpy.props.BoolProperty(
        name="自动检查更新",
        description="如启用，按设定的时间间隔自动检查更新",
        default=True) # type: ignore

    updater_interval_months: bpy.props.IntProperty(
        name='月',
        description="自动检查更新间隔月数",
        default=0,
        min=0) # type: ignore

    updater_interval_days: bpy.props.IntProperty(
        name='天',
        description="自动检查更新间隔天数",
        default=1,
        min=0,
        max=31) # type: ignore

    updater_interval_hours: bpy.props.IntProperty(
        name='小时',
        description="自动检查更新间隔小时数",
        default=0,
        min=0,
        max=23) # type: ignore

    updater_interval_minutes: bpy.props.IntProperty(
        name='分钟',
        description="自动检查更新间隔分钟数",
        default=0,
        min=0,
        max=59) # type: ignore
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "自动检查更新")
        addon_updater_ops.update_settings_ui(self, context)

def register():
    # 1. Configs
    properties_import_model.register()
    properties_wwmi.register()
    properties_generate_mod.register()
    properties_extract_model.register()
    
    # 2. Addon Updater (local classes)
    addon_updater_ops.register(bl_info)
    bpy.utils.register_class(UpdaterPanel)
    bpy.utils.register_class(HertaUpdatePreference)

    # 3. UI Panels & Logic
    blueprint_node_base.register()
    ui_panel_basic.register()
    ui_panel_model.register()
    ui_panel_sword.register()
    ui_panel_import.register()
    ui_panel_fast_texture.register()

    # 蓝图系统
    blueprint_node_obj.register()
    blueprint_import.register()
    blueprint_export.register()
    blueprint_node_menu.register()
    blueprint_node_shapekey.register()
    blueprint_node_datatype.register()
    blueprint_node_multifile_export.register()
    blueprint_drag_drop.register()
    blueprint_node_postprocess_vertex_attrs.register()
    blueprint_node_postprocess_shapekey.register()
    blueprint_node_postprocess_multifile.register()
    blueprint_node_postprocess_buffer_cleanup.register()
    blueprint_node_postprocess_resource_merge.register()
    blueprint_node_postprocess_material.register()
    blueprint_node_postprocess_health.register()
    blueprint_node_postprocess_slider.register()



def unregister():
    # 蓝图系统
    blueprint_node_postprocess_slider.unregister()
    blueprint_node_postprocess_health.unregister()
    blueprint_node_postprocess_material.unregister()
    blueprint_node_postprocess_resource_merge.unregister()
    blueprint_node_postprocess_buffer_cleanup.unregister()
    blueprint_node_postprocess_multifile.unregister()
    blueprint_node_postprocess_shapekey.unregister()
    blueprint_node_postprocess_vertex_attrs.unregister()
    blueprint_node_obj.unregister()
    blueprint_import.unregister()
    blueprint_export.unregister()
    blueprint_node_menu.unregister()
    blueprint_node_shapekey.unregister()
    blueprint_node_datatype.unregister()
    blueprint_node_multifile_export.unregister()
    blueprint_drag_drop.unregister()
    blueprint_node_base.unregister()

    ui_panel_fast_texture.unregister()
    ui_panel_import.unregister()
    ui_panel_sword.unregister()
    ui_panel_model.unregister()
    ui_panel_basic.unregister()

    # 2. Addon Updater (local classes)
    bpy.utils.unregister_class(HertaUpdatePreference)
    bpy.utils.unregister_class(UpdaterPanel)
    addon_updater_ops.unregister()

    # 1. Configs
    properties_extract_model.unregister()
    properties_generate_mod.unregister()
    properties_wwmi.unregister()
    properties_import_model.unregister()




