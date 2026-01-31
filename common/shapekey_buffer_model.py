import collections
import numpy
import bpy

from dataclasses import dataclass, field, InitVar
from typing import Dict

from ..base.d3d11_gametype import D3D11GameType
from ..helper.obj_buffer_helper import ObjBufferHelper

@dataclass
class ShapeKeyBufferModel:
    '''
    逻辑和ObjElementModel以及ObjBufferModelUnity类似
    不过呢，只处理得到Position分类的数据
    每个ObjElementModel都有一个形态键名称为key，ShapeKeyBufferModel为value的字典
    里面装着每个形态键对应的应用值到1的Position数据
    最终这些数据会在ObjBufferModelUnity中被合并到每个DrawIB最终的ShapeKey数据中
    然后变成对应的Buffer文件

    TODO
    除此之外需要注意，必须确保ShapeKey应用后，重复的顶点也被看做是独立的顶点以避免合并导致的顶点顺序错误的问题。

    '''

    name: str # 形态键名称
    base_element_vertex_ndarray: numpy.ndarray = field(repr=False) 
    indices_map: numpy.ndarray = field(repr=False) 
    d3d11_game_type:D3D11GameType = field(repr=False)
    mesh: InitVar[bpy.types.Mesh] = None

    element_vertex_ndarray: numpy.ndarray = field(init=False, repr=False) # 存储了该形态键形态下的顶点数据

    def __post_init__(self, mesh: bpy.types.Mesh) -> None:
        # 1. 复制基础数据
        self.element_vertex_ndarray = self.base_element_vertex_ndarray.copy()

        if not mesh:
            return

        # 2. 提取并映射 Position 分类下的所有数据
        # 我们假设 self.indices_map 传入的是 Buffer 中每个点对应的 Loop Index
        loop_indices = self.indices_map
        
        # 缓存：Vertex Indices (从 Loop Index 转换而来)
        loop_vertex_indices = None 

        target_category = "Position"
        for d3d11_element in self.d3d11_game_type.D3D11ElementList:
            if d3d11_element.Category != target_category:
                continue
            
            elem_name = d3d11_element.ElementName
            data = None
            
            if elem_name == 'POSITION':
                if loop_vertex_indices is None:
                    # 懒计算 Vertex Index 映射
                    all_loop_vertex_indices = numpy.empty(len(mesh.loops), dtype=int)
                    mesh.loops.foreach_get("vertex_index", all_loop_vertex_indices)
                    loop_vertex_indices = all_loop_vertex_indices[loop_indices]
                
                data = ObjBufferHelper._parse_position(
                    mesh_vertices=mesh.vertices,
                    mesh_vertices_length=len(mesh.vertices),
                    loop_vertex_indices=loop_vertex_indices,
                    d3d11_element=d3d11_element
                )
            
            elif elem_name == 'NORMAL':
                all_normals = ObjBufferHelper._parse_normal(
                    mesh_loops=mesh.loops,
                    mesh_loops_length=len(mesh.loops),
                    d3d11_element=d3d11_element
                )
                data = all_normals[loop_indices]
            
            elif elem_name == 'TANGENT':
                all_tangents = ObjBufferHelper._parse_tangent(
                    mesh_loops=mesh.loops,
                    mesh_loops_length=len(mesh.loops),
                    d3d11_element=d3d11_element
                )
                data = all_tangents[loop_indices]
            
            elif elem_name.startswith('BINORMAL'):
                all_binormals = ObjBufferHelper._parse_binormal(
                    mesh_loops=mesh.loops,
                    mesh_loops_length=len(mesh.loops),
                    d3d11_element=d3d11_element
                )
                data = all_binormals[loop_indices]

            if data is not None:
                self.element_vertex_ndarray[elem_name] = data
    

    