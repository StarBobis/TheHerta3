import numpy
import struct
import copy
import os
import shutil

from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import *
from ..utils.json_utils import *
from ..utils.timer_utils import *

from ..base.obj_data_model import ObjDataModel
from ..base.component_model import ComponentModel
from ..base.d3d11_gametype import D3D11GameType
from ..base.m_draw_indexed import M_DrawIndexed

from ..config.main_config import *
from ..config.import_config import ImportConfig

from ..blueprint.blueprint_model import BluePrintModel

from ..helper.buffer_export_helper import BufferExportHelper

class DrawIBModel:
    '''
    这个代表了一个DrawIB的Mod导出模型
    Mod导出可以调用这个模型来进行业务逻辑部分
    每个游戏的DrawIBModel都是不同的，但是一部分是可以复用的
    (例如WWMI就有自己的一套DrawIBModel)
    '''


    # 通过default_factory让每个类的实例的变量分割开来，不再共享类的静态变量
    def __init__(self, draw_ib:str, branch_model:BluePrintModel):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict:dict[str,str] = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib:str = draw_ib
        self.draw_ib_alias:str = draw_ib_alias_name_dict.get(draw_ib,draw_ib)

        print(self.draw_ib + " Alias Name: " + self.draw_ib_alias)
        # (2) 读取工作空间中配置文件的配置项
        self.import_config:ImportConfig = ImportConfig(draw_ib=self.draw_ib)
        self.d3d11GameType:D3D11GameType = self.import_config.d3d11GameType

        '''
        这里是要得到每个Component对应的obj_data_model列表
        在这一步之前，需要对当前DrawIB的所有的obj_data_model填充ib和category_buf_dict属性
        '''
        self.draw_ib_ordered_obj_data_model_list:list[ObjDataModel] = branch_model.get_buffered_obj_data_model_list_by_draw_ib_and_game_type(draw_ib=draw_ib,d3d11_game_type=self.import_config.d3d11GameType)
        self._component_model_list:list[ComponentModel] = []
        self.component_name_component_model_dict:dict[str,ComponentModel] = {}
        for part_name in self.import_config.part_name_list:
            print("part_name: " + part_name)
            component_obj_data_model_list = []
            for obj_data_model in self.draw_ib_ordered_obj_data_model_list:
                if part_name == str(obj_data_model.component_count):
                    component_obj_data_model_list.append(obj_data_model)
                    # print(part_name + " 已赋值")

            component_model = ComponentModel(component_name="Component " +part_name, final_ordered_draw_obj_model_list=component_obj_data_model_list)
     
            self._component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = component_model
        
        LOG.newline()

        # (4) 根据之前解析集合架构的结果，读取obj对象内容到字典中
        self.componentname_ibbuf_dict:dict[str,list[int]] = {} # 每个Component都生成一个IndexBuffer文件，或者所有Component共用一个IB文件。
        self.__categoryname_bytelist_dict = {} # 每个Category都生成一个CategoryBuffer文件。
        self.draw_number:int = 0 # 每个DrawIB都有总的顶点数，对应CategoryBuffer里的顶点数。
        self.total_index_count:int = 0 # 每个DrawIB都有总的IndexCount数，也就是所有的Component中的所有顶点索引数量
        self.__obj_name_drawindexed_dict:dict[str,M_DrawIndexed] = {} 

        # 用于存储合并后的形态键数据
        self.shapekey_name_bytelist_dict:dict[str, numpy.ndarray] = {}

        self.__read_component_ib_buf_dict()
            
        self.parse_categoryname_bytelist_dict()

        # (5) 导出Buffer文件，Export Index Buffer files, Category Buffer files. (And Export ShapeKey Buffer Files.(WWMI))
        # 用于写出IB时使用
        self.PartName_IBResourceName_Dict = {}
        self.PartName_IBBufferFileName_Dict = {}
        self.combine_partname_ib_resource_and_filename_dict()
        self.write_buffer_files()


    def parse_categoryname_bytelist_dict(self):
        # 1. 收集所有对象和唯一的形态键名称
        all_ordered_objects: list[ObjDataModel] = []
        unique_shape_key_names = set()
        processed_obj_names = set()
        
        for component_model in self._component_model_list:
            for obj_model in component_model.final_ordered_draw_obj_model_list:
                if obj_model.obj_name in processed_obj_names:
                    continue
                processed_obj_names.add(obj_model.obj_name)
                all_ordered_objects.append(obj_model)
                
                # 收集该对象的形态键
                if hasattr(obj_model, 'shape_key_buffer_dict') and obj_model.shape_key_buffer_dict:
                    for sk_name in obj_model.shape_key_buffer_dict.keys():
                        unique_shape_key_names.add(sk_name)

        # 2. 初始化数据容器
        # Category 容器
        category_data_lists = {name: [] for name in self.d3d11GameType.OrderedCategoryNameList}
        # ShapeKey 容器
        shapekey_data_lists = {name: [] for name in unique_shape_key_names}

        # Pre-calculate Position stride/offset for slicing ShapeKey data
        pos_cat_offset = 0
        pos_cat_stride = 0
        target_cat = "Position"
        for cat_name in self.d3d11GameType.OrderedCategoryNameList:
             stride = self.d3d11GameType.CategoryStrideDict.get(cat_name, 0)
             if cat_name == target_cat:
                 pos_cat_stride = stride
                 break
             pos_cat_offset += stride

        # 3. 遍历对象填充容器
        for obj_model in all_ordered_objects:
            # (A) 处理 Category Buffers
            if obj_model.category_buffer_dict:
                for cat_name in self.d3d11GameType.OrderedCategoryNameList:
                    if cat_name in obj_model.category_buffer_dict:
                        # 已经是展平的 uint8 数组或 bytes
                        category_data_lists[cat_name].append(obj_model.category_buffer_dict[cat_name])

            # (B) 处理 ShapeKey Buffers
            # 获取该对象的 Base Position 数据作为回退 (uint8/bytes format)
            base_pos_bytes = None
            if obj_model.category_buffer_dict and "Position" in obj_model.category_buffer_dict:
                 base_pos_bytes = obj_model.category_buffer_dict["Position"]

            for sk_name in unique_shape_key_names:
                sk_data_bytes = None
                
                # 尝试从对象的 shape_key_buffer_dict 中获取
                if hasattr(obj_model, 'shape_key_buffer_dict') and obj_model.shape_key_buffer_dict:
                    sk_buffer_model = obj_model.shape_key_buffer_dict.get(sk_name)
                    if sk_buffer_model and hasattr(sk_buffer_model, 'element_vertex_ndarray'):
                        # ShapeKeyBufferModel 存储的是完整的 Structured Array (包含 Pos/Normal/etc)
                        # 我们需要根据 Stride/Offset 切片出 Position Category 的数据
                        if pos_cat_stride > 0:
                            # 转换为 uint8 2D 视图 (VertexCount, TotalStride)
                            vertex_count = len(sk_buffer_model.element_vertex_ndarray)
                            sk_full_byte_view = sk_buffer_model.element_vertex_ndarray.view(numpy.uint8).reshape(vertex_count, -1)
                            
                            # 切片提取 Position Category
                            sk_pos_bytes = sk_full_byte_view[:, pos_cat_offset : pos_cat_offset + pos_cat_stride].flatten()
                            sk_data_bytes = sk_pos_bytes
                
                # 如果对象没有该形态键，使用 Base Position 填充
                if sk_data_bytes is None:
                    sk_data_bytes = base_pos_bytes
                
                if sk_data_bytes is not None:
                    shapekey_data_lists[sk_name].append(sk_data_bytes)
                else:
                    # 理论上不应发生：既没有 ShapeKey 也没有 Base Position
                    print(f"Warning: Missing Position data for object {obj_model.obj_name} during ShapeKey export.")

        # 4. 合并数据 (一次性 Concatenate)
        self.__categoryname_bytelist_dict = {}
        for cat_name, data_list in category_data_lists.items():
            if data_list:
                self.__categoryname_bytelist_dict[cat_name] = numpy.concatenate(data_list)
        
        self.shapekey_name_bytelist_dict = {}
        for sk_name, data_list in shapekey_data_lists.items():
            if data_list:
                self.shapekey_name_bytelist_dict[sk_name] = numpy.concatenate(data_list)

        # 顺便计算一下步长得到总顶点数
        # print(self.d3d11GameType.CategoryStrideDict)
        if "Position" in self.__categoryname_bytelist_dict:
            position_stride = self.d3d11GameType.CategoryStrideDict.get("Position", 12) # Default stride?
            position_bytelength = len(self.__categoryname_bytelist_dict["Position"])
            self.draw_number = int(position_bytelength/position_stride)

    def __read_component_ib_buf_dict(self):
        obj_name_drawindexedobj_cache_dict:dict[str,M_DrawIndexed] = {}
        
        is_merged_mode = (GlobalConfig.logic_name == LogicName.CTXMC or GlobalConfig.logic_name == LogicName.NierR)
        
        merged_ib_buffer = []  # Total IB buffer for merged mode
        draw_offset = 0        # Corresponds to DrawOffsetIndex
        
        # In Separate mode, total offset is also needed to calculate total_index_count
        total_offset_separate = 0

        # Global Vertex Buffer offset (since VB is always unified in this implementation)
        vertex_number_ib_offset = 0

        new_component_model_list = []
        
        for component_model in self._component_model_list:
            # For Separate mode: each component has its own IB buffer and offset starts from 0 (usually)
            component_ib_buffer = []
            component_draw_offset = 0
            
            new_final_ordered_draw_obj_model_list:list[ObjDataModel] = [] 

            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_model.obj_name

                # Try to reuse cached DrawIndexed object
                drawindexed_obj = obj_name_drawindexedobj_cache_dict.get(obj_name,None)
                
                if drawindexed_obj is not None:
                    # If exists, reuse it. 
                    # Note: We assume that if obj is reused, its draw params are identical.
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                    if not is_merged_mode:
                        # For separate log or debugging, we might just log reuse
                        # Ideally, reused objects shouldn't contribute to offset increase if they are purely instances
                        # But here logic implies they might be same object referenced?
                        # Based on original code, we just assign cached obj and do NOT increment offsets.
                        pass
                else:
                    ib = obj_model.ib
                    if ib is None:
                        print("Can't find ib object for " + obj_name +",skip this obj process.")
                        continue
                    
                    unique_vertex_number_set = set(ib)
                    unique_vertex_number = len(unique_vertex_number_set)

                    # Calculate offset IB for this object
                    current_obj_ib_with_offset = [idx + vertex_number_ib_offset for idx in ib]
                    draw_number = len(current_obj_ib_with_offset)
                    
                    # Accumulate buffers and calculate DrawIndexed params
                    drawindexed_obj = M_DrawIndexed()
                    drawindexed_obj.DrawNumber = str(draw_number)
                    drawindexed_obj.UniqueVertexCount = unique_vertex_number
                    drawindexed_obj.AliasName = "[" + obj_name + "]  (" + str(unique_vertex_number) + ")"
                    
                    if is_merged_mode:
                        merged_ib_buffer.extend(current_obj_ib_with_offset)
                        drawindexed_obj.DrawOffsetIndex = str(draw_offset)
                        draw_offset += draw_number
                    else:
                        component_ib_buffer.extend(current_obj_ib_with_offset)
                        # For separate mode, offset usually starts from 0 for each component file?
                        # Actually based on original code 'offset = offset + draw_number' (reset per component in loop)
                        drawindexed_obj.DrawOffsetIndex = str(component_draw_offset)
                        component_draw_offset += draw_number
                        total_offset_separate += draw_number

                    # Update global vertex offset (VB is shared across all components/draws in this current context usually?)
                    # Original code 'vertex_number_ib_offset = vertex_number_ib_offset + unique_vertex_number' is executed in BOTH modes inside the loop
                    vertex_number_ib_offset += unique_vertex_number
                    
                    # Cache and Store
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                    obj_name_drawindexedobj_cache_dict[obj_name] = drawindexed_obj

                obj_model.drawindexed_obj = drawindexed_obj
                new_final_ordered_draw_obj_model_list.append(obj_model)
            
            # Update component model
            component_model.final_ordered_draw_obj_model_list = new_final_ordered_draw_obj_model_list
            new_component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = copy.deepcopy(component_model)
            
            # Store Component Buffer (Separate Mode)
            if not is_merged_mode:
                if len(component_ib_buffer) == 0:
                    LOG.warning(self.draw_ib + " collection: " + component_model.component_name + " is hide, skip export ib buf.")
                else:
                    self.componentname_ibbuf_dict[component_model.component_name] = component_ib_buffer

        self._component_model_list = new_component_model_list

        # Finalize (Merged Mode) and Total Count
        if is_merged_mode:
            self.total_index_count = draw_offset
            # In Merged mode, we stick the big buffer into every component? 
            # Original code: iterate components allowing export if ib_buf is not empty.
            if len(merged_ib_buffer) != 0:
                for component_model in self._component_model_list:
                     self.componentname_ibbuf_dict[component_model.component_name] = merged_ib_buffer
            else:
                 for component_model in self._component_model_list:
                    LOG.warning(self.draw_ib + " collection: " + component_model.component_name + " is hide, skip export ib buf.")
        else:
            self.total_index_count = total_offset_separate

        

    def combine_partname_ib_resource_and_filename_dict(self):
        '''
        拼接每个PartName对应的IB文件的Resource和filename,这样生成ini的时候以及导出Mod的时候就可以直接使用了。
        '''
        for partname in self.import_config.part_name_list:
            style_part_name = "Component" + partname
            ib_resource_name = "Resource_" + self.draw_ib + "_" + style_part_name
            ib_buf_filename = self.draw_ib + "-" + style_part_name + ".buf"
            self.PartName_IBResourceName_Dict[partname] = ib_resource_name
            self.PartName_IBBufferFileName_Dict[partname] = ib_buf_filename

    def write_buffer_files(self):
        '''
        导出当前Mod的所有Buffer文件
        '''
        buf_output_folder = GlobalConfig.path_generatemod_buffer_folder()
        # print("Write Buffer Files::")
        # Export Index Buffer files.
        for partname in self.import_config.part_name_list:
            component_name = "Component " + partname
            ib_buf = self.componentname_ibbuf_dict.get(component_name,None)

            if ib_buf is None:
                print("Export Skip, Can't get ib buf for partname: " + partname)
            else:
                buf_filename = self.PartName_IBBufferFileName_Dict[partname]
                BufferExportHelper.write_buf_ib_r32_uint(ib_buf,buf_filename)
                
        # print("Export Category Buffers::")
        # Export category buffer files.
        for category_name, category_buf in self.__categoryname_bytelist_dict.items():
            buf_path = buf_output_folder + self.draw_ib + "-" + category_name + ".buf"
            # print("write: " + buf_path)
            # print(type(category_buf[0]))
             # 将 list 转换为 numpy 数组
            # category_array = numpy.array(category_buf, dtype=numpy.uint8)
            with open(buf_path, 'wb') as ibf:
                category_buf.tofile(ibf)

        # Export ShapeKey buffer files.
        if self.shapekey_name_bytelist_dict:
            # 需要把Shape.hlsl复制到Mod文件夹下面的res文件夹下面
            res_path = os.path.join(GlobalConfig.path_generate_mod_folder(),"res\\")

            if not os.path.exists(res_path):
                os.makedirs(res_path)

            # 获取当前文件(draw_ib_model.py)所在目录下的res文件夹
            current_res_path = os.path.join(os.path.dirname(__file__), "res")
            shape_hlsl_path = os.path.join(current_res_path, "Shapes.hlsl")
            
            if os.path.exists(shape_hlsl_path):
                if not os.path.exists(res_path):
                    os.makedirs(res_path)
                
                shutil.copy(shape_hlsl_path, res_path)
                print(f"Copied Shape.hlsl to {res_path}")

            print("Export ShapeKey Buffers::")
            for sk_name, sk_buf in self.shapekey_name_bytelist_dict.items():
                sk_filename = "Position." + sk_name + ".buf" 
                # 这里根据需求，也许需要加上 hash 前缀，如 self.draw_ib + "-" + sk_filename
                # 但根据用户指示："名字就是Position.形态键名称.buf", 这里直接拼接在 hash 后面比较稳妥
                # 通常格式: [Hash]-Position.[SKName].buf
                
                buf_path = buf_output_folder + self.draw_ib + "-" + sk_filename
                # print("write sk: " + buf_path)
                with open(buf_path, 'wb') as skf:
                    sk_buf.tofile(skf)



