from .obj_data_model import ObjDataModel

from dataclasses import dataclass, field
from typing import Dict

@dataclass
class ComponentModel:
    '''
    一个小数据结构，用来更方便的表示数据之间的关系，用于传递数据
    '''
    component_name:str
    final_ordered_draw_obj_model_list:list[ObjDataModel]

