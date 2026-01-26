
import math
import bpy
import copy

from ..config.main_config import GlobalConfig, LogicName

from ..utils.obj_utils import ObjUtils
from ..utils.log_utils import LOG
from ..utils.collection_utils import CollectionUtils, CollectionColor
from ..utils.config_utils import ConfigUtils
from ..utils.tips_utils import TipUtils

from ..base.m_key import M_Key
from ..base.m_condition import M_Condition
from ..base.d3d11_gametype import D3D11GameType
from ..base.obj_data_model import ObjDataModel
from ..base.m_global_key_counter import M_GlobalKeyCounter

from ..common.obj_element_model import ObjElementModel
from ..common.obj_buffer_model_unity import ObjBufferModelUnity
from ..helper.obj_buffer_helper import ObjBufferHelper

from .blueprint_export_helper import BlueprintExportHelper

class BluePrintModel:

    
    def __init__(self):
        # 全局按键名称和按键属性字典
        self.keyname_mkey_dict:dict[str,M_Key] = {} 

        # 全局obj_model列表，主要是obj_model里装了每个obj的生效条件。
        self.ordered_draw_obj_data_model_list:list[ObjDataModel] = [] 

        # 从输出节点开始递归解析所有的节点
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        output_node = BlueprintExportHelper.get_output_node(tree)
        self.parse_current_node(output_node, [])


        self.draw_ib__component_count_list__dict = {}

        for obj_data_model in self.ordered_draw_obj_data_model_list:
            draw_ib = obj_data_model.draw_ib
            component_count = obj_data_model.component_count

            component_count_list = []
            if draw_ib in self.draw_ib__component_count_list__dict:
                component_count_list = self.draw_ib__component_count_list__dict[draw_ib]
            
            if component_count not in component_count_list:
                component_count_list.append(component_count)

            component_count_list.sort()
            
            self.draw_ib__component_count_list__dict[draw_ib] = component_count_list

    def parse_current_node(self, current_node:bpy.types.Node, chain_key_list:list[M_Key]):
        '''
        这个是递归方法，就好像BranchModel中的递归一样

        解析当前节点，获取其连接的所有节点的信息,分类进行解析
        '''
        
        for unknown_node in BlueprintExportHelper.get_connected_nodes(current_node):

            if unknown_node.bl_idname == "SSMTNode_Object_Group":
                # 如果是单纯的分组节点，则不进行任何处理直接传递下去
                self.parse_current_node(unknown_node, chain_key_list)

            elif unknown_node.bl_idname == "SSMTNode_ToggleKey":
                # 如果是按键开关节点，则添加一个Key，更新全局Key字典，更新Key列表并传递解析下去
                m_key = M_Key()
                current_add_key_index = len(self.keyname_mkey_dict.keys())
                m_key.key_name = "$swapkey" + str(M_GlobalKeyCounter.global_key_index)

                m_key.value_list = [0,1]

                # 设置键具体是哪个键，由用户指定
                m_key.initialize_vk_str = unknown_node.key_name

                # 设置是否默认开启
                if unknown_node.default_on:
                    m_key.initialize_value = 1
                else:
                    m_key.initialize_value = 0
                
                # 创建的key加入全局key列表
                self.keyname_mkey_dict[m_key.key_name] = m_key

                if len(self.keyname_mkey_dict.keys()) > current_add_key_index:
                    M_GlobalKeyCounter.global_key_index = M_GlobalKeyCounter.global_key_index + 1
                
                # 创建的key要加入chain_key_list传递下去
                # 因为传递解析下去的话，要让这个key生效，而又因为它是按键开关key，所以value为1生效，所以tmp_value设为1
                chain_tmp_key = copy.deepcopy(m_key)
                chain_tmp_key.tmp_value = 1

                tmp_chain_key_list = copy.deepcopy(chain_key_list)
                tmp_chain_key_list.append(chain_tmp_key)

                # 递归解析
                self.parse_current_node(unknown_node, tmp_chain_key_list)

            elif unknown_node.bl_idname == "SSMTNode_SwitchKey":
                # 如果是按键切换节点，则该节点所有的分支节点，并逐个处理
                switch_node_list = BlueprintExportHelper.get_connected_nodes(unknown_node)
                if len(switch_node_list) == 1:
                    # 如果只有一个分支的话，就当成组节点进行处理
                    self.parse_current_node(switch_node_list[0], chain_key_list)
                else:
                    m_key = M_Key()
                    current_add_key_index = len(self.keyname_mkey_dict.keys())
                    m_key.key_name = "$switchkey" + str(M_GlobalKeyCounter.global_key_index)

                    m_key.value_list = list(range(len(switch_node_list)))

                    m_key.initialize_vk_str = unknown_node.key_name
                    m_key.initialize_value = 0  # 默认选择第一个分支

                    # 创建的key加入全局key列表
                    self.keyname_mkey_dict[m_key.key_name] = m_key

                    # 更新全局key索引
                    if len(self.keyname_mkey_dict.keys()) > current_add_key_index:
                        M_GlobalKeyCounter.global_key_index = M_GlobalKeyCounter.global_key_index + 1

                    # 逐个处理每个分支节点
                    key_tmp_value = 0
                    for switch_node in switch_node_list:
                        # 为每个分支创建一个临时key传递下去
                        chain_tmp_key = copy.deepcopy(m_key)
                        chain_tmp_key.tmp_value = key_tmp_value

                        tmp_chain_key_list = copy.deepcopy(chain_key_list)
                        tmp_chain_key_list.append(chain_tmp_key)

                        key_tmp_value = key_tmp_value + 1

                        # 递归解析
                        self.parse_current_node(switch_node, tmp_chain_key_list)
            elif unknown_node.bl_idname == "SSMTNode_Object_Info":
                obj_model = ObjDataModel(obj_name=unknown_node.object_name)
                obj_model.condition = M_Condition(work_key_list=copy.deepcopy(chain_key_list))
                
                # 每遇到一个obj，都把这个obj加入顺序渲染列表
                self.ordered_draw_obj_data_model_list.append(obj_model)


    def get_obj_data_model_list_by_draw_ib(self,draw_ib:str):
        '''
        只返回指定draw_ib的obj列表
        这个方法存在的目的是为了兼容鸣潮的MergedObj
        这里只是根据IB获取一下对应的obj列表,不需要额外计算其它东西,因为WWMI的逻辑是融合后计算。
        '''
    
        final_ordered_draw_obj_model_list:list[ObjDataModel] = [] 
        
        for obj_model in self.ordered_draw_obj_data_model_list:

            # 只统计给定DrawIB的数据
            if obj_model.draw_ib != draw_ib:
                continue

            final_ordered_draw_obj_model_list.append(copy.deepcopy(obj_model))
        
        return final_ordered_draw_obj_model_list
    

    def get_buffered_obj_data_model_list_by_draw_ib_and_game_type(self,draw_ib:str,d3d11_game_type:D3D11GameType):
        # print("BranchModel.get_buffered_obj_data_model_list_by_draw_ib_and_game_type()")
        '''
        调用这个方法的时候才转换Buffer，不调用的话不转换
        (1) 读取obj的category_buffer
        (2) 读取obj的ib
        (3) 设置到最终的ordered_draw_obj_model_list
        '''
        __obj_name_ib_dict:dict[str,list] = {} 
        __obj_name_category_buffer_list_dict:dict[str,list] =  {} 
        __obj_name_shape_key_buffer_dict:dict[str,dict] = {}

        obj_name_obj_model_cache_dict:dict[str,ObjDataModel] = {}

        for obj_model in self.ordered_draw_obj_data_model_list:

            # 只统计给定DrawIB的数据
            if obj_model.draw_ib != draw_ib:
                continue

            obj_name = obj_model.obj_name

            obj = bpy.data.objects[obj_name]
            
            obj_model_cached = obj_name_obj_model_cache_dict.get(obj_name,None)
            if obj_model_cached is not None:
                LOG.info("Using cached model for " + obj_name)
                __obj_name_ib_dict[obj.name] = obj_model_cached.ib
                __obj_name_category_buffer_list_dict[obj.name] = obj_model_cached.category_buffer_dict
                if hasattr(obj_model_cached, 'shape_key_buffer_dict'):
                    __obj_name_shape_key_buffer_dict[obj.name] = obj_model_cached.shape_key_buffer_dict
            else:
                # XXX 我们在导出具体数据之前，先对模型整体的权重进行normalize_all预处理，才能让后续的具体每一个权重的normalize_all更好的工作
                # 使用这个的前提是当前obj中没有锁定的顶点组，所以这里要先进行判断。
                if "Blend" in d3d11_game_type.OrderedCategoryNameList:
                    all_vgs_locked = ObjUtils.is_all_vertex_groups_locked(obj)
                    if not all_vgs_locked:
                        ObjUtils.normalize_all(obj)
                
                # 预处理翻转过去
                # TODO 目前的处理方式是翻转过去，然后读取完数据再翻转回来
                # 实际上这套流程和WWMI的处理有相似的地方，可以合二为一变为一套统一的流程
                # 不过懒得搞了，以后再说吧
                if (GlobalConfig.logic_name == LogicName.SRMI 
                    or GlobalConfig.logic_name == LogicName.GIMI
                    or GlobalConfig.logic_name == LogicName.HIMI):
                    ObjUtils.select_obj(obj)

                    obj.rotation_euler[0] = math.radians(-90)
                    obj.rotation_euler[1] = 0
                    obj.rotation_euler[2] = 0
                
                    # 应用旋转和缩放
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

                obj_buffer_model = ObjBufferModelUnity(obj=obj, d3d11_game_type=d3d11_game_type)

                # 后处理翻转回来
                if (GlobalConfig.logic_name == LogicName.SRMI 
                    or GlobalConfig.logic_name == LogicName.GIMI
                    or GlobalConfig.logic_name == LogicName.HIMI):
                    ObjUtils.select_obj(obj)

                    obj.rotation_euler[0] = math.radians(90)
                    obj.rotation_euler[1] = 0
                    obj.rotation_euler[2] = 0
                
                    # 应用旋转和缩放
                    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                
                __obj_name_ib_dict[obj.name] = obj_buffer_model.ib
                __obj_name_category_buffer_list_dict[obj.name] = obj_buffer_model.category_buffer_dict
                # 新增：收集 shape_key_buffer_dict
                if hasattr(obj_buffer_model, 'shape_key_buffer_dict'):
                    __obj_name_shape_key_buffer_dict[obj.name] = obj_buffer_model.shape_key_buffer_dict

                obj_name_obj_model_cache_dict[obj_name] = obj_buffer_model
        
        final_ordered_draw_obj_model_list:list[ObjDataModel] = [] 

        print(__obj_name_ib_dict.keys())
        
        for obj_model in self.ordered_draw_obj_data_model_list:

            # 只统计给定DrawIB的数据
            if obj_model.draw_ib != draw_ib:
                continue

            obj_name = obj_model.obj_name

            obj_model.ib = __obj_name_ib_dict[obj_name]
            obj_model.category_buffer_dict = __obj_name_category_buffer_list_dict[obj_name]
            
            # 这里的 obj_model 是 ObjDataModel 类型，我们需要动态给它添加 shape_key_buffer_dict 属性
            if obj_name in __obj_name_shape_key_buffer_dict:
                 obj_model.shape_key_buffer_dict = __obj_name_shape_key_buffer_dict[obj_name]

            final_ordered_draw_obj_model_list.append(copy.deepcopy(obj_model))
        
        return final_ordered_draw_obj_model_list
                

                



