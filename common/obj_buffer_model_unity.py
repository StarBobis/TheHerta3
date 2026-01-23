import collections
import numpy
import bpy

from dataclasses import dataclass, field

from ..utils.timer_utils import TimerUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel
from ..config.properties_generate_mod import Properties_GenerateMod

from ..base.d3d11_gametype import D3D11GameType
from .obj_element_model import ObjElementModel

@dataclass
class ObjBufferModelUnity:
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
    
    def __post_init__(self) -> None:
        self.obj = self.obj_element_model.obj
        self.mesh = self.obj_element_model.mesh
        self.d3d11_game_type = self.obj_element_model.d3d11_game_type
        self.obj_name = self.obj_element_model.obj_name
        self.dtype = self.obj_element_model.total_structured_dtype
        self.element_vertex_ndarray = self.obj_element_model.element_vertex_ndarray

        # 因为只有存在TANGENT时，顶点数才会增加，所以如果是GF2并且存在TANGENT才使用共享TANGENT防止增加顶点数
        if GlobalConfig.logic_name == LogicName.UnityCPU and "TANGENT" in self.obj_element_model.d3d11_game_type.OrderedFullElementList:
            self.calc_index_vertex_buffer_girlsfrontline2()
        else:
            # 计算IndexBuffer和CategoryBufferDict
            # self.calc_index_vertex_buffer_universal()
            self.calc_index_vertex_buffer_unified()

    def calc_index_vertex_buffer_unified(self):
        '''
        计算IndexBuffer和CategoryBufferDict并返回
        如果模型具有形态键，那么形态键盘的值为0到1的任何值应用后，都不会造成由于顶点合并导致的顶点数改变。
        '''
        # TimerUtils.Start("Calc IB VB")
        
        has_shape_keys = False
        if self.mesh.shape_keys and len(self.mesh.shape_keys.key_blocks) > 0:
             has_shape_keys = True

        if has_shape_keys:
            # 如果有形态键，必须区分不同顶点索引的顶点，即使它们的数据相同
            # 这样可以防止合并那些在Basis中重合但在ShapeKey中分离的顶点
            unique_map = collections.OrderedDict()
            ib = []
            for poly in self.mesh.polygons:
                poly_indices = []
                for loop_index in range(poly.loop_start, poly.loop_start + poly.loop_total):
                    loop = self.mesh.loops[loop_index]
                    data = self.element_vertex_ndarray[loop.index].tobytes()
                    # Key includes vertex_index to prevent merging different vertices
                    key = (data, loop.vertex_index)
                    idx = unique_map.setdefault(key, len(unique_map))
                    poly_indices.append(idx)
                ib.append(poly_indices)
            
            # Extract just the data bytes for the vertex buffer
            vertex_data_list = [k[0] for k in unique_map.keys()]
            
        else:
            # Standard merging based on data only
            indexed_vertices = collections.OrderedDict()
            ib = [[indexed_vertices.setdefault(self.element_vertex_ndarray[blender_lvertex.index].tobytes(), len(indexed_vertices))
                    for blender_lvertex in self.mesh.loops[poly.loop_start:poly.loop_start + poly.loop_total]
                        ]for poly in self.mesh.polygons] 
            vertex_data_list = indexed_vertices # keys are the data bytes

        flattened_ib = [item for sublist in ib for item in sublist]
        # TimerUtils.End("Calc IB VB")

        # 重计算TANGENT步骤
        indexed_vertices = self.average_normal_tangent(obj=self.obj, indexed_vertices=vertex_data_list, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)
        
        # 重计算COLOR步骤
        indexed_vertices = self.average_normal_color(obj=self.obj, indexed_vertices=indexed_vertices, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer")
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in self.d3d11_game_type.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride

        self.ib = flattened_ib


        # TODO YYSLS是目前除了鸣潮外，唯一需要翻转面朝向的游戏
        # 但是也许后续非镜像工作流统一后可以解决这个问题？
        if GlobalConfig.logic_name == LogicName.YYSLS:
            print("导出时翻转面朝向")

            flipped_indices = []
            # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
            for i in range(0, len(flattened_ib), 3):
                triangle = flattened_ib[i:i+3]
                flipped_triangle = triangle[::-1]
                flipped_indices.extend(flipped_triangle)
            # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])
            self.ib = flipped_indices

        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = None
        
    def calc_index_vertex_buffer_girlsfrontline2(self):
        '''
        1. Blender 的“顶点数”= mesh.vertices 长度，只要位置不同就算一个。
        2. 我们预分配同样长度的盒子列表，盒子下标 == 顶点下标，保证一一对应。
        3. 遍历 loop 时，把真实数据写进对应盒子；没人引用的盒子留 dummy（坐标填对，其余 0）。
        4. 最后按盒子顺序打包成字节数组，长度必然与 mesh.vertices 相同，导出数就能和 Blender 状态栏完全一致。
        '''
        print("calc ivb gf2")

        loops = self.mesh.loops
        v_cnt = len(self.mesh.vertices)
        loop_vidx = numpy.empty(len(loops), dtype=int)
        loops.foreach_get("vertex_index", loop_vidx)

        # 1. 预分配：每条 Blender 顶点一条记录，先填“空”
        dummy = numpy.zeros(1, dtype=self.element_vertex_ndarray.dtype)
        vertex_buffer = [dummy.copy() for _ in range(v_cnt)]   # list[ndarray]
        # 2. 标记哪些顶点被 loop 真正用到
        used_mask = numpy.zeros(v_cnt, dtype=bool)
        used_mask[loop_vidx] = True

        # 3. 共享 TANGENT 字典
        pos_normal_key = {}   # (position_tuple, normal_tuple) -> tangent

        # 4. 先给“被用到”的顶点填真实数据
        for lp in loops:
            v_idx = lp.vertex_index
            if used_mask[v_idx]:          # 其实恒为 True，留着可读性
                data = self.element_vertex_ndarray[lp.index].copy()
                pn_key = (tuple(data['POSITION']), tuple(data['NORMAL']))
                if pn_key in pos_normal_key:
                    data['TANGENT'] = pos_normal_key[pn_key]
                else:
                    pos_normal_key[pn_key] = data['TANGENT']
                vertex_buffer[v_idx] = data

        # 5. 给“死顶点”也填上 dummy，但位置必须对
        for v_idx in range(v_cnt):
            if not used_mask[v_idx]:
                vertex_buffer[v_idx]['POSITION'] = self.mesh.vertices[v_idx].co
                # 其余字段保持 0

        # 6. 现在 vertex_buffer 长度 == v_cnt，直接转 bytes 即可
        indexed_vertices = [arr.tobytes() for arr in vertex_buffer]

        # 7. 重建索引缓冲（IB）
        ib = []
        for poly in self.mesh.polygons:
            ib.append([v_idx for lp in loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    for v_idx in [lp.vertex_index]])

        flattened_ib = [i for sub in ib for i in sub]

        # 8. 拆 CategoryBuffer
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict = {name: [] for name in self.d3d11_game_type.CategoryStrideDict}
        data_matrix = numpy.array([numpy.frombuffer(b, dtype=numpy.uint8) for b in indexed_vertices])
        stride_offset = 0
        for name, stride in category_stride_dict.items():
            category_buffer_dict[name] = data_matrix[:, stride_offset:stride_offset + stride].flatten()
            stride_offset += stride

        print("长度：", v_cnt)          # 这里一定是 21668
        self.ib = flattened_ib
        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = None
 
    def calc_index_vertex_buffer_universal(self):
        '''
        计算IndexBuffer和CategoryBufferDict并返回

        这里是速度瓶颈，23万顶点情况下测试，前面的获取mesh数据只用了1.5秒
        但是这里两个步骤加起来用了6秒，占了4/5运行时间。
        不过暂时也够用了，先不管了。
        '''
        # TimerUtils.Start("Calc IB VB")
        # (1) 统计模型的索引和唯一顶点
        '''
        不保持相同顶点时，仍然使用经典而又快速的方法
        '''
        # print("calc ivb universal")
        indexed_vertices = collections.OrderedDict()
        ib = [[indexed_vertices.setdefault(self.element_vertex_ndarray[blender_lvertex.index].tobytes(), len(indexed_vertices))
                for blender_lvertex in self.mesh.loops[poly.loop_start:poly.loop_start + poly.loop_total]
                    ]for poly in self.mesh.polygons] 
            
        flattened_ib = [item for sublist in ib for item in sublist]
        # TimerUtils.End("Calc IB VB")

        # 重计算TANGENT步骤
        indexed_vertices = self.average_normal_tangent(obj=self.obj, indexed_vertices=indexed_vertices, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)
        
        # 重计算COLOR步骤
        indexed_vertices = self.average_normal_color(obj=self.obj, indexed_vertices=indexed_vertices, d3d11GameType=self.d3d11_game_type,dtype=self.dtype)

        # print("indexed_vertices:")
        # print(str(len(indexed_vertices)))

        # (2) 转换为CategoryBufferDict
        # TimerUtils.Start("Calc CategoryBuffer")
        category_stride_dict = self.d3d11_game_type.get_real_category_stride_dict()
        category_buffer_dict:dict[str,list] = {}
        for categoryname,category_stride in self.d3d11_game_type.CategoryStrideDict.items():
            category_buffer_dict[categoryname] = []

        data_matrix = numpy.array([numpy.frombuffer(byte_data,dtype=numpy.uint8) for byte_data in indexed_vertices])
        stride_offset = 0
        for categoryname,category_stride in category_stride_dict.items():
            category_buffer_dict[categoryname] = data_matrix[:,stride_offset:stride_offset + category_stride].flatten()
            stride_offset += category_stride


        

        self.ib = flattened_ib

        flip_face_direction = False

        if Properties_ImportModel.use_mirror_workflow():
            flip_face_direction = True
            if GlobalConfig.logic_name == LogicName.YYSLS:
                flip_face_direction = False
        else:
            if GlobalConfig.logic_name == LogicName.YYSLS:
                flip_face_direction = True

        if flip_face_direction:
            print("导出时翻转面朝向")

            flipped_indices = []
            # print(flattened_ib[0],flattened_ib[1],flattened_ib[2])
            for i in range(0, len(flattened_ib), 3):
                triangle = flattened_ib[i:i+3]
                flipped_triangle = triangle[::-1]
                flipped_indices.extend(flipped_triangle)
            # print(flipped_indices[0],flipped_indices[1],flipped_indices[2])
            self.ib = flipped_indices



        self.category_buffer_dict = category_buffer_dict
        self.index_vertex_id_dict = None




    def average_normal_tangent(self,obj,indexed_vertices,d3d11GameType,dtype):
        '''
        Nico: 米游所有游戏都能用到这个，还有曾经的GPU-PreSkinning的GF2也会用到这个，崩坏三2.0新角色除外。
        尽管这个可以起到相似的效果，但是仍然无法完美获取模型本身的TANGENT数据，只能做到身体轮廓线99%近似。
        经过测试，头发轮廓线部分并不是简单的向量归一化，也不是算术平均归一化。
        '''
        # TimerUtils.Start("Recalculate TANGENT")

        if "TANGENT" not in d3d11GameType.OrderedFullElementList:
            return indexed_vertices
        allow_calc = False
        if Properties_GenerateMod.recalculate_tangent():
            allow_calc = True
        elif obj.get("3DMigoto:RecalculateTANGENT",False): 
            allow_calc = True
        
        if not allow_calc:
            return indexed_vertices
        
        # 不用担心这个转换的效率，速度非常快
        vb = bytearray()
        for vertex in indexed_vertices:
            vb += bytes(vertex)
        vb = numpy.frombuffer(vb, dtype = dtype)

        # 开始重计算TANGENT
        positions = numpy.array([val['POSITION'] for val in vb])
        normals = numpy.array([val['NORMAL'] for val in vb], dtype=float)

        # 对位置进行排序，以便相同的位置会相邻
        sort_indices = numpy.lexsort(positions.T)
        sorted_positions = positions[sort_indices]
        sorted_normals = normals[sort_indices]

        # 找出位置变化的地方，即我们需要分组的地方
        group_indices = numpy.flatnonzero(numpy.any(sorted_positions[:-1] != sorted_positions[1:], axis=1))
        group_indices = numpy.r_[0, group_indices + 1, len(sorted_positions)]

        # 累加法线和计算计数
        unique_positions = sorted_positions[group_indices[:-1]]
        accumulated_normals = numpy.add.reduceat(sorted_normals, group_indices[:-1], axis=0)
        counts = numpy.diff(group_indices)

        # 归一化累积法线向量
        normalized_normals = accumulated_normals / numpy.linalg.norm(accumulated_normals, axis=1)[:, numpy.newaxis]
        normalized_normals[numpy.isnan(normalized_normals)] = 0  # 处理任何可能出现的零向量导致的除零错误

        # 构建结果字典
        position_normal_dict = dict(zip(map(tuple, unique_positions), normalized_normals))

        # TimerUtils.End("Recalculate TANGENT")

        # 获取所有位置并转换为元组，用于查找字典
        positions = [tuple(pos) for pos in vb['POSITION']]

        # 从字典中获取对应的标准化法线
        normalized_normals = numpy.array([position_normal_dict[pos] for pos in positions])

        # 计算 w 并调整 tangent 的第四个分量
        w = numpy.where(vb['TANGENT'][:, 3] >= 0, -1.0, 1.0)

        # 更新 TANGENT 分量，注意这里的切片操作假设 TANGENT 有四个分量
        vb['TANGENT'][:, :3] = normalized_normals
        vb['TANGENT'][:, 3] = w

        # TimerUtils.End("Recalculate TANGENT")

        return vb


    def average_normal_color(self,obj,indexed_vertices,d3d11GameType,dtype):
        '''
        Nico: 算数平均归一化法线，HI3 2.0角色使用的方法
        '''
        if "COLOR" not in d3d11GameType.OrderedFullElementList:
            return indexed_vertices
        allow_calc = False
        if Properties_GenerateMod.recalculate_color():
            allow_calc = True
        elif obj.get("3DMigoto:RecalculateCOLOR",False): 
            allow_calc = True
        if not allow_calc:
            return indexed_vertices

        # 开始重计算COLOR
        TimerUtils.Start("Recalculate COLOR")

        # 不用担心这个转换的效率，速度非常快
        vb = bytearray()
        for vertex in indexed_vertices:
            vb += bytes(vertex)
        vb = numpy.frombuffer(vb, dtype = dtype)

        # 首先提取所有唯一的位置，并创建一个索引映射
        unique_positions, position_indices = numpy.unique(
            [tuple(val['POSITION']) for val in vb], 
            return_inverse=True, 
            axis=0
        )

        # 初始化累积法线和计数器为零
        accumulated_normals = numpy.zeros((len(unique_positions), 3), dtype=float)
        counts = numpy.zeros(len(unique_positions), dtype=int)

        # 累加法线并增加计数（这里假设vb是一个list）
        for i, val in enumerate(vb):
            accumulated_normals[position_indices[i]] += numpy.array(val['NORMAL'], dtype=float)
            counts[position_indices[i]] += 1

        # 对所有位置的法线进行一次性规范化处理
        mask = counts > 0
        average_normals = numpy.zeros_like(accumulated_normals)
        average_normals[mask] = (accumulated_normals[mask] / counts[mask][:, None])

        # 归一化到[0,1]，然后映射到颜色值
        normalized_normals = ((average_normals + 1) / 2 * 255).astype(numpy.uint8)

        # 更新颜色信息
        new_color = []
        for i, val in enumerate(vb):
            color = [0, 0, 0, val['COLOR'][3]]  # 保留原来的Alpha通道
            
            if mask[position_indices[i]]:
                color[:3] = normalized_normals[position_indices[i]]

            new_color.append(color)

        # 将新的颜色列表转换为NumPy数组
        new_color_array = numpy.array(new_color, dtype=numpy.uint8)

        # 更新vb中的颜色信息
        for i, val in enumerate(vb):
            val['COLOR'] = new_color_array[i]

        TimerUtils.End("Recalculate COLOR")
        return vb