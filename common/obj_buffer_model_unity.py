import collections
import numpy
import bpy

from dataclasses import dataclass, field

from ..utils.timer_utils import TimerUtils
from ..utils.shapekey_utils import ShapeKeyUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from .obj_element_model import ObjElementModel

from ..helper.obj_buffer_helper import ObjBufferHelper
from ..utils.obj_utils import ObjUtils
from .shapekey_buffer_model import ShapeKeyBufferModel

from ..blueprint.blueprint_export_helper import BlueprintExportHelper

@dataclass
class ObjBufferModelUnity:
    obj:bpy.types.Object
    d3d11_game_type:D3D11GameType

    obj_name:str = field(init=False, repr=False)
    dtype:numpy.dtype = field(init=False, repr=False)
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    # 这三个是最终要得到的输出内容
    ib:list = field(init=False,repr=False)
    category_buffer_dict:dict = field(init=False,repr=False)
    index_loop_id_dict:dict = field(init=False,repr=False) # 仅用于WWMI的索引 Loop ID字典，key是 Buffer 索引，value是 Loop ID，默认可以为None
    
    def __post_init__(self) -> None:
        ObjBufferHelper.check_and_verify_attributes(obj=self.obj, d3d11_game_type=self.d3d11_game_type)
        obj_element_model = ObjElementModel(d3d11_game_type=self.d3d11_game_type,obj_name=self.obj.name)

        obj_element_model.element_vertex_ndarray = ObjBufferHelper.convert_to_element_vertex_ndarray(
            original_elementname_data_dict=obj_element_model.original_elementname_data_dict,
            final_elementname_data_dict={},
            mesh=obj_element_model.mesh,
            d3d11_game_type=self.d3d11_game_type
        )

        mesh = obj_element_model.mesh
        # self.obj_name = obj_element_model.obj_name
        self.dtype = obj_element_model.total_structured_dtype
        dtype = self.dtype
        self.element_vertex_ndarray = obj_element_model.element_vertex_ndarray

        # 因为只有存在TANGENT时，顶点数才会增加，所以如果是GF2并且存在TANGENT才使用共享TANGENT防止增加顶点数
        if GlobalConfig.logic_name == LogicName.UnityCPU and "TANGENT" in self.d3d11_game_type.OrderedFullElementList:
            self.ib, self.category_buffer_dict, self.index_loop_id_dict = ObjBufferHelper.calc_index_vertex_buffer_girlsfrontline2(mesh=mesh, element_vertex_ndarray=self.element_vertex_ndarray, d3d11_game_type=self.d3d11_game_type, dtype=dtype)
        else:
            # 计算IndexBuffer和CategoryBufferDict
            self.ib, self.category_buffer_dict, self.index_loop_id_dict = ObjBufferHelper.calc_index_vertex_buffer_unified(mesh=mesh, element_vertex_ndarray=self.element_vertex_ndarray, d3d11_game_type=self.d3d11_game_type, dtype=dtype,obj=self.obj)

        # 此时根据前面的计算，我们得到了 index_loop_id_dict
        # 它记录了每个索引对应的Blender Loop ID，方便后续ShapeKey数据的提取 (支持 Split Normals/Tangents)

        self.shape_key_buffer_dict = {}

        # 开关判断：是否生成 ShapeKey Slider Buffer
        is_generate_shapekey = False

        shapekeyname_mkey_dict = BlueprintExportHelper.get_current_shapekeyname_mkey_dict()
        if len(shapekeyname_mkey_dict.keys()) > 0:
            is_generate_shapekey = True
        
        if is_generate_shapekey and self.obj.data.shape_keys and self.obj.data.shape_keys.key_blocks:
            # 获取所有以 Shape. 开头的形态键
            shape_keys = [sk for sk in self.obj.data.shape_keys.key_blocks if sk.name.startswith("Shape.")]
            
            if shape_keys:
                TimerUtils.Start(f"Processing {len(shape_keys)} ShapeKeys for {self.obj.name}")
                
                # Pre-calculate indices_map explicitly once
                # 修复: target_count 必须对应导出后的唯一顶点数
                if self.index_loop_id_dict is not None:
                     target_count = len(self.index_loop_id_dict)
                     indices_map = numpy.zeros(target_count, dtype=int)
                     # value 存储的是 Blender Loop Index
                     indices_map[:] = list(self.index_loop_id_dict.values())
                else:
                     # 少前2模式 (GF2 Mode): 强制 1:1 对应 Blender Vertices
                     # 因此目标数量等于 Blender 顶点数量
                     target_count = len(self.obj.data.vertices)
                     indices_map = numpy.arange(target_count, dtype=int)

                # 创建一个正确大小的空 ndarray 作为 ShapeKey 的基础模板
                # 这避免了使用 self.element_vertex_ndarray (Loops) 导致的形状不匹配错误
                base_shape_vertex_ndarray = numpy.zeros(target_count, dtype=self.dtype)

                for sk in shape_keys:
                    sk_name = sk.name
                    
                    # 1. 重置所有形态键并激活当前形态键
                    ShapeKeyUtils.reset_shapekey_values(self.obj)
                    sk.value = 1.0
                    
                    # 2. 获取应用了形态键后的 Mesh 数据
                    # 注意：get_mesh_evaluate_from_obj 生成了一个新的 Mesh 数据块，使用完需要移除
                    mesh_eval = ObjUtils.get_mesh_evaluate_from_obj(obj=self.obj)
                    
                    # 3. 必须进行三角化，确保几何结构一致
                    ObjUtils.mesh_triangulate(mesh_eval)

                    # 计算TANGENT，不然导出丢失部分TANGENT数据导致光影效果错误
                    mesh_eval.calc_tangents()
                    
                    # 4. 构建 ShapeKeyBufferModel (它会自动在 __post_init__ 中计算数据)
                    sb_model = ShapeKeyBufferModel(
                        name=sk_name,
                        base_element_vertex_ndarray=base_shape_vertex_ndarray,
                        mesh=mesh_eval,
                        indices_map=indices_map,
                        d3d11_game_type=self.d3d11_game_type
                    )
                    self.shape_key_buffer_dict[sk_name] = sb_model
                    
  

                # 循环结束后重置状态
                ShapeKeyUtils.reset_shapekey_values(self.obj)
                TimerUtils.End(f"Processing {len(shape_keys)} ShapeKeys for {self.obj.name}")

        