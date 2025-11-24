"""
GIMI
"""
import bpy

from ..config.main_config import GlobalConfig
from ..config.properties_generate_mod import Properties_GenerateMod

from ..common.draw_ib_model import DrawIBModel
from ..common.branch_model import BranchModel,M_GlobalKeyCounter
from ..common.m_ini_builder import M_IniBuilder,M_IniSection,M_SectionType
from ..common.m_ini_helper import M_IniHelper,M_IniHelper
from ..common.m_ini_helper_gui import M_IniHelperGUI

class GIMITextureMarkName:
    '''
    GIMI的几个常用固定标记名称
    '''
    DiffuseMap = "DiffuseMap"
    NormalMap = "NormalMap"
    LightMap = "LightMap"


class ModModelGIMI:
    '''
    GIMI生成类
    '''
    def __init__(self,workspace_collection:bpy.types.Collection):
        # (1) 统计全局分支模型
        self.branch_model = BranchModel(workspace_collection=workspace_collection)

        # (2) 抽象每个DrawIB为DrawIBModel
        self.drawib_drawibmodel_dict:dict[str,DrawIBModel] = {}
        self.parse_draw_ib_draw_ib_model_dict()

        # (3) 这些属性用于ini生成
        self.texture_hash_filter_index_dict = {}

    def parse_draw_ib_draw_ib_model_dict(self):
        '''
        根据obj的命名规则，推导出DrawIB并抽象为DrawIBModel
        如果用户用不到某个DrawIB的话，就可以隐藏掉对应的obj
        隐藏掉的obj就不会被统计生成DrawIBModel，做到只导入模型，不生成Mod的效果。
        '''
        for draw_ib in self.branch_model.draw_ib__component_count_list__dict.keys():
            draw_ib_model = DrawIBModel(draw_ib=draw_ib,branch_model=self.branch_model)
            self.drawib_drawibmodel_dict[draw_ib] = draw_ib_model

    def add_unity_vs_texture_override_vb_sections(
            self,
            config_ini_builder:M_IniBuilder,
            draw_ib_model:DrawIBModel):
        '''
        添加
        '''

        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11_game_type = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        # 只有GPU-PreSkinning需要生成TextureOverrideVB部分，CPU类型不需要

        texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
        texture_override_vb_section.append("; " + draw_ib + " ")
        for category_name in d3d11_game_type.OrderedCategoryNameList:
            category_hash = draw_ib_model.import_config.category_hash_dict[category_name]

            texture_override_vb_name_suffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name
            texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_name_suffix + "]")
            texture_override_vb_section.append("hash = " + category_hash)

            
            # (1) 先初始化CommandList
            drawtype_indent_prefix = ""
   
            
            # 如果出现了VertexLimitRaise，Texcoord槽位需要检测filter_index才能替换
            filterindex_indent_prefix = ""


            # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
            for original_category_name, draw_category_name in d3d11_game_type.CategoryDrawCategoryDict.items():
                if category_name == draw_category_name:
                    category_original_slot = d3d11_game_type.CategoryExtractSlotDict[original_category_name]
                    texture_override_vb_section.append(filterindex_indent_prefix + drawtype_indent_prefix + category_original_slot + " = Resource" + draw_ib + original_category_name)

            # draw一般都是在Blend槽位上进行的，所以我们这里要判断确定是Blend要替换的hash才能进行draw。
            draw_category_name = d3d11_game_type.CategoryDrawCategoryDict.get("Blend",None)
            if draw_category_name is not None and category_name == d3d11_game_type.CategoryDrawCategoryDict["Blend"]:
                texture_override_vb_section.append(drawtype_indent_prefix + "handling = skip")
                texture_override_vb_section.append(drawtype_indent_prefix + "draw = " + str(draw_ib_model.draw_number) + ", 0")


            
            # 分支架构，如果是Position则需提供激活变量
            if category_name == d3d11_game_type.CategoryDrawCategoryDict["Position"]:
                if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
                    texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                    if Properties_GenerateMod.generate_branch_mod_gui():
                        texture_override_vb_section.append("$ActiveCharacter = 1")

            texture_override_vb_section.new_line()


        config_ini_builder.append_section(texture_override_vb_section)

    def add_unity_vs_texture_override_ib_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib

        texture_override_ib_section.append("[TextureOverride_IB_" + draw_ib + "]")
        texture_override_ib_section.append("hash = " + draw_ib)
        texture_override_ib_section.append("handling = skip")
        texture_override_ib_section.new_line()

        for count_i,part_name in enumerate(draw_ib_model.import_config.part_name_list):
            match_first_index = draw_ib_model.import_config.match_first_index_list[count_i]
            
            style_part_name = "Component" + part_name
            texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

            # 读取使用的IBResourceName，如果读取不到，就使用默认的
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name,"")
            

            texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
            texture_override_ib_section.append("hash = " + draw_ib)
            texture_override_ib_section.append("match_first_index = " + match_first_index)


            # If ib buf is emprt, continue to avoid add ib resource replace.
            ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
            if ib_buf is None or len(ib_buf) == 0:
                # 不导出对应部位时，要写ib = null，否则在部分场景会发生卡顿，原因未知但是这就是解决方案。
                texture_override_ib_section.append("ib = null")
                texture_override_ib_section.new_line()
                continue


            # Add ib replace
            texture_override_ib_section.append("ib = " + ib_resource_name)


            print("Test: ZZZ")
            # Add slot style texture slot replace.
            if not Properties_GenerateMod.forbid_auto_texture_ini():
                texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                
                # 先判断是否具有NormalMap
                normal_exists = False
                
                # 如果使用ORFix技术，则所有的槽位都要强制使用固定的槽位
                if Properties_GenerateMod.gimi_use_orfix():
                    if texture_markup_info_list is not None:
                        
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_name == GIMITextureMarkName.NormalMap:
                                normal_exists = True
                        
                        altered_texture_markup_info_list = []
                        if normal_exists:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_name == GIMITextureMarkName.NormalMap:
                                    texture_markup_info.mark_slot = "ps-t0"
                                elif texture_markup_info.mark_name == GIMITextureMarkName.DiffuseMap:
                                    texture_markup_info.mark_slot = "ps-t1"
                                elif texture_markup_info.mark_name == GIMITextureMarkName.LightMap:
                                    texture_markup_info.mark_slot = "ps-t2"
                                altered_texture_markup_info_list.append(texture_markup_info)
                        else:
                            for texture_markup_info in texture_markup_info_list:
                                if texture_markup_info.mark_name == GIMITextureMarkName.DiffuseMap:
                                    texture_markup_info.mark_slot = "ps-t0"
                                elif texture_markup_info.mark_name == GIMITextureMarkName.LightMap:
                                    texture_markup_info.mark_slot = "ps-t1"
                                altered_texture_markup_info_list.append(texture_markup_info)
                        
                        texture_markup_info_list = altered_texture_markup_info_list
                
                # print(texture_markup_info_list)
                # It may not have auto texture
                if texture_markup_info_list is not None:
                    slot_replace_exists = False
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            slot_replace_exists = True
                            texture_override_ib_section.append(texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

                    if Properties_GenerateMod.gimi_use_orfix() and slot_replace_exists:
                        if normal_exists:
                            texture_override_ib_section.append("run = CommandList\\global\\ORFix\\ORFix")
                        else:
                            texture_override_ib_section.append("run = CommandList\\global\\ORFix\\NNFix")

            # DrawIndexed部分
            component_name = "Component " + part_name
            component_model = draw_ib_model.component_name_component_model_dict[component_name]

            drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
            for drawindexed_str in drawindexed_str_list:
                texture_override_ib_section.append(drawindexed_str)

            
        config_ini_builder.append_section(texture_override_ib_section)

    def add_unity_vs_texture_override_vlr_section(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        '''
        Add VertexLimitRaise section, UnityVS style.
        Only Unity VertexShader GPU-PreSkinning use this.

        格式问题：
        override_byte_stride = 40
        override_vertex_count = 14325
        uav_byte_stride = 4
        由于这个格式并未添加到CommandList的解析中，所以没法单独写在CommandList里，只能写在TextureOverride下面
        所以我们这个VertexLimitRaise部分直接整体写入CommandList.ini中

        这个部分由于有一个Hash值，所以如果需要加密Mod并且让Hash值修复脚本能够运作的话，
        可以在最终制作完成Mod后，手动把这个VertexLimitRaise部分放到Config.ini中
        '''
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib
        if d3d11GameType.GPU_PreSkinning:
            vertexlimit_section = M_IniSection(M_SectionType.TextureOverrideVertexLimitRaise)

            vertexlimit_section_name_suffix =  draw_ib + "_" + draw_ib_model.draw_ib_alias + "_VertexLimitRaise"
            vertexlimit_section.append("[TextureOverride_" + vertexlimit_section_name_suffix + "]")
            vertexlimit_section.append("hash = " + draw_ib_model.import_config.vertex_limit_hash)
            vertexlimit_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
            vertexlimit_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))

            # GIMI应该暂时不需要显式指定uav_byte_stride = 4
            # vertexlimit_section.append("uav_byte_stride = 4")
            vertexlimit_section.new_line()

            commandlist_ini_builder.append_section(vertexlimit_section)

    def add_unity_vs_resource_vb_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add Resource VB Section
        '''
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            resource_vb_section.append("[Resource" + draw_ib_model.draw_ib + category_name + "]")
            resource_vb_section.append("type = Buffer")

            resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            
            resource_vb_section.append("filename = Buffer/" + draw_ib_model.draw_ib + "-" + category_name + ".buf")
            # resource_vb_section.append(";VertexCount: " + str(draw_ib_model.draw_number))
            resource_vb_section.new_line()
        
        '''
        Add Resource IB Section

        We default use R32_UINT because R16_UINT have a very small number limit.
        '''

        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname,None)
            resource_vb_section.append("[" + ib_resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("format = DXGI_FORMAT_R32_UINT")
            resource_vb_section.append("filename = Buffer/" + ib_filename)
            resource_vb_section.new_line()

        ini_builder.append_section(resource_vb_section)


    def add_resource_texture_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add texture resource.
        只有槽位风格贴图会用到，因为Hash风格贴图有专门的方法去声明这个。
        '''
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return 
        
        resource_texture_section = M_IniSection(M_SectionType.ResourceTexture)
        for partname, texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.items():
            for texture_markup_info in texture_markup_info_list:
                if texture_markup_info.mark_type == "Slot":
                    resource_texture_section.append("[" + texture_markup_info.get_resource_name() + "]")
                    resource_texture_section.append("filename = Texture/" + texture_markup_info.mark_filename)
                    resource_texture_section.new_line()

        ini_builder.append_section(resource_texture_section)


    def generate_unity_vs_config_ini(self):
        config_ini_builder = M_IniBuilder()

        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)

        
        for draw_ib_model in self.drawib_drawibmodel_dict.values():
            # 按键开关与按键切换声明部分

        
            self.add_unity_vs_texture_override_vlr_section(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_unity_vs_texture_override_vb_sections(config_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            self.add_unity_vs_texture_override_ib_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            self.add_unity_vs_resource_vb_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")
