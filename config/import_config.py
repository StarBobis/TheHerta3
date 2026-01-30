import os 
import json
import bpy
import json
import math
import bmesh
import os


from typing import List, Dict, Union
from dataclasses import dataclass, field, asdict

from ..utils.json_utils import JsonUtils
from ..utils.format_utils import Fatal

from .main_config import GlobalConfig

from ..base.d3d11_gametype import D3D11GameType

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
        workspace_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(), "Import.json")
        draw_ib_gametypename_dict = JsonUtils.LoadFromFile(workspace_import_json_path)
        gametypename = draw_ib_gametypename_dict.get(self.draw_ib,"")

        # 新版本中，我们把数据类型的信息写到了tmp.json中，这样我们就能够读取tmp.json中的内容来决定生成Mod时的数据类型了。
        extract_gametype_folder_path = GlobalConfig.path_extract_gametype_folder(draw_ib=self.draw_ib,gametype_name=gametypename)
        self.extract_gametype_folder_path = extract_gametype_folder_path
        tmp_json_path = os.path.join(extract_gametype_folder_path,"tmp.json")
        
        # 检查是否存在数据类型节点，如果存在则使用数据类型节点指定的 tmp.json 文件
        from ..blueprint.blueprint_export_helper import BlueprintExportHelper
        datatype_node_info_list = BlueprintExportHelper.get_datatype_node_info()
        
        # 查找匹配当前 DrawIB 的数据类型节点
        matched_datatype_node_info = None
        if datatype_node_info_list:
            for node_info in datatype_node_info_list:
                node = node_info["node"]
                if node.is_draw_ib_matched(self.draw_ib):
                    matched_datatype_node_info = node_info
                    print(f"找到匹配的数据类型节点，DrawIB: {self.draw_ib}, 节点: {node.name}")
                    break
        
        if os.path.exists(tmp_json_path):
            # 如果存在匹配的数据类型节点，则合并两个 tmp.json 文件
            if matched_datatype_node_info and matched_datatype_node_info.get("tmp_json_path") and os.path.exists(matched_datatype_node_info["tmp_json_path"]):
                import json
                with open(tmp_json_path, 'r', encoding='utf-8') as f:
                    base_tmp_json_dict = json.load(f)
                with open(matched_datatype_node_info["tmp_json_path"], 'r', encoding='utf-8') as f:
                    datatype_tmp_json_dict = json.load(f)
                
                # 使用数据类型节点的 D3D11ElementList 覆盖原始的
                if "D3D11ElementList" in datatype_tmp_json_dict:
                    base_tmp_json_dict["D3D11ElementList"] = datatype_tmp_json_dict["D3D11ElementList"]
                    print(f"使用数据类型节点的 D3D11ElementList 覆盖原始配置")
                
                # 保存合并后的配置到临时文件
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as f:
                    json.dump(base_tmp_json_dict, f, indent=2, ensure_ascii=False)
                    merged_tmp_json_path = f.name
                
                self.d3d11GameType:D3D11GameType = D3D11GameType(merged_tmp_json_path)
                tmp_json_dict = base_tmp_json_dict
                
                # 删除临时文件
                try:
                    os.unlink(merged_tmp_json_path)
                except:
                    pass
            else:
                self.d3d11GameType:D3D11GameType = D3D11GameType(tmp_json_path)
                tmp_json_dict = JsonUtils.LoadFromFile(tmp_json_path)
        else:
            raise Fatal("您还没有提取模型并一键导入当前工作空间内容，如果您是在Mod逆向后直接生成Mod，那么步骤是错误的，Mod逆向只是拿到模型文件，要生成Mod还需要从游戏中提取原模型以获取模型的Hash值等用于生成Mod的重要信息，随后在Blender中一键导入当前工作空间内容后，即可选中工作空间集合来生成Mod。\n可以理解为：Mod逆向只是拿到模型和贴图，后面的步骤就和Mod逆向没有关系了，全部需要走Mod制作的标准流程")
        
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





                


                


