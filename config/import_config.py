import os 
import json
import bpy
import json
import math
import bmesh
import os


from typing import List, Dict, Union, Optional
from dataclasses import dataclass, field, asdict

from ..utils.json_utils import JsonUtils
from ..utils.format_utils import Fatal

from .main_config import GlobalConfig

from ..base.d3d11_gametype import D3D11GameType


def check_and_try_generate_import_json() -> dict:
    '''
    检查 Import.json 是否存在，如果不存在则尝试自动生成
    返回 draw_ib_gametypename_dict
    '''
    workspace_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
    
    if os.path.exists(workspace_import_json_path):
        return JsonUtils.LoadFromFile(workspace_import_json_path)
    
    print("Import.json 不存在，尝试自动生成...")
    
    from ..utils.config_utils import ConfigUtils
    
    draw_ib_gametypename_dict = {}
    
    try:
        draw_ib_pair_list = ConfigUtils.get_extract_drawib_list_from_workspace_config_json()
    except Exception as e:
        raise Fatal(f"无法读取工作空间配置: {str(e)}\n请确保已在SSMT中正确配置工作空间。")
    
    current_workspace_folder = GlobalConfig.path_workspace_folder()
    
    for draw_ib_pair in draw_ib_pair_list:
        draw_ib = draw_ib_pair.DrawIB
        import_drawib_folder_path = os.path.join(current_workspace_folder, draw_ib)
        
        if not os.path.exists(import_drawib_folder_path):
            print(f"DrawIB {draw_ib} 的文件夹不存在，跳过")
            continue
        
        dirs = os.listdir(import_drawib_folder_path)
        gpu_folders = []
        cpu_folders = []
        
        for dirname in dirs:
            if not dirname.startswith("TYPE_"):
                continue
            folder_path = os.path.join(import_drawib_folder_path, dirname)
            if dirname.startswith("TYPE_GPU"):
                gpu_folders.append(folder_path)
            elif dirname.startswith("TYPE_CPU"):
                cpu_folders.append(folder_path)
        
        all_folders = gpu_folders + cpu_folders
        
        for folder_path in all_folders:
            tmp_json_path = os.path.join(folder_path, "tmp.json")
            if os.path.exists(tmp_json_path):
                try:
                    tmp_json = ConfigUtils.read_tmp_json(folder_path)
                    work_game_type = tmp_json.get("WorkGameType", "")
                    if work_game_type:
                        draw_ib_gametypename_dict[draw_ib] = work_game_type
                        print(f"自动检测到 DrawIB {draw_ib} 的数据类型: {work_game_type}")
                        break
                except Exception as e:
                    print(f"读取 {tmp_json_path} 失败: {e}")
                    continue
    
    if draw_ib_gametypename_dict:
        JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict, filepath=workspace_import_json_path)
        print(f"已自动生成 Import.json: {workspace_import_json_path}")
    else:
        print("警告: 无法自动生成 Import.json，没有找到有效的提取数据")
    
    return draw_ib_gametypename_dict


def check_tmp_json_exists(draw_ib: str, gametypename: str) -> tuple[bool, str, Optional[str]]:
    '''
    检查 tmp.json 是否存在
    返回: (是否存在, 错误信息, 找到的tmp.json路径)
    '''
    if not gametypename:
        workspace_folder = GlobalConfig.path_workspace_folder()
        draw_ib_folder = os.path.join(workspace_folder, draw_ib)
        
        if os.path.exists(draw_ib_folder):
            dirs = os.listdir(draw_ib_folder)
            found_types = []
            for dirname in dirs:
                if dirname.startswith("TYPE_"):
                    type_folder = os.path.join(draw_ib_folder, dirname)
                    tmp_json_path = os.path.join(type_folder, "tmp.json")
                    if os.path.exists(tmp_json_path):
                        found_types.append(dirname.replace("TYPE_", ""))
            
            if found_types:
                return False, f"DrawIB '{draw_ib}' 找到以下数据类型但没有在 Import.json 中记录: {', '.join(found_types)}\n请尝试重新执行「一键导入当前工作空间内容」操作。", None
        
        return False, f"DrawIB '{draw_ib}' 没有找到对应的提取数据。\n请确保已从游戏中提取模型并执行「一键导入当前工作空间内容」操作。", None
    
    extract_gametype_folder_path = GlobalConfig.path_extract_gametype_folder(draw_ib=draw_ib, gametype_name=gametypename)
    tmp_json_path = os.path.join(extract_gametype_folder_path, "tmp.json")
    
    if os.path.exists(tmp_json_path):
        return True, "", tmp_json_path
    
    return False, f"找不到 tmp.json 文件: {tmp_json_path}\n请确保已从游戏中提取模型并执行「一键导入当前工作空间内容」操作。", None

@dataclass
class TextureMarkUpInfo:
    mark_name:str = field(default="",init=False)
    mark_type:str = field(default="",init=False)
    mark_hash:str = field(default="",init=False)
    mark_slot:str = field(default="",init=False)
    mark_filename:str = field(default="",init=False)
    
    def get_resource_name(self):
        return "Resource-" + self.mark_filename.split(".")[0]
    
    def get_hash_style_filename(self):
        return self.mark_hash + "-" + self.mark_name + "." + self.mark_filename.split(".")[1]

@dataclass
class ImportConfig:
    '''
    在一键导入工作空间时，Import.json会记录导入的GameType，在生成Mod时需要用到
    所以这里我们读取Import.json来确定要从哪个提取出来的数据类型文件夹中读取
    然后读取tmp.json来初始化D3D11GameType
    '''
    draw_ib: str  # DrawIB
    
    # 使用field(default_factory)来初始化可变默认值
    category_hash_dict: Dict[str, str] = field(init=False,default_factory=dict)
    import_model_list: List[str] = field(init=False,default_factory=list)
    match_first_index_list: List[int] = field(init=False,default_factory=list)
    part_name_list: List[str] = field(init=False,default_factory=list)
    vshash_list: List[str] = field(init=False,default_factory=list)
    
    vertex_limit_hash: str = ""
    work_game_type: str = ""
    
    # 全新的贴图标记设计
    partname_texturemarkinfolist_dict:Dict[str,list[TextureMarkUpInfo]] = field(init=False,default_factory=dict)

    def __post_init__(self):
        draw_ib_gametypename_dict = check_and_try_generate_import_json()
        gametypename = draw_ib_gametypename_dict.get(self.draw_ib,"")

        extract_gametype_folder_path = GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=gametypename)
        self.extract_gametype_folder_path = extract_gametype_folder_path
        tmp_json_path = os.path.join(extract_gametype_folder_path,"tmp.json")
        
        from ..blueprint.blueprint_export_helper import BlueprintExportHelper
        datatype_node_info_list = BlueprintExportHelper.get_datatype_node_info()
        
        matched_datatype_node_info = None
        if datatype_node_info_list:
            for node_info in datatype_node_info_list:
                node = node_info["node"]
                if node.is_draw_ib_matched(self.draw_ib):
                    matched_datatype_node_info = node_info
                    print(f"找到匹配的数据类型节点，DrawIB: {self.draw_ib}, 节点: {node.name}")
                    break
        
        if not os.path.exists(tmp_json_path):
            exists, error_msg, found_path = check_tmp_json_exists(self.draw_ib, gametypename)
            if not exists:
                raise Fatal(error_msg)
            if found_path:
                tmp_json_path = found_path
        
        if matched_datatype_node_info and matched_datatype_node_info.get("tmp_json_path") and os.path.exists(matched_datatype_node_info["tmp_json_path"]):
            with open(tmp_json_path, 'r', encoding='utf-8') as f:
                base_tmp_json_dict = json.load(f)
            with open(matched_datatype_node_info["tmp_json_path"], 'r', encoding='utf-8') as f:
                datatype_tmp_json_dict = json.load(f)
            
            if "D3D11ElementList" in datatype_tmp_json_dict:
                base_tmp_json_dict["D3D11ElementList"] = datatype_tmp_json_dict["D3D11ElementList"]
                print(f"使用数据类型节点的 D3D11ElementList 覆盖原始配置")
            
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                json.dump(base_tmp_json_dict, f, indent=2, ensure_ascii=False)
                merged_tmp_json_path = f.name
            
            self.d3d11GameType:D3D11GameType = D3D11GameType(merged_tmp_json_path)
            tmp_json_dict = base_tmp_json_dict
            
            try:
                os.unlink(merged_tmp_json_path)
            except:
                pass
        else:
            self.d3d11GameType:D3D11GameType = D3D11GameType(tmp_json_path)
            tmp_json_dict = JsonUtils.LoadFromFile(tmp_json_path)
        
        '''
        读取tmp.json中的内容，后续会用于生成Mod的ini文件
        需要在确定了D3D11GameType之后再执行
        注意：这里使用已经确定的 tmp_json_dict
        '''
        self.category_hash_dict = tmp_json_dict["CategoryHash"]
        self.import_model_list = tmp_json_dict["ImportModelList"]
        self.match_first_index_list = tmp_json_dict["MatchFirstIndex"]
        self.part_name_list = tmp_json_dict["PartNameList"]
        # print(self.partname_textureresourcereplace_dict)
        self.vertex_limit_hash = tmp_json_dict["VertexLimitVB"]
        self.work_game_type = tmp_json_dict["WorkGameType"]
        self.vshash_list = tmp_json_dict.get("VSHashList",[])
        self.original_vertex_count = tmp_json_dict.get("OriginalVertexCount",0)

        # 自动贴图依赖于这个字典
        partname_texturemarkupinfolist_jsondict = tmp_json_dict["ComponentTextureMarkUpInfoListDict"]


        print("读取配置: " + tmp_json_path)
        # print(partname_textureresourcereplace_dict)
        for partname, texture_markup_info_dict_list in partname_texturemarkupinfolist_jsondict.items():

            texture_markup_info_list = []

            for texture_markup_info_dict in texture_markup_info_dict_list:
                markup_info = TextureMarkUpInfo()
                markup_info.mark_name = texture_markup_info_dict["MarkName"]
                markup_info.mark_type = texture_markup_info_dict["MarkType"]
                markup_info.mark_slot = texture_markup_info_dict["MarkSlot"]
                markup_info.mark_hash = texture_markup_info_dict["MarkHash"]
                markup_info.mark_filename = texture_markup_info_dict["MarkFileName"]

                texture_markup_info_list.append(markup_info)

            self.partname_texturemarkinfolist_dict[partname] = texture_markup_info_list





                


                


