
import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils

from ..config.main_config import GlobalConfig, LogicName
from ..base.m_global_key_counter import M_GlobalKeyCounter

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

from .blueprint_model import BluePrintModel


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

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")

        M_GlobalKeyCounter.initialize()

        # 调用对应游戏的生成Mod逻辑
        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            migoto_mod_model = ModModelWWMI()
            migoto_mod_model.generate_unreal_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.YYSLS:
            migoto_mod_model = ModModelYYSLS()
            migoto_mod_model.generate_unity_vs_config_ini()

        elif GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.IdentityV2 or GlobalConfig.logic_name == LogicName.NierR:
            migoto_mod_model = ModModelIdentityV()

            migoto_mod_model.generate_unity_vs_config_ini()
        
        # 老米四件套
        elif GlobalConfig.logic_name == LogicName.HIMI:
            migoto_mod_model = ModModelHIMI()
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.GIMI:
            migoto_mod_model = ModModelGIMI()
            migoto_mod_model.generate_unity_vs_config_ini()
        elif GlobalConfig.logic_name == LogicName.SRMI:
            migoto_mod_model = ModModelSRMI()
            migoto_mod_model.generate_unity_cs_config_ini()
        elif GlobalConfig.logic_name == LogicName.ZZMI:
            migoto_mod_model = ModModelZZMI()
            migoto_mod_model.generate_unity_vs_config_ini()

        # UnityVS
        elif GlobalConfig.logic_name == LogicName.UnityVS:
            migoto_mod_model = ModModelUnity()
            migoto_mod_model.generate_unity_vs_config_ini()

        # AILIMIT
        elif GlobalConfig.logic_name == LogicName.AILIMIT or GlobalConfig.logic_name == LogicName.UnityCS:
            migoto_mod_model = ModModelUnity()
            migoto_mod_model.generate_unity_cs_config_ini()
        
        # UnityCPU 例如少女前线2、虚空之眼等等，绝大部分手游都是UnityCPU
        elif GlobalConfig.logic_name == LogicName.UnityCPU:
            migoto_mod_model = ModModelUnity()
            migoto_mod_model.generate_unity_vs_config_ini()
        
        # UnityCSM
        elif GlobalConfig.logic_name == LogicName.UnityCSM:
            migoto_mod_model = ModModelUnity()
            migoto_mod_model.generate_unity_cs_config_ini()

        # 尘白禁区、卡拉比丘
        elif GlobalConfig.logic_name == LogicName.SnowBreak:
            migoto_mod_model = ModModelSnowBreak()
            migoto_mod_model.generate_ini()
        else:
            self.report({'ERROR'},"当前逻辑暂不支持生成Mod")
            return {'FINISHED'}


        self.report({'INFO'},TR.translate("Generate Mod Success!"))
        TimerUtils.End("GenerateMod Mod")
        CommandUtils.OpenGeneratedModFolder()
        return {'FINISHED'}
    

def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)


def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)



