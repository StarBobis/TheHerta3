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

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from ..base.obj_data_model import ObjDataModel

from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ObjElementModel:
    '''
    TODO 要实现把形态键导出为.buf的话，就需要对现在的类进行改造
    把所有的方法变成函数式的，方便任意组合灵活调用
    因为如果是放在类的设计里，调用的模式就会被固定死
    
    因为后面不仅有形态键的Shape. 以及Anim.导出
    还有基于帧的每帧buf导出
    不管是哪个都要求我们能灵活地调用这些方法

    需要实现，给出一个复制过的只保留某个形态键状态的obj
    就能直接获取到它的POSITION.buf的数据
    目前的架构很难做到，强行做到也会导致额外调用许多无效代码，导致拖慢执行速度
    例如check_and_verify_attributes这个只需要在开始之前进行一次校验就行了

    例如后面的替换BLENDINDICES，以及求Buffer，都需要变成灵活应用的函数
    也就是需要下放到utils层级
    这里可以看出我们之前的层级设计是错的，因为这里只涉及到底层操作，所以应该全部在utils层完成

    由于obj_buffer_model是依赖于obj_element_model的
    这个类一改，整个逻辑和体系全部都要修改，我靠了。。。

    所以暂时不动这里的东西，新开一个utils类去测试

    又因为obj_element_model还起到了数据传递的作用
    所以这个类还不能删掉，还需要用这个类来传递数据
    只不过需要把里面的方法去掉，方法改为从外面调用新的utils类，然后最终生成一个obj_element_model实例？
    也不对，整个基于obj_element_model和obj_buffer_model的设计都要改
    也就是这俩类都必须变成纯数据类，核心逻辑全部独立出来变成utils调用
    并且要尽可能拆分的小一点。
    '''
    # 初始化时必须填的字段
    d3d11_game_type:D3D11GameType
    obj_name:str

    # 外用字段
    obj:bpy.types.Object = field(init=False,repr=False)
    mesh:bpy.types.Mesh = field(init=False,repr=False)
    total_structured_dtype:numpy.dtype = field(init=False, repr=False)

    # 数据先从obj中提取出来，按 ElementName 放到这个 Dict 中，作为原始未修改数据
    original_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)

    # 在外部对原始数据进行修改/remap 后，结果应写入 final_elementname_data_dict
    # 然后再由 fill_into_element_vertex_ndarray() 优先使用 final 的内容进行打包。
    final_elementname_data_dict: dict = field(init=False, repr=False, default_factory=dict)

    # 然后再把数据写入
    element_vertex_ndarray:numpy.ndarray = field(init=False,repr=False)

    def __post_init__(self) -> None:
        '''
        使用Numpy直接从指定名称的obj的mesh中转换数据到目标格式Buffer
        '''
        self.obj = ObjUtils.get_obj_by_name(name=self.obj_name)

        '''
        这里我想把形态键归0，然后获取模型当前不含形态键的原始网格数据
        但是问题在于，有些人是要通过形态键来调整体态数据的，然后他们希望导出那个特定形态键下的模型
        此时如果我们把所有的形态键全部设为0，那就会导致导出结果和预期不符
        所以这里只把部分形态键设为0，具体请看如下规则
        可以把形态键命名为Export.XXXX 也就是以Export.开头的形态键，这样的形态键会被保留
        这种形态键数值是多少，导出的模型就是多少
        其它的形态键则会被归0，归0的目的是防止它们影响最终的网格数据
        因为我们要把一部分形态键 Shape.XXXX 当成滑条调整体型的形态键
        后面还有另一部分Anim.XXXX 当成动画形态键，也就是通过形态键、变量切换来实现循环播放小动画功能
        其它不符合命名规则的形态键将会被归0并且忽略掉

        TODO 在开发这个功能之前，我们必须把所有的导出流程都改为
        创建一个临时的obj来进行导出，所有的操作只在这个临时的obj上进行
        但是这个也不是必要的，总之先随便试试，写完功能之后再来优化这个问题


        '''
        shape_key_values = {}
        if self.obj.data.shape_keys:
            # 必须遍历 key_blocks 才能获取每个键的值
            for key_block in self.obj.data.shape_keys.key_blocks:
                shape_key_values[key_block.name] = key_block.value
                # 只有不以 Export. 开头的形态键才会被归零
                if not key_block.name.startswith("Export."):
                    key_block.value = 0.0
        
        # 这里获取应用了形态键之后的mesh数据
        mesh = ObjUtils.get_mesh_evaluate_from_obj(obj=self.obj)

        # 三角化mesh，因为游戏引擎里的mesh都是三角形
        ObjUtils.mesh_triangulate(mesh)

        # Calculates tangents and makes loop normals valid (still with our custom normal data from import time):
        # 前提是有UVMap，前面的步骤应该保证了模型至少有一个TEXCOORD.xy
        mesh.calc_tangents()

        # Cache frequently accessed mesh collections/lengths to avoid repeated attribute lookups
        # 提前获取到变量，这样避免用到的时候重复获取，也许能节省开销？不确定，应该节省不了多少
        self.mesh = mesh
        self.mesh_loops = mesh.loops
        self.mesh_loops_length = len(self.mesh_loops)
        self.mesh_vertices = mesh.vertices
        self.mesh_vertices_length = len(self.mesh_vertices)
        self.vertex_colors = mesh.vertex_colors
        self.uv_layers = mesh.uv_layers
    
        # 读取并解析数据（填充到 `original_elementname_data_dict`）
        # NOTE: we only parse into `original_elementname_data_dict` here and defer
        # packing into the structured `element_vertex_ndarray` until an
        # external caller invokes `fill_into_element_vertex_ndarray()`.
        # This allows callers to modify `final_elementname_data_dict` (for
        # example, to apply per-component BLENDINDICES remaps) before the
        # structured dtype is allocated and packed, avoiding uint8
        # truncation issues.
        self.original_elementname_data_dict = ObjBufferHelper.parse_elementname_data_dict(mesh=mesh, d3d11_game_type=self.d3d11_game_type)


    def fill_into_element_vertex_ndarray(self):
        self.total_structured_dtype:numpy.dtype = self.d3d11_game_type.get_total_structured_dtype()

        # Create the element array with the original dtype (matching ByteWidth)
        self.element_vertex_ndarray = numpy.zeros(self.mesh_loops_length, dtype=self.total_structured_dtype)
        # For each expected element, prefer the remapped/modified value in
        # `final_elementname_data_dict` if present; otherwise use the parsed
        # value from `original_elementname_data_dict`.
        for d3d11_element_name in self.d3d11_game_type.OrderedFullElementList:
            if d3d11_element_name in self.final_elementname_data_dict:
                data = self.final_elementname_data_dict[d3d11_element_name]
            else:
                data = self.original_elementname_data_dict.get(d3d11_element_name, None)

            if data is None:
                # Missing data is a fatal condition — better to raise so caller
                # can diagnose than to silently write zeros for an expected
                # element (which would corrupt downstream buffers).
                raise Fatal(f"Missing element data for '{d3d11_element_name}' when packing vertex ndarray")
            print("尝试赋值 Element: " + d3d11_element_name)
            self.element_vertex_ndarray[d3d11_element_name] = data

    