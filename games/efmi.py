import bpy
import math

from ..config.main_config import GlobalConfig,LogicName
from ..common.draw_ib_model import DrawIBModel

from ..base.m_global_key_counter import M_GlobalKeyCounter
from ..blueprint.blueprint_model import BluePrintModel

from ..common.m_ini_builder import M_IniBuilder,M_IniSection,M_SectionType
from ..config.properties_generate_mod import Properties_GenerateMod
from ..common.m_ini_helper import M_IniHelper,M_IniHelper
from ..common.m_ini_helper_gui import M_IniHelperGUI

class ModModelEFMI:
    def __init__(self):
        # (1) 统计全局分支模型
        self.branch_model = BluePrintModel()

        # (2) 抽象每个DrawIB为DrawIBModel
        self.drawib_drawibmodel_dict:dict[str,DrawIBModel] = {}
        self.parse_draw_ib_draw_ib_model_dict()

        # (3) 这些属性用于ini生成
        self.vlr_filter_index_indent = ""
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

 

    def add_unity_vs_texture_override_ib_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        
        d3d11GameType = draw_ib_model.d3d11GameType

        for count_i,part_name in enumerate(draw_ib_model.import_config.part_name_list):
            match_first_index = draw_ib_model.import_config.match_first_index_list[count_i]
            # part_name = draw_ib_model.import_config.part_name_list[count_i]

            style_part_name = "Component" + part_name

            
            texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

            # 读取使用的IBResourceName，如果读取不到，就使用默认的
            ib_resource_name = ""
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name,None)
            

            texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
            texture_override_ib_section.append("hash = " + draw_ib)
            texture_override_ib_section.append("match_first_index = " + match_first_index)

            if self.vlr_filter_index_indent != "":
                texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

            texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")

            # If ib buf is emprt, continue to avoid add ib resource replace.
            ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
            if ib_buf is None or len(ib_buf) == 0:
                # 不导出对应部位时，要写ib = null，否则在部分场景会发生卡顿，原因未知但是这就是解决方案。
                texture_override_ib_section.append("ib = null")
                texture_override_ib_section.new_line()
                continue

            # Nico:
            # EFMI加载器中，提供了对贴图槽位的统一校验，以及提供了基于ShaderRegex的全局Check
            # 所以无需生成VSCheck.ini，也无需进行手动的贴图槽位Check了，节省了一些Mod制作步骤，在此进行同步
            texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\EFMIv1\\OverrideTextures")

            
            # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
            for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                texture_override_ib_section.append(category_original_slot + " = Resource" + draw_ib + original_category_name)

            if Properties_GenerateMod.add_rain_effect():
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vb3 = Resource" + draw_ib + "Position")

            texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)

            if not Properties_GenerateMod.forbid_auto_texture_ini():
                texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
                if texture_markup_info_list is not None:
                    if Properties_GenerateMod.use_rabbitfx_slot():
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_type == "Slot":
                                if texture_markup_info.mark_name == "DiffuseMap":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\Diffuse = ref " + texture_markup_info.get_resource_name())
                                elif texture_markup_info.mark_name == "LightMap":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\LightMap = ref " + texture_markup_info.get_resource_name())
                                elif texture_markup_info.mark_name == "NormalMap":
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\NormalMap = ref " + texture_markup_info.get_resource_name())
                        
                        texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\RabbitFx\\SetTextures")
                        
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_type == "Slot":
                                if texture_markup_info.mark_name in ["DiffuseMap", "LightMap", "NormalMap"]:
                                    pass
                                else:
                                    texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                    else:
                        for texture_markup_info in texture_markup_info_list:
                            if texture_markup_info.mark_type == "Slot":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

            # 如果不使用GPU-Skinning即为Object类型，此时需要在ib下面替换对应槽位
            if not d3d11GameType.GPU_PreSkinning:
                for category_name in d3d11GameType.OrderedCategoryNameList:
                    category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
                    category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]

                    for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                        if original_category_name == draw_category_name:
                            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                            texture_override_ib_section.append(self.vlr_filter_index_indent + category_original_slot + " = Resource" + draw_ib + original_category_name)


            component_name = "Component " + part_name 
            component_model = draw_ib_model.component_name_component_model_dict[component_name]

            # EFMI绘制调用改为drawindexedinstanced格式
            drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(component_model.final_ordered_draw_obj_model_list)
            for drawindexed_str in drawindexed_str_list:
                texture_override_ib_section.append(drawindexed_str)
            
            # 补全endif
            if self.vlr_filter_index_indent:
                texture_override_ib_section.append("endif")
                texture_override_ib_section.new_line()
            
            if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
                texture_override_ib_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")
                
                if Properties_GenerateMod.generate_branch_mod_gui():
                        texture_override_ib_section.append("$ActiveCharacter = 1")
            
        config_ini_builder.append_section(texture_override_ib_section)


    def add_unity_vs_resource_vb_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add Resource VB Section
        '''
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            resource_vb_section.append("[Resource" + draw_ib_model.draw_ib + category_name + "]")
            resource_vb_section.append("type = Buffer")

            resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            
            buffer_folder_name = GlobalConfig.get_buffer_folder_name()
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + draw_ib_model.draw_ib + "-" + category_name + ".buf")
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
            buffer_folder_name = GlobalConfig.get_buffer_folder_name()
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
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


    def add_unity_cs_texture_override_vb_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        if d3d11GameType.GPU_PreSkinning:
            texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
            texture_override_vb_section.append("; " + draw_ib)
            for category_name in d3d11GameType.OrderedCategoryNameList:
                category_hash = draw_ib_model.category_hash_dict[category_name]
                category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]
                texture_override_vb_namesuffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name

                if GlobalConfig.logic_name == LogicName.SRMI:
                    if category_name == "Position":
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "_VertexLimitRaise]")
                        texture_override_vb_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
                        texture_override_vb_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
                        texture_override_vb_section.append("uav_byte_stride = 4")
                    else:
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                else:
                    texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                texture_override_vb_section.append("hash = " + category_hash)
                


                # 如果出现了VertexLimitRaise，Texcoord槽位需要检测filter_index才能替换
                filterindex_indent_prefix = ""
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
                for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                    if category_name == draw_category_name:
                        if original_category_name == "Position":
                            texture_override_vb_section.append("cs-cb0 = Resource_" + draw_ib + "_VertexLimit")

                            position_category_slot = d3d11GameType.CategoryExtractSlotDict["Position"]
                            blend_category_slot = d3d11GameType.CategoryExtractSlotDict["Blend"]
                            # print(position_category_slot)

                            texture_override_vb_section.append(position_category_slot + " = Resource" + draw_ib + "Position")
                            texture_override_vb_section.append(blend_category_slot + " = Resource" + draw_ib + "Blend")

                            texture_override_vb_section.append("handling = skip")

                            dispatch_number = int(math.ceil(draw_ib_model.draw_number / 64)) + 1
                            texture_override_vb_section.append("dispatch = " + str(dispatch_number) + ",1,1")
                        elif original_category_name != "Blend":
                            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                            texture_override_vb_section.append(filterindex_indent_prefix  + category_original_slot + " = Resource" + draw_ib + original_category_name)

                # 对应if vb0 == 3000的结束
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("endif")
                
                # 分支架构，如果是Position则需提供激活变量
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Position"]:
                    if draw_ib_model.key_number != 0:
                        texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                texture_override_vb_section.new_line()
            config_ini_builder.append_section(texture_override_vb_section)
            


    def generate_unity_vs_config_ini(self):
        '''
        EFMI
        '''
        config_ini_builder = M_IniBuilder()

        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        print("Length: " + str(len(self.drawib_drawibmodel_dict.items())))

        for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():
            print("Generating Config INI for DrawIB: " + draw_ib)

            self.add_unity_vs_texture_override_ib_sections(config_ini_builder=config_ini_builder,commandlist_ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_unity_vs_resource_vb_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        
        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        M_IniHelper.add_shapekey_ini_sections(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")






