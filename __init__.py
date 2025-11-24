

# UI界面
from .ui.panel_ui import * 
from .ui.panel_model_ui import *
from .ui.collection_rightclick_ui import *
from .ui.migoto_sword_ui import *
from .ui.export_ui import SSMTGenerateMod, PanelGenerateModConfig, SSMTSelectGenerateModFolder
from .ui.import_ui import Import3DMigotoRaw, SSMTImportAllFromCurrentWorkSpaceV3, PanelModelImportConfig
from .ui.fast_texture_ui import *

# 自动更新功能
from . import addon_updater_ops

# 开发时确保同时自动更新 addon_updater_ops
import importlib
importlib.reload(addon_updater_ops)

from bpy.types import SpaceView3D

# 全局配置
from .config.properties_import_model import Properties_ImportModel
from .config.properties_generate_mod import Properties_GenerateMod
from .config.properties_wwmi import Properties_WWMI
from .config.properties_extract_model import Properties_ExtractModel
from .config.plugin_config import PluginConfig

bl_info = {
    "name": "TheHerta3",
    "description": "SSMT3.0 Series's Blender Plugin.",
    "blender": (5, 1, 0),
    "version": (3, 1, 0),
    "location": "View3D",
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

register_classes = (
    # 全局配置
    Properties_ImportModel,
    Properties_WWMI,
    Properties_GenerateMod,
    Properties_ExtractModel,


    # 导入3Dmigoto模型功能
    Import3DMigotoRaw,
    SSMTImportAllFromCurrentWorkSpaceV3,
    # 生成Mod功能
    SSMTGenerateMod,

    # 模型处理面板
    RemoveAllVertexGroupOperator,
    RemoveUnusedVertexGroupOperator,
    MergeVertexGroupsWithSameNumber,
    FillVertexGroupGaps,
    AddBoneFromVertexGroupV2,
    RemoveNotNumberVertexGroup,
    MMTResetRotation,
    CatterRightClickMenu,
    SplitMeshByCommonVertexGroup,
    RecalculateTANGENTWithVectorNormalizedNormal,
    RecalculateCOLORWithVectorNormalizedNormal,
    WWMI_ApplyModifierForObjectWithShapeKeysOperator,
    SmoothNormalSaveToUV,
    RenameAmatureFromGame,
    ModelSplitByLoosePart,
    ModelSplitByVertexGroup,
    ModelDeleteLoosePoint,
    ModelRenameVertexGroupNameWithTheirSuffix,
    ModelResetLocation,
    ModelSortVertexGroupByName,
    ModelVertexGroupRenameByLocation,

    # 集合的右键菜单栏
    Catter_MarkCollection_Switch,
    Catter_MarkCollection_Toggle,
    SSMT_LinkObjectsToCollection,
    SSMT_UnlinkObjectsFromCollection,
    # UI
    PanelBasicInformation,

    PanelModelImportConfig,
    PanelGenerateModConfig,
    PanelModelProcess,

    ExtractSubmeshOperator,
    PanelModelSplit,

    HertaUpdatePreference,
    UpdaterPanel,

    SSMTSelectGenerateModFolder,

    Sword_UL_FastImportTextureList,
    Sword_ImportTexture_ImageListItem,
    Sword_ImportTexture_VIEW3D_PT_ImageMaterialPanel,
    Sword_ImportTexture_WM_OT_ApplyImageToMaterial,
    Sword_ImportTexture_WM_OT_SelectImageFolder,
    SwordImportAllReversed,

    SSMT_UL_FastImportTextureList,
    SSMT_ImportTexture_WM_OT_ApplyImageToMaterial,
    SSMT_ImportTexture_VIEW3D_PT_ImageMaterialPanel,
    SSMT_ImportTexture_WM_OT_AutoDetectTextureFolder,
    SSMT_FastTexture_ComponentOnly,
)


def register():
    # 创建预览集合
    pcoll = bpy.utils.previews.new()
    preview_collections["main"] = pcoll

    fast_pcoll = bpy.utils.previews.new()
    fast_preview_collections["main"] = fast_pcoll

    for cls in register_classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.properties_wwmi = bpy.props.PointerProperty(type=Properties_WWMI)
    bpy.types.Scene.properties_import_model = bpy.props.PointerProperty(type=Properties_ImportModel)
    bpy.types.Scene.properties_generate_mod = bpy.props.PointerProperty(type=Properties_GenerateMod)
    bpy.types.Scene.properties_extract_model = bpy.props.PointerProperty(type=Properties_ExtractModel)

    bpy.types.VIEW3D_MT_object_context_menu.append(menu_func_migoto_right_click)
    bpy.types.OUTLINER_MT_collection.append(menu_dbmt_mark_collection_switch)


    bpy.types.Scene.submesh_start = bpy.props.IntProperty(
        name="Start Index",
        default=0,
        min=0
    )
    bpy.types.Scene.submesh_count = bpy.props.IntProperty(
        name="Index Count",
        default=3,
        min=3
    )

    # 添加快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(SSMTImportAllFromCurrentWorkSpaceV3.bl_idname, 
                                    type='I', value='PRESS', 
                                    ctrl=True, alt=True, shift=False)
        kmi = km.keymap_items.new(SSMTGenerateMod.bl_idname, 
                                    type='O', value='PRESS',
                                    ctrl=True, alt=True, shift=False)


    addon_updater_ops.register(bl_info)
    

    # 在场景属性中存储图片列表和索引
    bpy.types.Scene.sword_image_list = CollectionProperty(type=Sword_ImportTexture_ImageListItem)
    bpy.types.Scene.sword_image_list_index = IntProperty(default=0)

    # 在场景属性中存储图片列表和索引
    bpy.types.Scene.image_list = CollectionProperty(type=Sword_ImportTexture_ImageListItem)
    bpy.types.Scene.image_list_index = IntProperty(default=0)




def unregister():

    # 清除预览集合
    for pcoll in preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    preview_collections.clear()

    for pcoll in fast_preview_collections.values():
        bpy.utils.previews.remove(pcoll)
    fast_preview_collections.clear()

    for cls in reversed(register_classes):
        bpy.utils.unregister_class(cls)
    
    # 删除场景属性
    del bpy.types.Scene.sword_image_list
    del bpy.types.Scene.sword_image_list_index

    del bpy.types.Scene.image_list
    del bpy.types.Scene.image_list_index


    addon_updater_ops.unregister()

    # 卸载右键菜单
    bpy.types.VIEW3D_MT_object_context_menu.remove(menu_func_migoto_right_click)
    bpy.types.OUTLINER_MT_collection.remove(menu_dbmt_mark_collection_switch)

    del bpy.types.Scene.submesh_start
    del bpy.types.Scene.submesh_count

    # 移除快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.get('3D View')
        if km:
            for kmi in km.keymap_items:
                if kmi.idname in [SSMTImportAllFromCurrentWorkSpaceV3.bl_idname, SSMTGenerateMod.bl_idname]:
                    km.keymap_items.remove(kmi)
    

    

if __name__ == "__main__":
    register()




