'''
新的设计，把旧的BufferModel和MeshExporter以及ObjDataModel整合到一起了
因为从结果上来看，BufferModel和MeshExporter只调用了一次，属于严重浪费
不如直接传入d3d11_game_type和obj_name到ObjBufferModel，然后直接一次性得到所有的内容

ObjBufferModel一创建，就自动把所有的内容都搞定了，后面只需要直接拿去使用就行了
'''

import collections
import numpy
import bpy

from dataclasses import dataclass, field
from typing import Dict

from ..utils.format_utils import FormatUtils, Fatal
from ..utils.timer_utils import TimerUtils
from ..utils.vertexgroup_utils import VertexGroupUtils
from ..utils.obj_utils import ObjUtils
from ..utils.shapekey_utils import ShapeKeyUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from ..base.obj_data_model import ObjDataModel

from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ObjElementModel:
    d3d11_game_type:D3D11GameType
    obj_name:str

    # 外用字段
    obj:bpy.types.Object = field(init=False,repr=False)
    mesh:bpy.types.Mesh = field(init=False,repr=False)
    total_structured_dtype:numpy.dtype = field(init=False, repr=False)
    
    # 数据先从obj中提取出来，按 ElementName 放到这个 Dict 中，作为原始未修改数据
    original_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)
    
    # 如果有修改，例如BlendRemapIndices就放到这里
    final_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)

    # 最终数据被写入到这个 ndarray 中，传递给buffer model
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    def __post_init__(self) -> None:
        self.obj = ObjUtils.get_obj_by_name(name=self.obj_name)

        # 重置形态键，因为用户不一定会重置，咱们帮他重置好了
        ShapeKeyUtils.reset_shapekey_values(self.obj)

        # 这里获取应用了形态键之后的mesh数据
        # 注意：物体在导出前已经被 BEAUTY 三角化，所以这里不需要再次三角化
        mesh = ObjUtils.get_mesh_evaluate_from_obj(obj=self.obj)

        # 前提是有UVMap，前面的步骤应该保证了模型至少有一个TEXCOORD.xy
        mesh.calc_tangents()
        
        self.mesh = mesh
        self.total_structured_dtype:numpy.dtype = self.d3d11_game_type.get_total_structured_dtype()
        self.original_elementname_data_dict = ObjBufferHelper.parse_elementname_data_dict(mesh=mesh, d3d11_game_type=self.d3d11_game_type)

