import bpy
from ..config.main_config import GlobalConfig
from ..base.m_key import M_Key

class BlueprintExportHelper:

    # 静态变量，用于强行指定当前要导出的蓝图树（如果在Operator中指定了树名）
    # 如果为 None，则使用默认的 GlobalConfig.workspacename 逻辑
    forced_target_tree_name = None
    
    # 静态变量，用于多文件导出功能
    # 存储当前导出次数（从1开始）
    current_export_index = 1
    
    # 静态变量，存储最大导出次数
    max_export_count = 1
    
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
    def get_nodes_from_bl_idname(tree, node_type:str):
        """在树中查找所有匹配的节点"""
        if not tree:
            return []
        nodes = []
        for node in tree.nodes:
            if node.bl_idname == node_type:
                nodes.append(node)
        return nodes
    
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
            comment = getattr(shapekey_node, 'comment', '')

            m_key = M_Key()
            m_key.key_name = "$shapekey" + str(key_index)
            m_key.initialize_value = 0
            m_key.initialize_vk_str = key
            m_key.comment = comment

            shapekey_name_mkey_dict[shapekey_name] = m_key

            key_index += 1
        
        return shapekey_name_mkey_dict

    @staticmethod
    def get_datatype_node_info():
        """获取当前蓝图中连接到输出节点的数据类型节点信息"""
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return None
        
        # 获取输出节点
        output_node = BlueprintExportHelper.get_node_from_bl_idname(tree, 'SSMTNode_Result_Output')
        if not output_node:
            return None
        
        # 递归查找所有连接到输出节点的数据类型节点
        datatype_nodes = BlueprintExportHelper._find_datatype_nodes_connected_to_output(output_node)
        if not datatype_nodes:
            return None
        
        # 返回所有数据类型节点的信息
        node_info_list = []
        for node in datatype_nodes:
            node_info_list.append({
                "draw_ib_match": node.draw_ib_match,
                "tmp_json_path": node.tmp_json_path,
                "loaded_data": node.loaded_data,
                "node": node
            })
        
        return node_info_list
    
    @staticmethod
    def _find_datatype_nodes_connected_to_output(node, visited=None):
        """递归查找连接到输出节点的所有数据类型节点"""
        if visited is None:
            visited = set()
        
        if node.name in visited:
            return []
        
        visited.add(node.name)
        datatype_nodes = []
        
        # 如果当前节点是数据类型节点，添加到列表
        if node.bl_idname == 'SSMTNode_DataType':
            datatype_nodes.append(node)
        
        # 递归查找连接的节点
        connected_nodes = BlueprintExportHelper.get_connected_nodes(node)
        for connected_node in connected_nodes:
            datatype_nodes.extend(BlueprintExportHelper._find_datatype_nodes_connected_to_output(connected_node, visited))
        
        return datatype_nodes
    
    @staticmethod
    def get_multifile_export_nodes():
        """获取当前蓝图中所有多文件导出节点"""
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return []
        
        multifile_nodes = []
        for node in tree.nodes:
            if node.bl_idname == 'SSMTNode_MultiFile_Export':
                multifile_nodes.append(node)
        
        return multifile_nodes
    
    @staticmethod
    def calculate_max_export_count():
        """计算最大导出次数"""
        multifile_nodes = BlueprintExportHelper.get_multifile_export_nodes()
        
        if not multifile_nodes:
            return 1
        
        max_count = 1
        for node in multifile_nodes:
            object_count = len(node.object_list)
            if object_count > max_count:
                max_count = object_count
        
        BlueprintExportHelper.max_export_count = max_count
        return max_count
    
    @staticmethod
    def reset_export_state():
        """重置导出状态"""
        BlueprintExportHelper.current_export_index = 1
        BlueprintExportHelper.max_export_count = 1
    
    @staticmethod
    def increment_export_index():
        """增加导出次数"""
        BlueprintExportHelper.current_export_index += 1
    
    @staticmethod
    def get_current_export_index():
        """获取当前导出次数"""
        return BlueprintExportHelper.current_export_index
    
    @staticmethod
    def get_max_export_count():
        """获取最大导出次数"""
        return BlueprintExportHelper.max_export_count
    
    @staticmethod
    def update_multifile_export_nodes(export_index):
        """更新多文件导出节点的当前物体信息"""
        from ..blueprint.blueprint_model import BluePrintModel
        
        multifile_nodes = BlueprintExportHelper.get_multifile_export_nodes()
        if not multifile_nodes:
            return
        
        for node in multifile_nodes:
            node.current_export_index = export_index
    
    @staticmethod
    def update_export_path(export_index):
        """更新导出路径（Buffer01、Buffer02等）"""
        from ..config.main_config import GlobalConfig
        
        multifile_nodes = BlueprintExportHelper.get_multifile_export_nodes()
        has_multifile_nodes = len(multifile_nodes) > 0
        
        if has_multifile_nodes:
            GlobalConfig.buffer_folder_suffix = f"{export_index:02d}"
        else:
            GlobalConfig.buffer_folder_suffix = ""
        
        print(f"更新Buffer文件夹后缀: Buffer{GlobalConfig.buffer_folder_suffix}")
    
    @staticmethod
    def restore_export_path():
        """恢复原始导出路径"""
        from ..config.main_config import GlobalConfig
        
        GlobalConfig.buffer_folder_suffix = ""
        print(f"恢复Buffer文件夹后缀: Buffer")

    @staticmethod
    def get_postprocess_nodes():
        """获取连接到Generate Mod输出节点的所有后处理节点，按连接顺序返回"""
        tree = BlueprintExportHelper.get_current_blueprint_tree()
        if not tree:
            return []
        
        output_node = BlueprintExportHelper.get_node_from_bl_idname(tree, 'SSMTNode_Result_Output')
        if not output_node:
            return []
        
        postprocess_nodes = []
        
        def collect_postprocess_nodes(node, visited=None):
            """递归收集后处理节点"""
            if visited is None:
                visited = set()
            
            if node.name in visited:
                return
            
            visited.add(node.name)
            
            for output in node.outputs:
                if output.is_linked:
                    for link in output.links:
                        target_node = link.to_node
                        
                        if target_node.bl_idname.startswith('SSMTNode_PostProcess'):
                            postprocess_nodes.append(target_node)
                            collect_postprocess_nodes(target_node, visited)
        
        collect_postprocess_nodes(output_node)
        
        return postprocess_nodes
    
    @staticmethod
    def execute_postprocess_nodes(mod_export_path):
        """执行所有后处理节点，按连接顺序逐个运行"""
        postprocess_nodes = BlueprintExportHelper.get_postprocess_nodes()
        
        if not postprocess_nodes:
            print("没有找到后处理节点，跳过后处理流程")
            return
        
        print(f"找到 {len(postprocess_nodes)} 个后处理节点，开始执行...")
        
        for index, node in enumerate(postprocess_nodes):
            print(f"执行第 {index + 1}/{len(postprocess_nodes)} 个后处理节点: {node.name}")
            
            try:
                if hasattr(node, 'execute_postprocess'):
                    node.execute_postprocess(mod_export_path)
                else:
                    print(f"警告: 节点 {node.name} 没有实现 execute_postprocess 方法")
            except Exception as e:
                print(f"执行后处理节点 {node.name} 时出错: {e}")
                import traceback
                traceback.print_exc()
        
        print("所有后处理节点执行完成")



            
        