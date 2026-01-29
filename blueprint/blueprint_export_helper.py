import bpy
from ..config.main_config import GlobalConfig
from ..base.m_key import M_Key

class BlueprintExportHelper:

    # 静态变量，用于强行指定当前要导出的蓝图树（如果在Operator中指定了树名）
    # 如果为 None，则使用默认的 GlobalConfig.workspacename 逻辑
    forced_target_tree_name = None
    
    @staticmethod
    def get_current_blueprint_tree():
        """获取当前工作空间对应的蓝图树"""
        if BlueprintExportHelper.forced_target_tree_name:
           tree_name = BlueprintExportHelper.forced_target_tree_name
        
        tree = bpy.data.node_groups.get(tree_name)
        return tree

    @staticmethod
    def get_node_from_bl_idname(tree, node_type:str):
        """在树中查找输出节点 (假设只有一个)"""
        if not tree:
            return None
        for node in tree.nodes:
            if node.bl_idname == node_type:
                return node
        return None
    
    @staticmethod
    def get_connected_groups(output_node):
        """
        获取连接到输出节点的所有 Group 节点。
        按照 Input 插槽的顺序返回列表。
        """
        connected_groups = []
        if not output_node:
            return connected_groups
            
        # 遍历 Output 节点的所有输入插槽
        for socket in output_node.inputs:
            if socket.is_linked:
                # 遍历连线 (通常一个插槽只有一个连线，但数据结构是列表)
                for link in socket.links:
                    source_node = link.from_node
                    # 确保来源是 Group 节点
                    if source_node.bl_idname == 'SSMTNode_Object_Group':
                         connected_groups.append(source_node)
        
        return connected_groups
    
    @staticmethod
    def get_connected_nodes(current_node):
        """
        按照插槽顺序返回所有连接的节点
        """
        connected_groups = []
        if not current_node:
            return connected_groups
            
        # 遍历 Output 节点的所有输入插槽
        for socket in current_node.inputs:
            if socket.is_linked:
                # 遍历连线 (通常一个插槽只有一个连线，但数据结构是列表)
                for link in socket.links:
                    source_node = link.from_node
                    connected_groups.append(source_node)
        
        return connected_groups
    
    @staticmethod
    def get_objects_from_group(group_node):
        """
        获取连接到某个 Group 节点的所有 Object Info 节点中的物体名称信息。
        """
        objects_info = []
        if not group_node:
            return objects_info

        for socket in group_node.inputs:
            if socket.is_linked:
                for link in socket.links:
                    source_node = link.from_node
                    # 确保来源是 Object Info 节点
                    if source_node.bl_idname == 'SSMTNode_Object_Info':
                        # 这里您可以返回整个节点对象，或者只返回需要的属性
                        # 比如: (ObjName, DrawIB, Component)
                        info = {
                            "object_name": source_node.object_name,
                            "draw_ib": source_node.draw_ib,
                            "component": source_node.component,
                            "node": source_node
                        }
                        objects_info.append(info)
        return objects_info
    

    @staticmethod
    def get_current_shapekeyname_mkey_dict():
        """获取当前蓝图中所有 ShapeKey 节点的形态键名称和按键列表"""
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        shapekey_output_node = BlueprintExportHelper.get_node_from_bl_idname(tree, 'SSMTNode_ShapeKey_Output')

        # 获取连接到shapekey_output_node的所有shapekey节点
        shapekey_nodes = BlueprintExportHelper.get_connected_nodes(shapekey_output_node)

        shapekey_name_mkey_dict = {}

        key_index = 0
        for shapekey_node in shapekey_nodes:
            if shapekey_node.bl_idname != 'SSMTNode_ShapeKey':
                continue

            shapekey_name = shapekey_node.shapekey_name
            key = shapekey_node.key

            m_key = M_Key()
            m_key.key_name = "$shapekey" + str(key_index)
            m_key.initialize_value = 0
            m_key.initialize_vk_str = key

            shapekey_name_mkey_dict[shapekey_name] = m_key

            key_index += 1
        
        return shapekey_name_mkey_dict



            
        