import os
import shutil

from .m_ini_builder import *
from ..utils.json_utils import JsonUtils
from ..config.main_config import GlobalConfig,LogicName
from ..config.properties_generate_mod import Properties_GenerateMod
from ..base.m_global_key_counter import M_GlobalKeyCounter

from .draw_ib_model import DrawIBModel
from ..base.m_key import M_Key
from ..base.obj_data_model import ObjDataModel
from .workspace_helper import WorkSpaceHelper
from ..utils.format_utils import Fatal

class M_IniHelper:
    @classmethod
    def get_drawindexed_str_list(cls,ordered_draw_obj_model_list) -> list[str]:
        # 在输出之前，我们需要根据condition对obj_model进行分组
        condition_str_obj_model_list_dict:dict[str,list[ObjDataModel]] = {}
        for obj_model in ordered_draw_obj_model_list:

            obj_model_list = condition_str_obj_model_list_dict.get(obj_model.condition.condition_str,[])
            
            obj_model_list.append(obj_model)
            condition_str_obj_model_list_dict[obj_model.condition.condition_str] = obj_model_list
        
        drawindexed_str_list:list[str] = []
        for condition_str, obj_model_list in condition_str_obj_model_list_dict.items():
            if condition_str != "":
                drawindexed_str_list.append("if " + condition_str)
                for obj_model in obj_model_list:
                    drawindexed_str_list.append("  ; [mesh:" + obj_model.obj_name + "] [vertex_count:" + str(obj_model.drawindexed_obj.UniqueVertexCount) + "]" )
                    drawindexed_str_list.append("  " + obj_model.drawindexed_obj.get_draw_str())
                drawindexed_str_list.append("endif")
            else:
                for obj_model in obj_model_list:
                    drawindexed_str_list.append("; [mesh:" + obj_model.obj_name + "] [vertex_count:" + str(obj_model.drawindexed_obj.UniqueVertexCount) + "]" )
                    drawindexed_str_list.append(obj_model.drawindexed_obj.get_draw_str())
            drawindexed_str_list.append("")

        return drawindexed_str_list
    


    @classmethod
    def generate_hash_style_texture_ini(cls,ini_builder:M_IniBuilder,drawib_drawibmodel_dict:dict[str,DrawIBModel]):
        '''
        Hash风格贴图
        '''
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return
        

        # 先统计当前标记的具有Slot风格的Hash值，后续Render里搞图片的时候跳过这些
        slot_style_texture_hash_list = []
        for draw_ib_model in drawib_drawibmodel_dict.values():
            for texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.values():
                for texture_markup_info in texture_markup_info_list:
                    if texture_markup_info.mark_type == "Slot":
                        slot_style_texture_hash_list.append(texture_markup_info.mark_hash)
                    
        repeat_hash_list = []
        # 遍历当前drawib的Render文件夹
        for draw_ib,draw_ib_model in drawib_drawibmodel_dict.items():

            hash_deduped_texture_info_dict = WorkSpaceHelper.get_hash_deduped_texture_info_dict(draw_ib=draw_ib)



            # 添加标记的Hash风格贴图
            for texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.values():
                for texture_markup_info in texture_markup_info_list:
                    if texture_markup_info.mark_type != "Hash":
                        continue

                    if texture_markup_info.mark_hash in repeat_hash_list:
                        continue
                    else:
                        repeat_hash_list.append(texture_markup_info.mark_hash)

                    original_texture_file_path = GlobalConfig.path_extract_gametype_folder(draw_ib=draw_ib,gametype_name=draw_ib_model.d3d11GameType.GameTypeName) + texture_markup_info.mark_filename
                    if not os.path.exists(original_texture_file_path):
                        continue

                    hash_style_texture_filename = ""
                    hash_style_texture_filename = hash_style_texture_filename + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_"

                    deduped_texture_info = hash_deduped_texture_info_dict.get(texture_markup_info.mark_hash,None)
                    if deduped_texture_info is None:
                        raise Fatal("在生成Mod的过程中，发现贴图标记的Hash值在提取的游戏类型文件夹中不存在对应的贴图文件，无法继续生成Mod，请检查工作空间内容与提取的游戏类型文件夹内容是否匹配，或者手动替换该贴图后再生成Mod。\n缺失贴图信息:\nDrawIB:" + draw_ib + "\n标记贴图文件名:" + texture_markup_info.mark_filename + "\n标记Hash值:" + texture_markup_info.mark_hash)

                    component_count_list_str = deduped_texture_info.componet_count_list_str
                    hash_style_texture_filename = hash_style_texture_filename + "_" + component_count_list_str + "_"
                    hash_style_texture_filename = hash_style_texture_filename + deduped_texture_info.original_hash + "_" + deduped_texture_info.render_hash + "_" + deduped_texture_info.format + "_" + texture_markup_info.mark_name

                    hash_style_texture_filename = hash_style_texture_filename + "." + texture_markup_info.mark_filename.split(".")[1]
                    print(texture_markup_info.mark_filename)
                    print(texture_markup_info.get_hash_style_filename())




                    target_texture_file_path = GlobalConfig.path_generatemod_texture_folder(draw_ib=draw_ib) + hash_style_texture_filename
                    
                    resource_and_textureoverride_texture_section = M_IniSection(M_SectionType.ResourceAndTextureOverride_Texture)
                    resource_and_textureoverride_texture_section.append("[Resource_Texture_" + texture_markup_info.mark_hash + "]")
                    resource_and_textureoverride_texture_section.append("filename = Texture/" + hash_style_texture_filename)
                    resource_and_textureoverride_texture_section.new_line()

                    resource_and_textureoverride_texture_section.append("[TextureOverride_" + texture_markup_info.mark_hash + "]")
                    resource_and_textureoverride_texture_section.append("; " + texture_markup_info.mark_filename)
                    resource_and_textureoverride_texture_section.append("hash = " + texture_markup_info.mark_hash)
                    resource_and_textureoverride_texture_section.append("match_priority = 0")
                    resource_and_textureoverride_texture_section.append("this = Resource_Texture_" + texture_markup_info.mark_hash)
                    resource_and_textureoverride_texture_section.new_line()

                    ini_builder.append_section(resource_and_textureoverride_texture_section)

                    # copy only if target not exists avoid overwrite texture manually replaced by mod author.
                    if not os.path.exists(target_texture_file_path):
                        shutil.copy2(original_texture_file_path,target_texture_file_path)

            # 现在除了WWMI外都不使用全局Hash贴图风格，而是上面的标记的Hash风格贴图
            if GlobalConfig.logic_name != LogicName.WWMI and GlobalConfig.logic_name != LogicName.WuWa:
                continue


            

        # if len(repeat_hash_list) != 0:
        #     texture_ini_builder.save_to_file(MainConfig.path_generate_mod_folder() + MainConfig.workspacename + "_Texture.ini")

    @classmethod
    def move_slot_style_textures(cls,draw_ib_model:DrawIBModel):
        '''
        Move all textures from extracted game type folder to generate mod Texture folder.
        Only works in default slot style texture.
        '''
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return
        
        for texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.values():
            for texture_markup_info in texture_markup_info_list:
                # 只有槽位风格会移动到目标位置
                if texture_markup_info.mark_type != "Slot":
                    continue

                target_path = GlobalConfig.path_generatemod_texture_folder(draw_ib=draw_ib_model.draw_ib) + texture_markup_info.mark_filename
                source_path = draw_ib_model.import_config.extract_gametype_folder_path + texture_markup_info.mark_filename
                
                # only overwrite when there is no texture file exists.
                if not os.path.exists(target_path):
                    print("Move Texture File: " + texture_markup_info.mark_filename)
                    shutil.copy2(source_path,target_path)

    @classmethod
    def add_branch_key_sections(cls,ini_builder:M_IniBuilder,key_name_mkey_dict:dict[str,M_Key]):

        if len(key_name_mkey_dict.keys()) != 0:
            constants_section = M_IniSection(M_SectionType.Constants)
            constants_section.SectionName = "Constants"

            for i in range(M_GlobalKeyCounter.generated_mod_number):
                constants_section.append("global $active" + str(i))

            for mkey in key_name_mkey_dict.values():
                key_str = "global persist " + mkey.key_name + " = " + str(mkey.initialize_value)
                constants_section.append(key_str) 

            ini_builder.append_section(constants_section)


        if len(key_name_mkey_dict.keys()) != 0:
            present_section = M_IniSection(M_SectionType.Present)
            present_section.SectionName = "Present"

            for i in range(M_GlobalKeyCounter.generated_mod_number):
                present_section.append("post $active" + str(i) + " = 0")
            ini_builder.append_section(present_section)
        
        key_number = 0
        if len(key_name_mkey_dict.keys()) != 0:

            for mkey in key_name_mkey_dict.values():
                key_section = M_IniSection(M_SectionType.Key)
                key_section.append("[KeySwap_" + str(key_number) + "]")
                # key_section.append("condition = $active" + str(key_number) + " == 1")

                # XXX 这里由于有BUG，我们固定用$active0来检测激活，不搞那么复杂了。
                key_section.append("condition = $active0 == 1")

                if mkey.initialize_vk_str != "":
                    key_section.append("key = " + mkey.initialize_vk_str)
                else:
                    key_section.append("key = " + mkey.key_value)
                key_section.append("type = cycle")

                key_value_number = len(mkey.value_list)
                key_cycle_str = ""
                for i in range(key_value_number):
                    if i < key_value_number + 1:
                        key_cycle_str = key_cycle_str + str(i) + ","
                    else:
                        key_cycle_str = key_cycle_str + str(i)
                key_section.append(mkey.key_name + " = " + key_cycle_str)
                key_section.new_line()
                ini_builder.append_section(key_section)

                key_number = key_number + 1