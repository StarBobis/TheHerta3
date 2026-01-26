import bpy
from ..config.main_config import GlobalConfig


class BlueprintExportHelper:
    
    @staticmethod
    def get_current_blueprint_tree():
        """获取当前工作空间对应的蓝图树"""
        tree_name = f"Mod_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "SSMT_Mod_Logic"
        tree = bpy.data.node_groups.get(tree_name)
        return tree

    @staticmethod
    def get_output_node(tree):
        """在树中查找输出节点 (假设只有一个)"""
        if not tree:
            return None
        for node in tree.nodes:
            if node.bl_idname == 'SSMTNode_Result_Output':
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