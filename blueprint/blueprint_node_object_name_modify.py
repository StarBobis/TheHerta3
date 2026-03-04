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
    '''物体名称修改节点 - 基于映射表修改物体名称，支持多个映射关系'''
    bl_idname = 'SSMTNode_Object_Name_Modify'
    bl_label = 'Object Name Modify'
    bl_icon = 'SORTALPHA'
    bl_width_min = 400
    
    mapping_list: bpy.props.CollectionProperty(type=NameMappingItem)
    active_mapping_index: bpy.props.IntProperty(default=0)
    
    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Object Input")
        self.outputs.new('SSMTSocketObject', "Object Output")
        self.width = 400
    
    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="名称映射表:", icon='SORTALPHA')
        
        row = box.row()
        row.template_list("SSMT_UL_NameMapping", "", self, "mapping_list", self, "active_mapping_index", rows=3)
        
        col = row.column(align=True)
        col.operator("ssmt.name_mapping_add", icon='ADD', text="")
        col.operator("ssmt.name_mapping_remove", icon='REMOVE', text="")
    
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
            if item.original_name and item.original_name in modified_name:
                old_name = modified_name
                modified_name = modified_name.replace(item.original_name, item.new_name)
                print(f"[NameModify] 物体 {original_name}: '{item.original_name}' -> '{item.new_name}'")
                print(f"[NameModify] 中间结果: {old_name} -> {modified_name}")
        
        return modified_name
    
    def is_valid(self):
        return len(self.mapping_list) > 0 and any(item.original_name for item in self.mapping_list)
    
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


classes = (
    NameMappingItem,
    SSMT_UL_NameMapping,
    SSMTNode_Object_Name_Modify,
    SSMT_OT_NameMappingAdd,
    SSMT_OT_NameMappingRemove,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
