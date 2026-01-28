import bpy


class Properties_GenerateMod(bpy.types.PropertyGroup):

    open_mod_folder_after_generate_mod: bpy.props.BoolProperty(
        name="生成后打开Mod文件夹",
        description="勾选后，在生成Mod完成后自动打开Mod文件夹",
        default=True
    ) # type: ignore
    
    @classmethod
    def open_mod_folder_after_generate_mod(cls):
        '''
        bpy.context.scene.properties_generate_mod.open_mod_folder_after_generate_mod
        '''
        return bpy.context.scene.properties_generate_mod.open_mod_folder_after_generate_mod

    zzz_use_slot_fix: bpy.props.BoolProperty(
        name="槽位风格贴图使用SlotFix技术",
        description="仅适用于槽位风格贴图，勾选后，特定名称标记的贴图将使用SlotFix风格，能一定程度上解决槽位风格贴图跨槽位的问题，跨Pixel槽位指的是在前一个DrawCall中是ps-t3但是下一个DrawCall变为ps-t5这种情况，但由于负责维护的人也在偷懒所以并不可靠",
        default=True
    ) # type: ignore


    @classmethod
    def zzz_use_slot_fix(cls):
        '''
        bpy.context.scene.properties_generate_mod.zzz_use_slot_fix
        '''
        return bpy.context.scene.properties_generate_mod.zzz_use_slot_fix
    
    gimi_use_orfix: bpy.props.BoolProperty(
        name="槽位风格贴图使用ORFix",
        description="勾选后，在使用槽位风格贴图标记时，如果偷懒不想手动维护由于贴图槽位变化导致的贴图损坏问题，可以勾选此选项将问题交给ORFix维护者来解决，仅GIMI可用\n注意，如果你不懂ORFix和NNFix的原理，请不要取消勾选，取消勾选会严格按照贴图标记来执行贴图部分ini生成，默认你会在ini中自行写判断语句修复来替代实现ORFix和NNFix的功能",
        default=True
    ) # type: ignore

    @classmethod
    def gimi_use_orfix(cls):
        '''
        bpy.context.scene.properties_generate_mod.gimi_use_orfix
        '''
        return bpy.context.scene.properties_generate_mod.gimi_use_orfix
    
    
    forbid_auto_texture_ini: bpy.props.BoolProperty(
        name="禁止自动贴图流程",
        description="生成Mod时禁止生成贴图相关ini部分",
        default=False
    ) # type: ignore


    @classmethod
    def forbid_auto_texture_ini(cls):
        '''
        bpy.context.scene.properties_generate_mod.forbid_auto_texture_ini
        '''
        return bpy.context.scene.properties_generate_mod.forbid_auto_texture_ini
    
    generate_branch_mod_gui: bpy.props.BoolProperty(
        name="生成分支切换Mod面板(测试版)",
        description="生成Mod时，生成一个基于当前集合架构的分支Mod面板，可在游戏中按住Ctrl + Alt呼出，仍在测试改进中",
        default=False
    ) # type: ignore


    @classmethod
    def generate_branch_mod_gui(cls):
        '''
        bpy.context.scene.properties_generate_mod.generate_branch_mod_gui
        '''
        return bpy.context.scene.properties_generate_mod.generate_branch_mod_gui
    

    recalculate_tangent: bpy.props.BoolProperty(
        name="向量归一化法线存入TANGENT(全局)",
        description="使用向量相加归一化重计算所有模型的TANGENT值，勾选此项后无法精细控制具体某个模型是否计算，是偷懒选项,在不勾选时默认使用右键菜单中标记的选项。\n" \
        "用途:\n" \
        "1.一般用于修复GI角色,HI3 1.0角色,HSR角色轮廓线。\n" \
        "2.用于修复模型由于TANGENT不正确导致的黑色色块儿问题，比如HSR的薄裙子可能会出现此问题。",
        default=False
    ) # type: ignore

    recalculate_color: bpy.props.BoolProperty(
        name="算术平均归一化法线存入COLOR(全局)",
        description="使用算术平均归一化重计算所有模型的COLOR值，勾选此项后无法精细控制具体某个模型是否计算，是偷懒选项,在不勾选时默认使用右键菜单中标记的选项，仅用于HI3 2.0角色修复轮廓线",
        default=False
    ) # type: ignore



    # use_specific_generate_mod_folder_path
    use_specific_generate_mod_folder_path:bpy.props.BoolProperty(
        name="生成Mod到指定的文件夹中",
        description="勾选后将生成Mod到你指定的文件夹中",
        default=False
    ) # type: ignore

    @classmethod
    def use_specific_generate_mod_folder_path(cls):
        '''
        bpy.context.scene.properties_generate_mod.use_specific_generate_mod_folder_path
        '''
        return bpy.context.scene.properties_generate_mod.use_specific_generate_mod_folder_path

    generate_mod_folder_path: bpy.props.StringProperty(
        name="生成Mod文件夹路径",
        description="选择的生成Mod的文件夹路径",
        default="",
        subtype='DIR_PATH'
    ) # type: ignore

    @classmethod
    def generate_mod_folder_path(cls):
        '''
        bpy.context.scene.properties_generate_mod.generate_mod_folder_path
        '''
        return bpy.context.scene.properties_generate_mod.generate_mod_folder_path
    


    



    
    @classmethod
    def author_name(cls):
        '''
        bpy.context.scene.properties_generate_mod.credit_info_author_name
        '''
        return bpy.context.scene.properties_generate_mod.credit_info_author_name
    
    @classmethod
    def author_link(cls):
        '''
        bpy.context.scene.properties_generate_mod.credit_info_author_social_link
        '''
        return bpy.context.scene.properties_generate_mod.credit_info_author_social_link
    
    @classmethod
    def recalculate_tangent(cls):
        '''
        bpy.context.scene.properties_generate_mod.recalculate_tangent
        '''
        return bpy.context.scene.properties_generate_mod.recalculate_tangent
    
    @classmethod
    def recalculate_color(cls):
        '''
        bpy.context.scene.properties_generate_mod.recalculate_color
        '''
        return bpy.context.scene.properties_generate_mod.recalculate_color
    
def register():
    bpy.utils.register_class(Properties_GenerateMod)
    bpy.types.Scene.properties_generate_mod = bpy.props.PointerProperty(type=Properties_GenerateMod)

def unregister():
    del bpy.types.Scene.properties_generate_mod
    bpy.utils.unregister_class(Properties_GenerateMod)

