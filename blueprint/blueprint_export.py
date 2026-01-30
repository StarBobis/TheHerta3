import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils

from ..config.main_config import GlobalConfig, LogicName
from ..base.m_global_key_counter import M_GlobalKeyCounter

from ..config.properties_generate_mod import Properties_GenerateMod

from .blueprint_model import BluePrintModel
from .blueprint_export_helper import BlueprintExportHelper


'''
TODO 

1.现在咱们不是有一个可以选择生成Mod的目标文件夹的按钮嘛
后续改成输出节点的一个属性，这样用户就可以在蓝图里动态控制Mod生成路径了
这样每个工作空间都可以指定独特的生成Mod位置

2.对于之前用户说的生成mod要有备份的问题，也可以在输出节点新增一个备份文件夹的属性
'''



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

        try:
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

            # 终末地测试AEMI，到时候老外的NDMI发布之后，再开一套新逻辑兼容他们的，咱们用这个先测试
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

            self.report({'INFO'},TR.translate("Generate Mod Success!"))
            TimerUtils.End("GenerateMod Mod")
            CommandUtils.OpenGeneratedModFolder()
        finally:
            # Clean up override
            BlueprintExportHelper.forced_target_tree_name = None
            
        return {'FINISHED'}
    

def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)


def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)

