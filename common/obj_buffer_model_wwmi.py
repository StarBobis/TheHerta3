import numpy
import bpy

from dataclasses import dataclass, field


from ..base.d3d11_gametype import D3D11GameType
from .obj_element_model import ObjElementModel
from ..utils.shapekey_utils import ShapeKeyUtils

from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ObjBufferModelWWMI:
    '''
    这个类应该是导出前的最后一步，负责把所有的mesh属性以及d3d11Element属性
    转换成最终要输出的格式
    然后交给ObjWriter去写入文件


    TODO 目前测试发现一个非常严重的问题
    那就是咱们TheHerta3的架构设计是完全错误的，对于Blender插件开发，最好的方法其实是函数式编程
    因为基于类的编程会导致模式被固定死，难以修改
    尤其是需要频繁添加新功能的时候

    函数式编程虽然让新人上手比较困难，但是却是灵活性最高的选择，所以必须完成整体的函数式编程重构
    （反正也很难有人参与开发）
    这是个大工程，但是它是基础前置，如果不这样做，后面要添加的动画Mod支持，形态键Mod支持，基于帧的buf导出支持等等
    就很难在现有的基于类的模式下进行开发和测试
    因为目前的模式牵一发而动全身，必须要改动很多地方才能实现一个小功能
    所以必须重构为函数式编程，彻底解放代码逻辑

    '''

    obj_element_model:ObjElementModel
    
    # 这些是直接从obj_element_model中获取的
    obj:bpy.types.Object = field(init=False,repr=False)
    mesh:bpy.types.Mesh = field(init=False,repr=False)
    d3d11_game_type:D3D11GameType = field(init=False, repr=False)
    obj_name:str = field(init=False, repr=False)
    dtype:numpy.dtype = field(init=False, repr=False)
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    # 这三个是最终要得到的输出内容
    ib:list = field(init=False,repr=False)
    category_buffer_dict:dict = field(init=False,repr=False)
    index_vertex_id_dict:dict = field(init=False,repr=False) # 仅用于WWMI的索引顶点ID字典，key是顶点索引，value是顶点ID，默认可以为None
    
    shapekey_offsets:list = field(init=False,repr=False,default_factory=list)
    shapekey_vertex_ids:list = field(init=False,repr=False,default_factory=list)
    shapekey_vertex_offsets:list = field(init=False,repr=False,default_factory=list)

    export_shapekey:bool = field(init=False,repr=False,default=False)

    def __post_init__(self) -> None:
        self.obj = self.obj_element_model.obj
        self.mesh = self.obj_element_model.mesh
        self.d3d11_game_type = self.obj_element_model.d3d11_game_type
        self.obj_name = self.obj_element_model.obj_name
        self.dtype = self.obj_element_model.total_structured_dtype
        self.element_vertex_ndarray = self.obj_element_model.element_vertex_ndarray

        # 计算IB和分类缓冲区以及索引映射表
        self.ib,self.category_buffer_dict,self.index_vertex_id_dict,self.unique_element_vertex_ndarray,self.unique_first_loop_indices = ObjBufferHelper.calc_index_vertex_buffer_wwmi_v2(
            mesh=self.mesh,
            element_vertex_ndarray=self.element_vertex_ndarray,
            dtype=self.dtype,
            d3d11_game_type=self.d3d11_game_type
        )
        
        # 获取ShapeKey数据
        if self.obj.data.shape_keys is None or len(getattr(self.obj.data.shape_keys, 'key_blocks', [])) == 0:
            print(f'No shapekeys found to process!')
            self.export_shapekey = False
        else:
            shapekey_offsets,shapekey_vertex_ids,shapekey_vertex_offsets_np = ShapeKeyUtils.extract_shapekey_data(merged_obj=self.obj,index_vertex_id_dict=self.index_vertex_id_dict)
            
            self.shapekey_offsets = shapekey_offsets
            self.shapekey_vertex_ids = shapekey_vertex_ids
            self.shapekey_vertex_offsets = shapekey_vertex_offsets_np

            self.export_shapekey = True

