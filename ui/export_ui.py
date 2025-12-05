'''
生成Mod配置面板
'''
import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils

from ..config.main_config import GlobalConfig, LogicName
from ..common.branch_model import M_GlobalKeyCounter

from ..games.himi import ModModelHIMI
from ..games.gimi import ModModelGIMI

from ..games.zzmi import ModModelZZMI

from ..games.unity import ModModelUnity
from ..games.srmi import ModModelSRMI
from ..games.identityv import ModModelIdentityV
from ..games.yysls import ModModelYYSLS
from ..games.wwmi import ModModelWWMI
from ..games.snowbreak import ModModelSnowBreak
from ..config.properties_generate_mod import Properties_GenerateMod


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


class PanelGenerateModConfig(bpy.types.Panel):
    '''
    生成Mod面板
    '''
    bl_label = "生成二创模型"
    bl_idname = "VIEW3D_PT_CATTER_GenerateMod_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'
    # bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        # 生成Mod按钮
        if GlobalConfig.logic_name == LogicName.WWMI:
            layout.label(text="鸣潮请优先考虑使用WWMI-Tools,SSMT仅提供概念与流程验证支持",icon='INFO')

        layout.operator("ssmt.generate_mod",icon='EXPORT')

        # 根据当前游戏类型判断哪些应该显示哪些不显示。
        # 因为UnrealVS显然无法支持这里所有的特性，每个游戏只能支持一部分特性。

        # 任何游戏都能贴图标记
        if GlobalConfig.logic_name == LogicName.WWMI:
            layout.prop(context.scene.properties_wwmi, "ignore_muted_shape_keys")
            layout.prop(context.scene.properties_wwmi, "apply_all_modifiers")

        layout.prop(context.scene.properties_generate_mod, 
                    "forbid_auto_texture_ini",text="禁止自动贴图流程")

        if GlobalConfig.logic_name != LogicName.UnityCPU:
            layout.prop(context.scene.properties_generate_mod,
                        "recalculate_tangent",text="向量归一化法线存入TANGENT(全局)")

        if GlobalConfig.logic_name == LogicName.HIMI:
            layout.prop(context.scene.properties_generate_mod,
                        "recalculate_color",text="算术平均归一化法线存入COLOR(全局)")

        # 绝区零特有的SlotFix技术
        if GlobalConfig.logic_name == LogicName.ZZMI:
            layout.prop(context.scene.properties_generate_mod, "zzz_use_slot_fix")

        # 原神特有的ORFix与NNFix技术
        if GlobalConfig.logic_name == LogicName.GIMI:
            layout.prop(context.scene.properties_generate_mod, "gimi_use_orfix")

        # 所有的游戏都要能支持生成分支架构面板Mod
        layout.prop(context.scene.properties_generate_mod, "generate_branch_mod_gui",text="生成分支架构Mod面板(测试中)")

        # 默认习惯肯定是要显示这个的，但是由于不经常点击关闭，所以放在最后面
        layout.prop(context.scene.properties_generate_mod, "open_mod_folder_after_generate_mod",text="生成Mod后打开Mod所在文件夹")

        # 生成Mod到指定的文件夹中吗？什么时候才会有这种需求呢？
        # 一般生成到当前的3Dmigoto下面的Mods下面不就行了嘛
        # emmmmm，不管怎么说，还是加上，万一有用呢。
        layout.prop(context.scene.properties_generate_mod, "use_specific_generate_mod_folder_path")

        if Properties_GenerateMod.use_specific_generate_mod_folder_path():
            # 显示当前选择的文件夹或提示信息
            box = layout.box()
            box.label(text="当前生成Mod位置文件夹:")
            box.label(text=context.scene.properties_generate_mod.generate_mod_folder_path)

            # 选择文件夹按钮
            layout.operator("ssmt.select_generate_mod_folder", icon='FILE_FOLDER')
        

class SSMTGenerateMod(bpy.types.Operator):
    bl_idname = "ssmt.generate_mod"
    bl_label = TR.translate("生成Mod")
    bl_description = "一键导出当前工作空间集合中的Mod，隐藏显示的模型不会被导出，隐藏的DrawIB为名称的集合不会被导出。使用前确保取消隐藏所有要导出的模型以及集合"
    bl_options = {'REGISTER'}

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")

        M_GlobalKeyCounter.initialize()

        # 先校验当前选中的工作空间是不是一个有效的工作空间集合
        workspace_collection = bpy.context.collection
        result = CollectionUtils.is_valid_ssmt_workspace_collection_v2(workspace_collection)
        if result != "":
            self.report({'ERROR'},result)
            return {'FINISHED'}
    
        # 调用对应游戏的生成Mod逻辑
        if GlobalConfig.logic_name == LogicName.WWMI:
            migoto_mod_model = ModModelWWMI(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unreal_vs_config_ini()

        elif GlobalConfig.logic_name == LogicName.YYSLS:
            migoto_mod_model = ModModelYYSLS(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()

        elif GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.IdentityV2 or GlobalConfig.logic_name == LogicName.NierR:
            migoto_mod_model = ModModelIdentityV(workspace_collection=workspace_collection)

            migoto_mod_model.generate_unity_vs_config_ini()
        
        # 老米四件套
        elif GlobalConfig.logic_name == LogicName.HIMI:
            migoto_mod_model = ModModelHIMI(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.GIMI:
            migoto_mod_model = ModModelGIMI(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.SRMI:
            migoto_mod_model = ModModelSRMI(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_cs_config_ini()
        elif GlobalConfig.logic_name == LogicName.ZZMI:
            migoto_mod_model = ModModelZZMI(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()

        # UnityVS
        elif GlobalConfig.logic_name == LogicName.UnityVS:
            migoto_mod_model = ModModelUnity(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()

        # AILIMIT
        elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
            migoto_mod_model = ModModelUnity(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_cs_config_ini()
        
        # UnityCPU 例如少女前线2、虚空之眼等等，绝大部分手游都是UnityCPU
        elif GlobalConfig.logic_name == LogicName.UnityCPU:
            migoto_mod_model = ModModelUnity(workspace_collection=workspace_collection)
            migoto_mod_model.generate_unity_vs_config_ini()

        # 尘白禁区、卡拉比丘
        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            migoto_mod_model = ModModelSnowBreak(workspace_collection=workspace_collection)
            migoto_mod_model.generate_ini()
        else:
            self.report({'ERROR'},"当前逻辑暂不支持生成Mod")
            return {'FINISHED'}
        

        self.report({'INFO'},TR.translate("Generate Mod Success!"))
        TimerUtils.End("GenerateMod Mod")

        CommandUtils.OpenGeneratedModFolder()
        return {'FINISHED'}