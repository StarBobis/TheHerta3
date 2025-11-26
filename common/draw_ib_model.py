import numpy
import struct
import copy


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

from .branch_model import BranchModel
from .obj_writer import ObjWriter

class DrawIBModel:
    '''
    这个代表了一个DrawIB的Mod导出模型
    Mod导出可以调用这个模型来进行业务逻辑部分
    每个游戏的DrawIBModel都是不同的，但是一部分是可以复用的
    (例如WWMI就有自己的一套DrawIBModel)
    '''


    # 通过default_factory让每个类的实例的变量分割开来，不再共享类的静态变量
    def __init__(self, draw_ib:str, branch_model:BranchModel):
        # (1) 读取工作空间下的Config.json来设置当前DrawIB的别名
        draw_ib_alias_name_dict:dict[str,str] = ConfigUtils.get_draw_ib_alias_name_dict()
        self.draw_ib:str = draw_ib
        self.draw_ib_alias:str = draw_ib_alias_name_dict.get(draw_ib,draw_ib)

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

        if GlobalConfig.logic_name == LogicName.CTXMC == GlobalConfig.logic_name == LogicName.NierR:
            self.__read_component_ib_buf_dict_merged()
        else:
            self.__read_component_ib_buf_dict_seperated_single()
            
        self.parse_categoryname_bytelist_dict_3()

        # (5) 导出Buffer文件，Export Index Buffer files, Category Buffer files. (And Export ShapeKey Buffer Files.(WWMI))
        # 用于写出IB时使用
        self.PartName_IBResourceName_Dict = {}
        self.PartName_IBBufferFileName_Dict = {}
        self.combine_partname_ib_resource_and_filename_dict()
        self.write_buffer_files()


    def parse_categoryname_bytelist_dict_3(self):
        processed_obj_name_list = [] # 用于记录已经处理过的obj_name，避免重复处理

        for component_model in self._component_model_list:
            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_model.obj_name
                # 如果obj_name已经被处理过了，则跳过
                if obj_name in processed_obj_name_list:
                    continue
                
                # 否则加入已处理列表，并进行处理
                processed_obj_name_list.append(obj_name)
                # 下面的流程是对当前obj处理得到CategoryBuffer，所以如果obj_name已经被处理过，那就不需要继续处理了
                category_buffer_list = obj_model.category_buffer_dict
                
                if category_buffer_list is None:
                    print("Can't find vb object for " + obj_name +",skip this obj process.")
                    continue

                for category_name in self.d3d11GameType.OrderedCategoryNameList:
                    if category_name not in self.__categoryname_bytelist_dict:
                        self.__categoryname_bytelist_dict[category_name] =  category_buffer_list[category_name]
                    else:
                        existing_array = self.__categoryname_bytelist_dict[category_name]
                        buffer_array = category_buffer_list[category_name]

                        # 确保两个数组都是NumPy数组
                        existing_array = numpy.asarray(existing_array)
                        buffer_array = numpy.asarray(buffer_array)

                        # 使用 concatenate 连接两个数组，确保传递的是一个序列（如列表或元组）
                        concatenated_array = numpy.concatenate((existing_array, buffer_array))

                        # 更新字典中的值
                        self.__categoryname_bytelist_dict[category_name] = concatenated_array

                        # self.__categoryname_bytelist_dict[category_name] = numpy.concatenate(self.__categoryname_bytelist_dict[category_name],category_buffer_list[category_name])

        # 顺便计算一下步长得到总顶点数
        # print(self.d3d11GameType.CategoryStrideDict)
        position_stride = self.d3d11GameType.CategoryStrideDict["Position"]
        position_bytelength = len(self.__categoryname_bytelist_dict["Position"])
        self.draw_number = int(position_bytelength/position_stride)

    def __read_component_ib_buf_dict_merged(self):
        '''
        一个DrawIB的所有Component共享整体的IB文件。
        也就是一个DrawIB的所有绘制中，所有的MatchFirstIndex都来源于一个IndexBuffer文件。
        是游戏原本的做法，但是不分开的话，一个IndexBuffer文件会遇到135W顶点索引数的上限。
        
        由于在WWMI中只能使用一个IB文件，而在GI、HSR、HI3、ZZZ等Unity游戏中天生就能使用多个IB文件
        WWMI会用到但是是MergedObj不在这个逻辑里
        '''

        obj_name_drawindexedobj_cache_dict:dict[str,M_DrawIndexed] = {}

        vertex_number_ib_offset = 0
        ib_buf:list[int] = []
        draw_offset = 0

        new_component_model_list = []
        for component_model in self._component_model_list:
            new_final_ordered_draw_obj_model_list:list[ObjDataModel] = [] 

            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_model.obj_name

                drawindexed_obj = obj_name_drawindexedobj_cache_dict.get(obj_name,None)
                if drawindexed_obj is not None:
                    LOG.info("Using cached drawindexed object for " + obj_name)
                    # 如果已经存在的情况下，不改变draw_offset，也不改变vertex_number_ib_offset，直接使用就好了
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                    
                else:
                    # print("processing: " + obj_name)
                    ib = obj_model.ib
                    # ib的数据类型是list[int]
                    unique_vertex_number_set = set(ib)
                    unique_vertex_number = len(unique_vertex_number_set)

                    if ib is None:
                        print("Can't find ib object for " + obj_name +",skip this obj process.")
                        continue
                    
                    # 扩充总IB Buffer
                    offset_ib:list[int] = []
                    for ib_number in ib:
                        offset_ib.append(ib_number + vertex_number_ib_offset)
                    ib_buf.extend(offset_ib)
                    # Add UniqueVertexNumber to show vertex count in mod ini.
                    # print("Draw Number: " + str(unique_vertex_number))
                    vertex_number_ib_offset = vertex_number_ib_offset + unique_vertex_number
                    # print("Component name: " + component_name)
                    # print("Draw Offset: " + str(vertex_number_ib_offset))
                    drawindexed_obj = M_DrawIndexed()
                    draw_number = len(offset_ib)
                    drawindexed_obj.DrawNumber = str(draw_number)
                    drawindexed_obj.DrawOffsetIndex = str(draw_offset)
                    drawindexed_obj.UniqueVertexCount = unique_vertex_number
                    drawindexed_obj.AliasName = "[" + obj_name + "]  (" + str(unique_vertex_number) + ")"
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                    draw_offset = draw_offset + draw_number

                    obj_name_drawindexedobj_cache_dict[obj_name] = drawindexed_obj
                
                obj_model.drawindexed_obj = drawindexed_obj
                new_final_ordered_draw_obj_model_list.append(obj_model)
            
            component_model.final_ordered_draw_obj_model_list = new_final_ordered_draw_obj_model_list
            new_component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = copy.deepcopy(component_model)

        # 累加完毕后draw_offset的值就是总的index_count的值，正好作为WWMI的$object_id
        self.total_index_count = draw_offset

        for component_model in self._component_model_list:
            # Only export if it's not empty.
            if len(ib_buf) != 0:
                self.componentname_ibbuf_dict[component_model.component_name] = ib_buf
            else:
                LOG.warning(self.draw_ib + " collection: " + component_model.component_name + " is hide, skip export ib buf.")
    
    def __read_component_ib_buf_dict_seperated_single(self):
        vertex_number_ib_offset = 0
        total_offset = 0
        
        obj_name_drawindexedobj_cache_dict:dict[str,M_DrawIndexed] = {}

        new_component_model_list = []
        for component_model in self._component_model_list:
            ib_buf = []
            offset = 0

            new_final_ordered_draw_obj_model_list:list[ObjDataModel] = [] 

            for obj_model in component_model.final_ordered_draw_obj_model_list:
                obj_name = obj_model.obj_name

                drawindexed_obj = obj_name_drawindexedobj_cache_dict.get(obj_name,None)

                if drawindexed_obj is not None:
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                else:
                    # print("processing: " + obj_name)
                    ib =  obj_model.ib

                    # ib的数据类型是list[int]
                    unique_vertex_number_set = set(ib)
                    unique_vertex_number = len(unique_vertex_number_set)

                    if ib is None:
                        print("Can't find ib object for " + obj_name +",skip this obj process.")
                        continue

                    offset_ib = []
                    for ib_number in ib:
                        offset_ib.append(ib_number + vertex_number_ib_offset)
                    
                    # print("Component name: " + component_name)
                    # print("Draw Offset: " + str(vertex_number_ib_offset))
                    ib_buf.extend(offset_ib)

                    drawindexed_obj = M_DrawIndexed()
                    draw_number = len(offset_ib)
                    drawindexed_obj.DrawNumber = str(draw_number)
                    drawindexed_obj.DrawOffsetIndex = str(offset)
                    drawindexed_obj.UniqueVertexCount = unique_vertex_number
                    drawindexed_obj.AliasName = "[" + obj_name + "]  (" + str(unique_vertex_number) + ")"
                    self.__obj_name_drawindexed_dict[obj_name] = drawindexed_obj
                    offset = offset + draw_number

                    # 鸣潮需要
                    total_offset = total_offset + draw_number

                    # Add UniqueVertexNumber to show vertex count in mod ini.
                    # print("Draw Number: " + str(unique_vertex_number))
                    vertex_number_ib_offset = vertex_number_ib_offset + unique_vertex_number

                    # 加入缓存
                    obj_name_drawindexedobj_cache_dict[obj_name] = drawindexed_obj

                
                obj_model.drawindexed_obj = drawindexed_obj
                new_final_ordered_draw_obj_model_list.append(obj_model)

            component_model.final_ordered_draw_obj_model_list = new_final_ordered_draw_obj_model_list
            new_component_model_list.append(component_model)
            self.component_name_component_model_dict[component_model.component_name] = copy.deepcopy(component_model)

            # Only export if it's not empty.
            if len(ib_buf) == 0:
                LOG.warning(self.draw_ib + " collection: " + component_model.component_name + " is hide, skip export ib buf.")
            else:
                self.componentname_ibbuf_dict[component_model.component_name] = ib_buf

        self._component_model_list = new_component_model_list

        self.total_index_count = total_offset

        

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
                ObjWriter.write_buf_ib_r32_uint(ib_buf,buf_filename)
                
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



