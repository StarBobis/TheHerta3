import bpy
import os
import json


from ..config.properties_generate_mod import Properties_GenerateMod

'''
执行逻辑名称
理论上多个执行名称可以公用一套生成Mod逻辑
但最好是每个执行逻辑名称单独一套生成Mod逻辑
'''
class LogicName:
    UnityVS = "UnityVS"
    UnityCS = "UnityCS"
    UnityCSM = "UnityCSM"
    UnityCPU = "UnityCPU"
    
    GIMI = "GIMI"
    HIMI = "HIMI"
    SRMI = "SRMI"
    ZZMI = "ZZMI"
    WWMI = "WWMI"
    EFMI = "EFMI"

    WuWa = "WuWa"

    CTXMC = "CTXMC"
    IdentityV2 = "IdentityV2"
    NierR = "NierR"
    YYSLS = "YYSLS"
    AILIMIT = "AILIMIT"
    HOK = "HOK"
    SnowBreak = "SnowBreak"
    AEMI = "AEMI"

# 全局配置类，使用字段默认为全局可访问的唯一静态变量的特性，来实现全局变量
# 可减少从Main.json中读取的IO消耗
class GlobalConfig:
    # 全局静态变量,任何地方访问到的值都是唯一的
    gamename = ""
    workspacename = ""
    dbmtlocation = ""
    current_game_migoto_folder = ""
    logic_name = ""

    # 适配的SSMT最低版本号
    ssmt_version_number = 0

    # 多文件导出功能：Buffer文件夹后缀（如"01"、"02"等）
    buffer_folder_suffix = ""

    @classmethod
    def read_from_main_json(cls) :
        try:
            main_json_path = GlobalConfig.path_main_json()

            # 先从main_json_path里读取dbmt位置，也就是dbmt总工作空间的位置
            # 在新架构中，总工作空间位置已不会再发生改变，所以用户只需要选择一次就可以了
            if os.path.exists(main_json_path):
                main_setting_file = open(main_json_path)
                main_setting_json = json.load(main_setting_file)
                main_setting_file.close()
                cls.workspacename = main_setting_json.get("CurrentWorkSpace","")
                cls.gamename = main_setting_json.get("CurrentGameName","")
                cls.dbmtlocation = main_setting_json.get("DBMTWorkFolder","") + "\\"
                cls.ssmt_version_number = main_setting_json.get("VersionNumber",0)
            else:
                print("Can't find: " + main_json_path)
            
            game_config_json_path = os.path.join(GlobalConfig.path_ssmt3_global_configs_folder(),"Games\\" + cls.gamename + "\\Config.json")
            if os.path.exists(game_config_json_path):
                game_config_json_file = open(game_config_json_path)
                game_config_json = json.load(game_config_json_file)
                game_config_json_file.close()

                cls.current_game_migoto_folder = game_config_json.get("3DmigotoPath","")
                cls.logic_name = game_config_json.get("LogicName","")
        except Exception as e:
            print(e)
            
    @classmethod
    def base_path(cls):
        return cls.dbmtlocation
    
    @classmethod
    def path_configs_folder(cls):
        return os.path.join(GlobalConfig.base_path(),"Configs\\")
    
    @classmethod
    def path_reverse_output_folder(cls):
        # 先从main_json_path里读取dbmt位置，也就是dbmt总工作空间的位置
        # 在新架构中，总工作空间位置已不会再发生改变，所以用户只需要选择一次就可以了
        if os.path.exists(cls.path_main_json()):
            main_setting_file = open(cls.path_main_json())
            main_setting_json = json.load(main_setting_file)
            main_setting_file.close()
            reverse_output_folder = main_setting_json.get("ReverseOutputFolder","") + "\\"
            
            print(reverse_output_folder)
            return reverse_output_folder
        else:
            return ""

    @classmethod
    def path_mods_folder(cls):
        return os.path.join(cls.current_game_migoto_folder,"Mods\\") 

    @classmethod
    def path_total_workspace_folder(cls):
        return os.path.join(GlobalConfig.base_path(),"WorkSpace\\") 
    
    @classmethod
    def path_current_game_total_workspace_folder(cls):
        return os.path.join(GlobalConfig.path_total_workspace_folder(),GlobalConfig.gamename + "\\") 
    
    @classmethod
    def path_workspace_folder(cls):
        return os.path.join(GlobalConfig.path_current_game_total_workspace_folder(), GlobalConfig.workspacename + "\\")
    
    @classmethod
    def path_generate_mod_folder(cls):
        # 如果用户勾选了使用指定文件夹，那就返回指定文件夹位置，否则返回我们的默认位置。
        # 但是这里有个问题就是SkipIB和VSCheck不会生成在指定位置。
        if Properties_GenerateMod.use_specific_generate_mod_folder_path():
            return Properties_GenerateMod.generate_mod_folder_path()
        else:
            # 确保用的时候直接拿到的就是已经存在的目录
            ssmt_generated_mod_folder_path = os.path.join(GlobalConfig.path_mods_folder(),"SSMTGeneratedMod\\")
            ssmt_generated_mod_default_folder_path = os.path.join(ssmt_generated_mod_folder_path,"Default\\")

            generate_mod_folder_path = os.path.join(ssmt_generated_mod_default_folder_path,"Mod_" + GlobalConfig.workspacename + "\\")

            if not os.path.exists(generate_mod_folder_path):
                os.makedirs(generate_mod_folder_path)
            return generate_mod_folder_path
    
    @classmethod
    def path_extract_gametype_folder(cls,draw_ib:str,gametype_name:str):
        return os.path.join(GlobalConfig.path_workspace_folder(), draw_ib + "\\TYPE_" + gametype_name + "\\")
    
    @classmethod
    def path_generatemod_buffer_folder(cls):
       
        buffer_folder_name = "Buffer"
        if cls.buffer_folder_suffix:
            buffer_folder_name = f"Buffer{cls.buffer_folder_suffix}"
        
        buffer_path = os.path.join(GlobalConfig.path_generate_mod_folder(), buffer_folder_name + "\\")
        if not os.path.exists(buffer_path):
            os.makedirs(buffer_path)
        return buffer_path
    
    @classmethod
    def get_buffer_folder_name(cls):
        """获取当前Buffer文件夹名称（用于INI文件中的路径引用）"""
        buffer_folder_name = "Buffer"
        if cls.buffer_folder_suffix:
            buffer_folder_name = f"Buffer{cls.buffer_folder_suffix}"
        return buffer_folder_name
    
    @classmethod
    def path_generatemod_texture_folder(cls,draw_ib:str):

        texture_path = os.path.join(GlobalConfig.path_generate_mod_folder(),"Texture\\")
        if not os.path.exists(texture_path):
            os.makedirs(texture_path)
        return texture_path
    
    @classmethod
    def path_appdata_local(cls):
        return os.path.join(os.environ['LOCALAPPDATA'])
    
    @classmethod
    def path_ssmt3_global_configs_folder(cls):
        return os.path.join(GlobalConfig.path_appdata_local(),"SSMT3GlobalConfigs\\")
    
    # 定义基础的Json文件路径
    @classmethod
    def path_main_json(cls):
        return os.path.join(GlobalConfig.path_ssmt3_global_configs_folder(), "SSMT3-Config.json")
        



    
