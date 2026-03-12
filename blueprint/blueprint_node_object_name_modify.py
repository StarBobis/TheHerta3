import bpy
from bpy.types import PropertyGroup
from .blueprint_node_base import SSMTNodeBase


class NameMappingItem(bpy.types.PropertyGroup):
    original_name: bpy.props.StringProperty(
        name="原始名称",
        description="要替换的原始名称片段",
        default=""
    )
    
    new_name: bpy.props.StringProperty(
        name="新名称",
        description="替换成的新名称片段",
        default=""
    )


class SSMT_UL_NameMapping(bpy.types.UIList):
    bl_idname = 'SSMT_UL_NameMapping'
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.prop(item, "original_name", text="", placeholder="原始名称")
            row.label(text=">>")
            row.prop(item, "new_name", text="", placeholder="新名称")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.prop(item, "original_name", text="")


class SSMTNode_Object_Name_Modify(SSMTNodeBase):
    '''物体名称修改节点 - 基于映射表修改物体名称，支持多个映射关系，支持反向映射和后处理'''
    bl_idname = 'SSMTNode_Object_Name_Modify'
    bl_label = 'Object Name Modify'
    bl_icon = 'SORTALPHA'
    bl_width_min = 400
    
    mapping_list: bpy.props.CollectionProperty(type=NameMappingItem)
    active_mapping_index: bpy.props.IntProperty(default=0)
    
    reverse_mapping: bpy.props.BoolProperty(
        name="反向映射",
        description="启用后，映射关系将被反转（原始名称和新名称互换）",
        default=False
    )
    
    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Object Input")
        self.outputs.new('SSMTSocketObject', "Object Output")
        self.outputs.new('SSMTSocketPostProcess', "Post Process")
        self.width = 400
    
    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="名称映射表 (按顺序匹配):", icon='SORTALPHA')
        
        row = box.row()
        row.template_list("SSMT_UL_NameMapping", "", self, "mapping_list", self, "active_mapping_index", rows=3)
        
        col = row.column(align=True)
        col.operator("ssmt.name_mapping_add", icon='ADD', text="")
        col.operator("ssmt.name_mapping_remove", icon='REMOVE', text="")
        col.separator()
        col.operator("ssmt.name_mapping_move_up", icon='TRIA_UP', text="")
        col.operator("ssmt.name_mapping_move_down", icon='TRIA_DOWN', text="")
        
        row = box.row()
        row.prop(self, "reverse_mapping", icon='ARROW_LEFTRIGHT')
        if self.reverse_mapping:
            row.label(text="映射已反转", icon='INFO')
    
    def get_preview_info(self):
        """获取预览信息，递归获取所有连接的物体"""
        result = []
        
        if not self.inputs[0].is_linked:
            return result
        
        visited = set()
        
        def collect_object_names(node, depth=0):
            """递归收集所有连接的物体名称"""
            if node in visited:
                return
            visited.add(node)
            
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    modified_name = self.get_modified_object_name(obj_name)
                    result.append({
                        'original_name': obj_name,
                        'modified_name': modified_name,
                        'source_node': node.name
                    })
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        modified_name = self.get_modified_object_name(obj_name)
                        result.append({
                            'original_name': obj_name,
                            'modified_name': modified_name,
                            'source_node': f"{node.name} (多文件)"
                        })
            elif node.bl_idname == 'SSMTNode_Object_Name_Modify':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
            elif node.bl_idname == 'SSMTNode_VertexGroupProcess':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
            elif node.bl_idname == 'SSMTNode_Object_Group':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
            elif node.bl_idname == 'SSMTNode_ToggleKey':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
            elif node.bl_idname == 'SSMTNode_SwitchKey':
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
            elif node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                for input_socket in nested_node.inputs:
                                    if input_socket.is_linked:
                                        for link in input_socket.links:
                                            collect_object_names(link.from_node, depth + 1)
            else:
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node, depth + 1)
        
        for link in self.inputs[0].links:
            collect_object_names(link.from_node)
        
        return result
    
    def get_modified_object_name(self, original_name):
        if not original_name:
            return original_name
        
        modified_name = original_name
        
        for item in self.mapping_list:
            original = item.original_name
            new = item.new_name
            
            if self.reverse_mapping:
                original, new = new, original
            
            if original and original in modified_name:
                old_name = modified_name
                modified_name = modified_name.replace(original, new)
                print(f"[NameModify] 物体 {original_name}: '{original}' -> '{new}'")
                print(f"[NameModify] 中间结果: {old_name} -> {modified_name}")
        
        return modified_name
    
    def get_mapping_dict(self):
        """获取映射字典（用于后处理阶段）
        
        返回格式：{配置表中的名称片段: 场景中的名称片段}
        用于将配置表中的原始名称转换为场景中的新名称
        """
        mapping = {}
        for item in self.mapping_list:
            original = item.original_name
            new = item.new_name
            
            if original and new:
                if self.reverse_mapping:
                    mapping[new] = original
                else:
                    mapping[original] = new
        return mapping
    
    def is_valid(self):
        if len(self.mapping_list) == 0:
            return False
        
        if self.reverse_mapping:
            return any(item.new_name for item in self.mapping_list)
        else:
            return any(item.original_name for item in self.mapping_list)
    
    def get_connected_object_names(self):
        """获取所有连接的物体名称（用于导出流程）"""
        result = []
        
        if not self.inputs[0].is_linked:
            return result
        
        visited = set()
        
        def collect_object_names(node):
            if node in visited:
                return
            visited.add(node)
            
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    result.append(obj_name)
            elif node.bl_idname == 'SSMTNode_MultiFile_Export':
                for item in node.object_list:
                    obj_name = getattr(item, 'object_name', '')
                    if obj_name:
                        result.append(obj_name)
            elif node.bl_idname == 'SSMTNode_Blueprint_Nest':
                blueprint_name = getattr(node, 'blueprint_name', '')
                if blueprint_name:
                    nested_tree = bpy.data.node_groups.get(blueprint_name)
                    if nested_tree and nested_tree.bl_idname == 'SSMTBlueprintTreeType':
                        for nested_node in nested_tree.nodes:
                            if nested_node.bl_idname == 'SSMTNode_Result_Output':
                                for input_socket in nested_node.inputs:
                                    if input_socket.is_linked:
                                        for link in input_socket.links:
                                            collect_object_names(link.from_node)
            else:
                for input_socket in node.inputs:
                    if input_socket.is_linked:
                        for link in input_socket.links:
                            collect_object_names(link.from_node)
        
        for link in self.inputs[0].links:
            collect_object_names(link.from_node)
        
        return result
    
    def execute_postprocess(self, mod_export_path):
        """
        后处理阶段执行：修改配置表中的物体名称（仅用于识别）
        
        这个方法会在导出完成后执行，用于修改后续后处理节点接收到的配置表信息。
        主要用于跨IB节点等需要识别物体名称的场景。
        """
        print(f"[NameModify] 后处理阶段开始执行，Mod导出路径: {mod_export_path}")
        
        if not self.is_valid():
            print(f"[NameModify] 映射表为空，跳过后处理")
            return
        
        mapping = self.get_mapping_dict()
        print(f"[NameModify] 映射字典: {mapping}")
        
        self._propagate_mapping_to_downstream_nodes(mapping)
        
        print(f"[NameModify] 后处理阶段执行完成")
    
    def _propagate_mapping_to_downstream_nodes(self, mapping):
        """递归地将映射传递给所有下游后处理节点"""
        visited = set()
        
        def propagate(node):
            if node.name in visited:
                return
            visited.add(node.name)
            
            for output in node.outputs:
                if output.is_linked:
                    for link in output.links:
                        target_node = link.to_node
                        
                        if target_node.bl_idname.startswith('SSMTNode_PostProcess') or \
                           target_node.bl_idname == 'SSMTNode_Object_Name_Modify':
                            
                            if hasattr(target_node, 'apply_name_mapping'):
                                target_node.apply_name_mapping(mapping)
                                print(f"[NameModify] 已将映射传递给节点: {target_node.name}")
                            
                            propagate(target_node)
        
        propagate(self)


class SSMT_OT_NameMappingAdd(bpy.types.Operator):
    bl_idname = "ssmt.name_mapping_add"
    bl_label = "添加映射"
    bl_description = "添加新的名称映射项"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_Object_Name_Modify':
            self.report({'ERROR'}, "请先选择物体名称修改节点")
            return {'CANCELLED'}
        
        new_item = node.mapping_list.add()
        new_item.original_name = ""
        new_item.new_name = ""
        node.active_mapping_index = len(node.mapping_list) - 1
        
        return {'FINISHED'}


class SSMT_OT_NameMappingRemove(bpy.types.Operator):
    bl_idname = "ssmt.name_mapping_remove"
    bl_label = "删除映射"
    bl_description = "删除选中的名称映射项"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_Object_Name_Modify':
            self.report({'ERROR'}, "请先选择物体名称修改节点")
            return {'CANCELLED'}
        
        if node.active_mapping_index >= 0 and node.active_mapping_index < len(node.mapping_list):
            node.mapping_list.remove(node.active_mapping_index)
            if node.active_mapping_index >= len(node.mapping_list) and node.active_mapping_index > 0:
                node.active_mapping_index -= 1
        
        return {'FINISHED'}


class SSMT_OT_NameMappingMoveUp(bpy.types.Operator):
    bl_idname = "ssmt.name_mapping_move_up"
    bl_label = "上移"
    bl_description = "将选中的映射项向上移动（提高匹配优先级）"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_Object_Name_Modify':
            self.report({'ERROR'}, "请先选择物体名称修改节点")
            return {'CANCELLED'}
        
        if node.active_mapping_index > 0:
            node.mapping_list.move(node.active_mapping_index, node.active_mapping_index - 1)
            node.active_mapping_index -= 1
        
        return {'FINISHED'}


class SSMT_OT_NameMappingMoveDown(bpy.types.Operator):
    bl_idname = "ssmt.name_mapping_move_down"
    bl_label = "下移"
    bl_description = "将选中的映射项向下移动（降低匹配优先级）"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_Object_Name_Modify':
            self.report({'ERROR'}, "请先选择物体名称修改节点")
            return {'CANCELLED'}
        
        if node.active_mapping_index < len(node.mapping_list) - 1:
            node.mapping_list.move(node.active_mapping_index, node.active_mapping_index + 1)
            node.active_mapping_index += 1
        
        return {'FINISHED'}


class SSMT_OT_NameMappingReverse(bpy.types.Operator):
    bl_idname = "ssmt.name_mapping_reverse"
    bl_label = "反转映射"
    bl_description = "交换所有映射项的原始名称和新名称"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_Object_Name_Modify':
            self.report({'ERROR'}, "请先选择物体名称修改节点")
            return {'CANCELLED'}
        
        for item in node.mapping_list:
            item.original_name, item.new_name = item.new_name, item.original_name
        
        self.report({'INFO'}, "已反转所有映射项")
        return {'FINISHED'}


classes = (
    NameMappingItem,
    SSMT_UL_NameMapping,
    SSMTNode_Object_Name_Modify,
    SSMT_OT_NameMappingAdd,
    SSMT_OT_NameMappingRemove,
    SSMT_OT_NameMappingMoveUp,
    SSMT_OT_NameMappingMoveDown,
    SSMT_OT_NameMappingReverse,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
