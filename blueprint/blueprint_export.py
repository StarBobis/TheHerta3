
import bpy

from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR
from ..utils.command_utils import CommandUtils
from ..utils.collection_utils import CollectionUtils

from ..config.main_config import GlobalConfig, LogicName
from ..common.branch_model import M_GlobalKeyCounter

# from ..games.himi import ModModelHIMI
# from ..games.gimi import ModModelGIMI

# from ..games.zzmi import ModModelZZMI

# from ..games.unity import ModModelUnity
# from ..games.srmi import ModModelSRMI
# from ..games.identityv import ModModelIdentityV
# from ..games.yysls import ModModelYYSLS
# from ..games.wwmi import ModModelWWMI
# from ..games.snowbreak import ModModelSnowBreak

from ..games_new.zzmi_new import ModModelZZMI



from ..config.properties_generate_mod import Properties_GenerateMod

from .blueprint_model import BluePrintModel


'''
TODO 

1.现在咱们不是有一个可以选择生成Mod的目标文件夹的按钮嘛
后续改成输出节点的一个属性，这样用户就可以在蓝图里动态控制Mod生成路径了
这样每个工作空间都可以指定独特的生成Mod位置

2.对于之前用户说的生成mod要有备份的问题，也可以在输出节点新增一个备份文件夹的属性

3.生成Mod的逻辑需要全部改为基于解析蓝图节点的方式
因为蓝图里可以通过组来嵌套，也可以实现目前的无限嵌套递归解析的分支架构，且更加直观可控
摆脱了对于复杂的集合嵌套的依赖，也不需要改集合名称了，全部都在组节点的属性中指定
每个组就代表一个key或者单纯分组功能

4.后续生成Mod时，无需指定必须得是某个集合下面，因为蓝图里可以自由组合obj的原因
我们在生成时，只需要去解析蓝图输出节点所连接的组中的obj即可
所以目前的工作空间集合的颜色是红色的这一条可以去掉
也就是把导入和导出解耦合了，导入就只是导入，导出就只是导出，无需依赖于工作空间为名称的集合


5.之前老高加了一个导入和导出的快捷键，这个很少人用到，后续考虑删除掉
不过我在测试的时候既不会删除，也不会专门新增这个快捷键去测试

'''


class SSMTGenerateModBlueprint(bpy.types.Operator):
    bl_idname = "ssmt.generate_mod_blueprint"
    bl_label = TR.translate("生成Mod(蓝图架构)")
    bl_description = "根据当前工作空间对应的蓝图架构生成对应的Mod文件"
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        TimerUtils.Start("GenerateMod Mod")

        M_GlobalKeyCounter.initialize()

        # TODO
        # 当前的生成Mod逻辑是递归解析工作空间集合下的内容
        # 后面要改为解析蓝图中的内容
        # 然后我们需要先完成蓝图逻辑的构建
        # 然后目前的ModModel类，基本上全部都要重写为解析蓝图架构来得到导出所需数据
        # 有点复杂，不能着急，一步一步测试
        # 测试使用ZZMI，因为这个游戏测试起来比较方便
        # 使用ZZMI测试流程通过后，后面需要将其它游戏的逻辑同步为ZZMI的蓝图解析逻辑
        # 尤其要注意的是WWMI，在我们新的基于蓝图架构的解析中，WWMI的逻辑也可以很轻松的容纳进来了
        # 解决了之前生成WWMI Mod时，旧的集合架构需要频繁修改obj名称的问题
        # 也就是新的WWMI导入后可以直接是对应的DrawIB集合下面放对应的obj，便于区分
        # 也就顺利实现了WWMI的多IB支持
        # 并且也可以像WWMITools那样分开不同的文件夹，每个文件夹一个单独的DrawIB了，通过组节点来实现即可
        # 新的蓝图架构潜力非常大，能够任意扩展，基本上所有的目前现存的需求都能得到解决。


        # TODO 暂时现在这里测试流程，流程通过后迁移到zzmi_new.py里去
        if GlobalConfig.logic_name == LogicName.ZZMI:
            migoto_mod_model = ModModelZZMI()
            migoto_mod_model.generate_unity_vs_config_ini()



        self.report({'INFO'},TR.translate("Generate Mod Success!"))
        TimerUtils.End("GenerateMod Mod")
        CommandUtils.OpenGeneratedModFolder()
        return {'FINISHED'}
    

def register():
    bpy.utils.register_class(SSMTGenerateModBlueprint)

def unregister():
    bpy.utils.unregister_class(SSMTGenerateModBlueprint)




