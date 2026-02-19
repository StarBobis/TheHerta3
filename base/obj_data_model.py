from .m_condition import M_Condition
from .m_draw_indexed import M_DrawIndexed


from dataclasses import dataclass, field

@dataclass
class ObjDataModel:
    obj_name:str
    display_name:str = field(init=False,repr=False,default="")

    component_count:int = field(init=False,repr=False,default=0)
    draw_ib:str = field(init=False,repr=False,default="")
    obj_alias_name:str = field(init=False,repr=False)

    ib:list = field(init=False,repr=False,default_factory=list)
    category_buffer_dict:dict = field(init=False,repr=False,default_factory=dict)

    # 仅用于WWMI的索引顶点ID字典，key是顶点索引，value是顶点ID，默认可以为None
    index_vertex_id_dict:dict = field(init=False,repr=False,default_factory=dict) 

    condition:M_Condition = field(init=False,repr=False,default_factory=M_Condition)
    drawindexed_obj:M_DrawIndexed = field(init=False,repr=False,default_factory=M_DrawIndexed)

    def __post_init__(self):
        self.display_name = self.obj_name
        if "-" in self.obj_name:
            obj_name_split = self.obj_name.split("-")
            self.draw_ib = obj_name_split[0]
            self.component_count = int(obj_name_split[1])
            self.obj_alias_name = obj_name_split[2]
       