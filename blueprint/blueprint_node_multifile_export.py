import bpy
from bpy.types import Node, NodeSocket
from bpy.props import StringProperty, CollectionProperty, BoolProperty, IntProperty

from ..config.main_config import GlobalConfig
from .blueprint_node_base import SSMTNodeBase


class SSMT_OT_MultiFileExport_AddObject(bpy.types.Operator):
    '''Add object to multi-file export list'''
    bl_idname = "ssmt.multifile_export_add_object"
    bl_label = "添加物体"
    bl_description = "手动添加物体到列表"
    
    node_name: bpy.props.StringProperty() # type: ignore

    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            node.add_object_to_list(node.temp_object_name)
            self.report({'INFO'}, f"已添加物体: {node.temp_object_name}")
        else:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_RemoveObject(bpy.types.Operator):
    '''Remove object from multi-file export list'''
    bl_idname = "ssmt.multifile_export_remove_object"
    bl_label = "移除物体"
    bl_description = "从列表中移除物体"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            node.remove_object_from_list(self.index)
            self.report({'INFO'}, f"已移除物体索引: {self.index}")
        else:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_ParseCollection(bpy.types.Operator):
    '''Parse collection and add all objects'''
    bl_idname = "ssmt.multifile_export_parse_collection"
    bl_label = "解析合集"
    bl_description = "解析合集中的所有物体（识别_001、_002等序列）"
    
    node_name: bpy.props.StringProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            count = node.parse_collection(node.temp_collection_name)
            self.report({'INFO'}, f"已解析合集: {node.temp_collection_name}，找到 {count} 个物体")
        else:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_MoveUp(bpy.types.Operator):
    '''Move object up in list'''
    bl_idname = "ssmt.multifile_export_move_up"
    bl_label = "上移"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.index > 0:
            node.move_object_in_list(self.index, self.index - 1)
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_MoveDown(bpy.types.Operator):
    '''Move object down in list'''
    bl_idname = "ssmt.multifile_export_move_down"
    bl_label = "下移"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.index < len(node.object_list) - 1:
            node.move_object_in_list(self.index, self.index + 1)
        
        return {'FINISHED'}


class MultiFileExportObjectItem(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty(name="物体名称", default="") # type: ignore
    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    alias_name: bpy.props.StringProperty(name="别名", default="") # type: ignore


class SSMTNode_MultiFile_Export(SSMTNodeBase):
    '''多文件导出节点：支持自动切换多个物体进行多次导出'''
    bl_idname = 'SSMTNode_MultiFile_Export'
    bl_label = '多文件导出'
    bl_icon = 'FILE_FOLDER'
    bl_width_min = 350
    
    object_list: bpy.props.CollectionProperty(type=MultiFileExportObjectItem) # type: ignore
    current_export_index: bpy.props.IntProperty(name="当前导出次数", default=1) # type: ignore
    
    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 350
    
    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="物体列表", icon='GROUP_VCOL')
        
        if len(self.object_list) == 0:
            box.label(text="列表为空，请添加物体", icon='ERROR')
        else:
            box.label(text=f"共 {len(self.object_list)} 个物体", icon='INFO')
        
        box.separator()
        
        for i, item in enumerate(self.object_list):
            row = box.row(align=True)
            
            object_label = item.object_name
            if item.object_name:
                if "-" in item.object_name:
                    parts = item.object_name.split("-")
                    if len(parts) >= 3:
                        object_label = f"{parts[0]}-{parts[1]} ({parts[2]})"
            
            row.label(text=f"{i + 1}. {object_label}", icon='OBJECT_DATA')
            
            op_up = row.operator("ssmt.multifile_export_move_up", text="", icon='TRIA_UP')
            op_up.node_name = self.name
            op_up.index = i
            
            op_down = row.operator("ssmt.multifile_export_move_down", text="", icon='TRIA_DOWN')
            op_down.node_name = self.name
            op_down.index = i
            
            op_remove = row.operator("ssmt.multifile_export_remove_object", text="", icon='X')
            op_remove.node_name = self.name
            op_remove.index = i
            
            box.separator()
        
        box.separator()
        
        row = box.row(align=True)
        
        row.prop_search(self, "temp_object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        row.operator("ssmt.multifile_export_add_object", text="添加", icon='ADD').node_name = self.name
        
        box.separator()
        
        row = box.row(align=True)
        row.prop_search(self, "temp_collection_name", bpy.data, "collections", text="", icon='GROUP')
        row.operator("ssmt.multifile_export_parse_collection", text="解析合集", icon='FILE_REFRESH').node_name = self.name
    
    def get_current_object_info(self, export_index):
        """获取当前导出次数对应的物体信息"""
        if export_index < 0 or export_index >= len(self.object_list):
            return None
        
        item = self.object_list[export_index]
        return {
            "object_name": item.object_name,
            "draw_ib": item.draw_ib,
            "component": item.component,
            "alias_name": item.alias_name
        }
    
    def add_object_to_list(self, object_name):
        """添加物体到列表"""
        if not object_name:
            return
        
        obj = bpy.data.objects.get(object_name)
        if not obj:
            return
        
        item = self.object_list.add()
        item.object_name = object_name
        
        if "-" in object_name:
            parts = object_name.split("-")
            if len(parts) >= 2:
                item.draw_ib = parts[0]
                item.component = parts[1]
                if len(parts) >= 3:
                    item.alias_name = "-".join(parts[2:])
    
    def remove_object_from_list(self, index):
        """从列表中移除物体"""
        if index >= 0 and index < len(self.object_list):
            self.object_list.remove(index)
    
    def move_object_in_list(self, from_index, to_index):
        """移动物体在列表中的位置"""
        if (from_index < 0 or from_index >= len(self.object_list) or
            to_index < 0 or to_index >= len(self.object_list)):
            return
        
        item = self.object_list[from_index]
        self.object_list.remove(from_index)
        self.object_list.move(len(self.object_list), to_index)
    
    def parse_collection(self, collection_name):
        """解析合集中的所有物体，识别序列号并按顺序添加"""
        if not collection_name:
            return 0
        
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            return 0
        
        import re
        
        objects_dict = {}
        
        for obj in collection.objects:
            if not obj.name:
                continue
            
            object_name = obj.name
            
            pattern = r'_(\d+)$'
            match = re.search(pattern, object_name)
            
            if match:
                sequence_num = int(match.group(1))
                base_name = object_name[:match.start()]
                
                if base_name not in objects_dict:
                    objects_dict[base_name] = []
                
                objects_dict[base_name].append((sequence_num, object_name))
        
        count = 0
        for base_name in sorted(objects_dict.keys()):
            objects_dict[base_name].sort(key=lambda x: x[0])
            
            for seq_num, obj_name in objects_dict[base_name]:
                self.add_object_to_list(obj_name)
                count += 1
        
        return count
    
    temp_object_name: bpy.props.StringProperty(name="临时物体名称", default="") # type: ignore
    temp_collection_name: bpy.props.StringProperty(name="临时合集名称", default="") # type: ignore


classes = (
    MultiFileExportObjectItem,
    SSMTNode_MultiFile_Export,
    SSMT_OT_MultiFileExport_AddObject,
    SSMT_OT_MultiFileExport_RemoveObject,
    SSMT_OT_MultiFileExport_ParseCollection,
    SSMT_OT_MultiFileExport_MoveUp,
    SSMT_OT_MultiFileExport_MoveDown,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
