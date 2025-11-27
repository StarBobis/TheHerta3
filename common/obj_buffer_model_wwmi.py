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
from .obj_element_model import ObjElementModel
from ..utils.shapekey_utils import ShapeKeyUtils

@dataclass
class ObjBufferModelWWMI:
    '''
    这个类应该是导出前的最后一步，负责把所有的mesh属性以及d3d11Element属性
    转换成最终要输出的格式
    然后交给ObjWriter去写入文件
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

    export_shapekey:bool =  field(init=False,repr=False,default=False)

    def __post_init__(self) -> None:
        self.obj = self.obj_element_model.obj
        self.mesh = self.obj_element_model.mesh
        self.d3d11_game_type = self.obj_element_model.d3d11_game_type
        self.obj_name = self.obj_element_model.obj_name
        self.dtype = self.obj_element_model.total_structured_dtype
        self.element_vertex_ndarray = self.obj_element_model.element_vertex_ndarray

        # 计算IB和分类缓冲区以及索引映射表
        self.calc_index_vertex_buffer_wwmi_v2()
        
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


    def calc_index_vertex_buffer_wwmi_v2(self):
        '''
        优点：
        - 用 numpy 将结构化顶点视图为一行字节，避免逐顶点 bytes() 与 dict 哈希。
        - 使用 numpy.unique(..., axis=0, return_index=True, return_inverse=True) 在 C 层完成唯一化与逆映射。
        - 仅在构建 per-polygon IB 时使用少量 Python 切片，整体效率大幅提高。

        注意：
        - 当 structured dtype 非连续时，内部会做一次拷贝（ascontiguousarray）；通常开销小于逐顶点哈希开销。
        - 若模型非常大且内存受限，可改为分块实现（我可以后续提供）。
        '''
        import numpy as np

        # (1) loop -> vertex mapping
        loops = self.mesh.loops
        n_loops = len(loops)
        loop_vertex_indices = np.empty(n_loops, dtype=int)
        loops.foreach_get("vertex_index", loop_vertex_indices)

        # (2) 将 element_vertex_ndarray 保证为连续，并视为 (n_loops, row_bytes) uint8 矩阵
        vb = np.ascontiguousarray(self.element_vertex_ndarray)
        row_size = vb.dtype.itemsize
        try:
            row_bytes = vb.view(np.uint8).reshape(n_loops, row_size)
        except Exception:
            raw = vb.tobytes()
            row_bytes = np.frombuffer(raw, dtype=np.uint8).reshape(n_loops, row_size)

        # WWMI-Tools deduplicates loop rows including the loop's VertexId -> they
        # effectively perform uniqueness on loop attributes + VertexId treated as
        # a field. To replicate that reliably (preserving structured field layout
        # and alignment) we build a structured array that copies all existing
        # fields and appends a 'VERTEXID' uint32 field, then call np.unique on it.
        # Afterwards we select unique rows from the original `row_bytes` using
        # the indices returned by np.unique to preserve exact original layout.

        # Build 4-byte vertex index array (little-endian) and concatenate to row bytes
        # to form combined rows: [row_bytes | vid_bytes]. Use np.unique on combined
        # rows to get uniqueness, then reorder unique results to match insertion
        # order (first occurrence). This vectorized path keeps behavior identical
        # to the OrderedDict+bytes approach but runs much faster in numpy.
        # Build 4-byte vertex index array (little-endian)
        vid_bytes = loop_vertex_indices.astype(numpy.uint32).view(numpy.uint8).reshape(n_loops, 4)

        # Combine row bytes + vid bytes, but to make np.unique faster we pad the
        # combined row to a multiple of 8 bytes and view it as uint64 blocks.
        total_bytes = row_size + 4
        pad = (-total_bytes) % 8
        padded_width = total_bytes + pad

        # Allocate padded combined buffer and fill
        combined_padded = np.zeros((n_loops, padded_width), dtype=np.uint8)
        combined_padded[:, :row_size] = row_bytes
        combined_padded[:, row_size:row_size+4] = vid_bytes

        # View as uint64 blocks (shape: n_loops x n_blocks)
        n_blocks = padded_width // 8
        combined_u64 = combined_padded.view(np.uint64).reshape(n_loops, n_blocks)

        # Create a structured view so np.unique treats each row as a single record
        dtype_descr = [(f'f{i}', np.uint64) for i in range(n_blocks)]
        structured = combined_u64.view(numpy.dtype(dtype_descr)).reshape(n_loops)

        unique_struct, unique_first_indices, inverse = numpy.unique(
            structured, return_index=True, return_inverse=True
        )

        # Remap unique ids to insertion order (first occurrence order)
        order = numpy.argsort(unique_first_indices)
        new_id = numpy.empty_like(order)
        new_id[order] = numpy.arange(len(order), dtype=new_id.dtype)
        inverse = new_id[inverse]

        unique_first_indices_insertion = unique_first_indices[order]

        # Pick original unique rows from row_bytes using insertion-ordered indices
        unique_rows = row_bytes[unique_first_indices_insertion]

        # Expose the loop indices (first-occurrence loop indices) used to select
        # the unique rows. Callers can sample per-loop original arrays using
        # these indices to reconstruct per-unique-row original element values.
        self.unique_first_loop_indices = unique_first_indices_insertion

        # Reconstruct a structured ndarray of the unique element rows.
        # This lets callers access element fields by name for the unique
        # vertex set (useful for debugging or further processing).
        # Ensure the byte width matches the dtype itemsize.
        if unique_rows.shape[1] != self.dtype.itemsize:
            raise Fatal(f"Unique row byte-size ({unique_rows.shape[1]}) does not match structured dtype itemsize ({self.dtype.itemsize})")

        n_unique = unique_rows.shape[0]
        unique_rows_contig = numpy.ascontiguousarray(unique_rows)
        try:
            # Zero-copy view where possible
            unique_element_vertex_ndarray = unique_rows_contig.view(self.dtype).reshape(n_unique)
        except Exception:
            # Fallback to a safe copy-based reconstruction
            unique_element_vertex_ndarray = numpy.frombuffer(unique_rows_contig.tobytes(), dtype=self.dtype).reshape(n_unique)

        # Expose for downstream use: structure-aligned unique vertex records
        self.unique_element_vertex_ndarray = unique_element_vertex_ndarray

        # 构建 index -> original vertex id（使用每个 unique 行的第一个 loop 对应的 vertex）
        original_vertex_ids = loop_vertex_indices[unique_first_indices_insertion]
        index_vertex_id_dict = dict(enumerate(original_vertex_ids.astype(int).tolist()))

        # (4) 为每个 polygon 构建 IB（使用 inverse 映射）
        # inverse is already ordered by loops; concatenating polygon slices in
        # polygon order is equivalent to taking inverse in sequence.
        flattened_ib_arr = inverse.astype(numpy.int32)

        # (5) 按 category 从 unique_rows 切分 bytes 序列
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {}
        stride_offset = 0
        for cname, cstride in category_stride_dict.items():
            category_buffer_dict[cname] = unique_rows[:, stride_offset:stride_offset + cstride].flatten()
            stride_offset += cstride

        # (6) 翻转三角形方向（高效）
        flat_arr = flattened_ib_arr
        if flat_arr.size % 3 == 0:
            flipped = flat_arr.reshape(-1, 3)[:, ::-1].flatten().tolist()
        else:
            # Rare irregular case: fallback to python loop on numpy array
            flipped = []
            iarr = flat_arr.tolist()
            for i in range(0, len(iarr), 3):
                tri = iarr[i:i + 3]
                flipped.extend(tri[::-1])

        # (7) 写回到 self（与原函数一致的字段）
        self.ib = flipped
        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = index_vertex_id_dict

