'''
基础数据类型
'''

import json
import os

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class D3D11Element:
    SemanticName:str
    SemanticIndex:int
    Format:str
    ByteWidth:int
    # Which type of slot and slot number it use? eg:vb0
    ExtractSlot:str
    # Is it from pointlist or trianglelist or compute shader?
    ExtractTechnique:str
    # Human named category, also will be the buf file name suffix.
    Category:str

    # Fixed items
    InputSlot:str = field(default="0", init=False, repr=False)
    InputSlotClass:str = field(default="per-vertex", init=False, repr=False)
    InstanceDataStepRate:str = field(default="0", init=False, repr=False)

    # Generated Items
    ElementNumber:int = field(init=False,default=0)
    AlignedByteOffset:int
    ElementName:str = field(init=False,default="")

    def __post_init__(self):
        self.ElementName = self.get_indexed_semantic_name()

    def get_indexed_semantic_name(self)->str:
        if self.SemanticIndex == 0:
            return self.SemanticName
        else:
            return self.SemanticName + str(self.SemanticIndex)



class M_DrawIndexed:
    def __init__(self) -> None:
        self.DrawNumber = ""

        # 绘制起始位置
        self.DrawOffsetIndex = "" 

        self.DrawStartIndex = "0"

        # 代表一个obj具体的draw_indexed
        self.AliasName = "" 

        # 代表这个obj的顶点数
        self.UniqueVertexCount = 0 
    
    def get_draw_str(self) ->str:
        return "drawindexed = " + self.DrawNumber + "," + self.DrawOffsetIndex +  "," + self.DrawStartIndex

class M_Key:
    '''
    key_name 声明的key名称，一般按照声明顺序为$swapkey + 数字
    key_value 具体的按键VK值
    '''

    def __init__(self):
        self.key_name = ""
        self.key_value = ""
        self.value_list:list[int] = []
        
        self.initialize_value = 0
        self.initialize_vk_str = "" # 虚拟按键组合，遵循3Dmigoto的解析格式

        # 用于chain_key_list中传递使用，
        self.tmp_value = 0

    def __str__(self):
        return (f"M_Key(key_name='{self.key_name}', key_value='{self.key_value}', "
                f"value_list={self.value_list}, initialize_value={self.initialize_value}, "
                f"tmp_value={self.tmp_value})")
    

class M_Condition:
    def __init__(self,work_key_list:list[M_Key] = []):
        self.work_key_list = work_key_list

        # 计算出生效的ConditionStr
        condition_str = ""
        if len(self.work_key_list) != 0:
            for work_key in self.work_key_list:
                single_condition:str = work_key.key_name + " == " + str(work_key.tmp_value)
                condition_str = condition_str + single_condition + " && "
            # 移除结尾的最后四个字符 " && "
            condition_str = condition_str[:-4] 
        
        self.condition_str = condition_str


class ObjDataModel:
    def __init__(self,obj_name:str):
        self.obj_name = obj_name
        
        # 因为现在的obj都需要遵守命名规则
        print(self.obj_name)
        obj_name_split = self.obj_name.split("-")
        self.draw_ib = obj_name_split[0]

        # 鸣潮生成的临时obj不会遵循命名规范，这里的值也不需要设置
        # 这里是旧代码的遗留问题，暂时只添加个兼容处理即可。
        if "-" in self.obj_name:
            self.component_count = int(obj_name_split[1])
            self.obj_alias_name = obj_name_split[2]

        # 其它属性
        self.ib = []
        self.category_buffer_dict = {}
        self.index_vertex_id_dict = {} # 仅用于WWMI的索引顶点ID字典，key是顶点索引，value是顶点ID，默认可以为None
        self.condition:M_Condition = M_Condition()
        self.drawindexed_obj:M_DrawIndexed = M_DrawIndexed()


# Designed to read from json file for game type config
@dataclass
class D3D11GameType:
    # Read config from json file, easy to modify and test.
    FilePath:str = field(repr=False)

    # Original file name.
    FileName:str = field(init=False,repr=False)
    # The name of the game type, usually the filename without suffix.
    GameTypeName:str = field(init=False)
    # Is GPU-PreSkinning or CPU-PreSkinning
    GPU_PreSkinning:bool = field(init=False,default=False)
    # All d3d11 element,should be already ordered in config json.
    D3D11ElementList:list[D3D11Element] = field(init=False,repr=False)
    # Ordered ElementName list.
    OrderedFullElementList:list[str] = field(init=False,repr=False)
    # 按顺序排列的CategoryName
    OrderedCategoryNameList:list[str] = field(init=False,repr=False)
    # Category name and draw category name, used to decide the category should draw on which category's TextureOverrideVB.
    CategoryDrawCategoryDict:Dict[str,str] = field(init=False,repr=False)


    # Generated
    ElementNameD3D11ElementDict:Dict[str,D3D11Element] = field(init=False,repr=False)
    CategoryExtractSlotDict:Dict[str,str] =  field(init=False,repr=False)
    CategoryExtractTechniqueDict:Dict[str,str] =  field(init=False,repr=False)
    CategoryStrideDict:Dict[str,int] =  field(init=False,repr=False)

    def __post_init__(self):
        self.FileName = os.path.basename(self.FilePath)
        self.GameTypeName = os.path.splitext(self.FileName)[0]
        

        self.OrderedFullElementList = []
        self.OrderedCategoryNameList = []
        self.D3D11ElementList = []

        self.CategoryDrawCategoryDict = {}
        self.CategoryExtractSlotDict = {}
        self.CategoryExtractTechniqueDict = {}
        self.CategoryStrideDict = {}
        self.ElementNameD3D11ElementDict = {}

        # read config from json file.
        with open(self.FilePath, 'r', encoding='utf-8') as f:
            game_type_json = json.load(f)
        
        self.GPU_PreSkinning = game_type_json.get("GPU-PreSkinning",False)

        self.GameTypeName = game_type_json.get("WorkGameType","")

        # self.OrderedFullElementList = game_type_json.get("OrderedFullElementList",[])
        self.CategoryDrawCategoryDict = game_type_json.get("CategoryDrawCategoryMap",{})
        d3d11_element_list_json = game_type_json.get("D3D11ElementList",[])
        aligned_byte_offset = 0
        for d3d11_element_json in d3d11_element_list_json:
            d3d11_element = D3D11Element(
                SemanticName=d3d11_element_json.get("SemanticName",""),
                SemanticIndex=int(d3d11_element_json.get("SemanticIndex","")),
                Format=d3d11_element_json.get("Format",""),
                ByteWidth=int(d3d11_element_json.get("ByteWidth",0)),
                ExtractSlot=d3d11_element_json.get("ExtractSlot",""),
                ExtractTechnique=d3d11_element_json.get("ExtractTechnique",""),
                Category=d3d11_element_json.get("Category",""),
                AlignedByteOffset=aligned_byte_offset
            )
            aligned_byte_offset = aligned_byte_offset + d3d11_element.ByteWidth
            self.D3D11ElementList.append(d3d11_element)

            # 这俩常用
            self.OrderedFullElementList.append(d3d11_element.get_indexed_semantic_name())
            if d3d11_element.Category not in self.OrderedCategoryNameList:
                self.OrderedCategoryNameList.append(d3d11_element.Category)
        
        for d3d11_element in self.D3D11ElementList:
            self.CategoryExtractSlotDict[d3d11_element.Category] = d3d11_element.ExtractSlot
            self.CategoryExtractTechniqueDict[d3d11_element.Category] = d3d11_element.ExtractTechnique
            self.CategoryStrideDict[d3d11_element.Category] = self.CategoryStrideDict.get(d3d11_element.Category,0) + d3d11_element.ByteWidth
            self.ElementNameD3D11ElementDict[d3d11_element.ElementName] = d3d11_element
    
    def get_real_category_stride_dict(self) -> dict:
        new_dict = {}
        for categoryname,category_stride in self.CategoryStrideDict.items():
            new_dict[categoryname] = category_stride
        return new_dict

  
