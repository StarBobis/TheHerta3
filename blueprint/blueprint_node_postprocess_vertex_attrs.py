import bpy
from bpy.types import PropertyGroup

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class VertexAttributeItem(bpy.types.PropertyGroup):
    attr_type: bpy.props.EnumProperty(
        name="数据类型",
        description="顶点属性的数据类型",
        items=[
            ('float', 'float', '单精度浮点数 (4字节)'),
            ('float2', 'float2', '2个浮点数 (8字节)'),
            ('float3', 'float3', '3个浮点数 (12字节)'),
            ('float4', 'float4', '4个浮点数 (16字节)'),
            ('int', 'int', '整数 (4字节)'),
            ('int2', 'int2', '2个整数 (8字节)'),
            ('int3', 'int3', '3个整数 (12字节)'),
            ('int4', 'int4', '4个整数 (16字节)'),
            ('uint', 'uint', '无符号整数 (4字节)'),
            ('uint2', 'uint2', '2个无符号整数 (8字节)'),
            ('uint3', 'uint3', '3个无符号整数 (12字节)'),
            ('uint4', 'uint4', '4个无符号整数 (16字节)'),
            ('half', 'half', '半精度浮点数 (2字节)'),
            ('half2', 'half2', '2个半精度浮点数 (4字节)'),
            ('half3', 'half3', '3个半精度浮点数 (6字节)'),
            ('half4', 'half4', '4个半精度浮点数 (8字节)'),
            ('double', 'double', '双精度浮点数 (8字节)'),
            ('double2', 'double2', '2个双精度浮点数 (16字节)'),
            ('double3', 'double3', '3个双精度浮点数 (24字节)'),
            ('double4', 'double4', '4个双精度浮点数 (32字节)'),
        ],
        default='float3'
    )
    attr_name: bpy.props.StringProperty(name="属性名称", description="顶点属性的名称", default="position", maxlen=256)


class SSMTNode_PostProcess_VertexAttrs(SSMTNode_PostProcess_Base):
    '''顶点属性定义节点：为形态键配置和多文件配置提供顶点属性定义'''
    bl_idname = 'SSMTNode_PostProcess_VertexAttrs'
    bl_label = '顶点属性定义'
    bl_description = '为形态键配置和多文件配置提供顶点属性定义'

    vertex_attributes: bpy.props.CollectionProperty(type=VertexAttributeItem)
    active_vertex_attribute: bpy.props.IntProperty(default=0)

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="顶点属性定义", icon='PROPERTIES')
        box.template_list("SSMT_UL_VERTEX_ATTRIBUTES", "", self, "vertex_attributes", self, "active_vertex_attribute", rows=3)
        
        row = box.row()
        row.operator("ssmt_postprocess.add_vertex_attribute", icon='ADD', text="")
        row.operator("ssmt_postprocess.remove_vertex_attribute", icon='REMOVE', text="")
        
        if self.vertex_attributes and self.active_vertex_attribute >= 0 and self.active_vertex_attribute < len(self.vertex_attributes):
            item = self.vertex_attributes[self.active_vertex_attribute]
            row = box.row()
            row.prop(item, "attr_type")
            row = box.row()
            row.prop(item, "attr_name")

    def get_vertex_struct_definition(self):
        """获取顶点属性结构体定义字符串"""
        if not self.vertex_attributes or len(self.vertex_attributes) == 0:
            return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"
        
        struct_lines = ["struct VertexAttributes {"]
        for item in self.vertex_attributes:
            if item.attr_type and item.attr_name:
                struct_lines.append(f"    {item.attr_type} {item.attr_name};")
        struct_lines.append("};")
        
        return "\n".join(struct_lines)

    def get_shader_struct_definition(self):
        """获取着色器结构体定义代码"""
        if not self.vertex_attributes or len(self.vertex_attributes) == 0:
            return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"
        
        struct_lines = ["struct VertexAttributes {"]
        for item in self.vertex_attributes:
            if item.attr_type and item.attr_name:
                struct_lines.append(f"    {item.attr_type} {item.attr_name};")
        struct_lines.append("};")
        
        return "\n".join(struct_lines)

    def parse_vertex_struct(self):
        """解析顶点属性结构体定义，计算总字节数和float数量"""
        struct_definition = self.get_vertex_struct_definition()
        
        if not struct_definition or not struct_definition.strip():
            return None
        
        TYPE_SIZES = {
            'float': 4,
            'float2': 8,
            'float3': 12,
            'float4': 16,
            'int': 4,
            'int2': 8,
            'int3': 12,
            'int4': 16,
            'uint': 4,
            'uint2': 8,
            'uint3': 12,
            'uint4': 16,
            'half': 2,
            'half2': 4,
            'half3': 6,
            'half4': 8,
            'double': 8,
            'double2': 16,
            'double3': 24,
            'double4': 32,
        }
        
        total_bytes = 0
        total_floats = 0
        attributes = []
        
        lines = struct_definition.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                continue
            
            line = line.rstrip(';').strip()
            
            parts = line.split()
            if len(parts) >= 2:
                type_name = parts[0]
                var_name = parts[1].rstrip(';')
                
                if type_name in TYPE_SIZES:
                    byte_size = TYPE_SIZES[type_name]
                    total_bytes += byte_size
                    total_floats += byte_size // 4
                    attributes.append({'type': type_name, 'name': var_name, 'size': byte_size})
        
        if total_bytes == 0:
            return None
        
        return (total_bytes, total_floats, attributes)

    def execute_postprocess(self, mod_export_path):
        """顶点属性定义节点不执行任何操作，只是提供配置信息"""
        print(f"顶点属性定义节点已配置，Mod导出路径: {mod_export_path}")


class SSMT_UL_VERTEX_ATTRIBUTES(bpy.types.UIList):
    bl_idname = 'SSMT_UL_VERTEX_ATTRIBUTES'
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            row.label(text=f"{item.attr_type} {item.attr_name}")
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text=f"{item.attr_type} {item.attr_name}")


class SSMT_OT_PostProcess_AddVertexAttribute(bpy.types.Operator):
    bl_idname = "ssmt_postprocess.add_vertex_attribute"
    bl_label = "添加顶点属性"
    bl_description = "添加新的顶点属性项"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}
        
        new_item = node.vertex_attributes.add()
        
        if len(node.vertex_attributes) == 1:
            new_item.attr_name = "position"
        elif len(node.vertex_attributes) == 2:
            new_item.attr_name = "normal"
        elif len(node.vertex_attributes) == 3:
            new_item.attr_name = "tangent"
        else:
            new_item.attr_name = f"attr{len(node.vertex_attributes)}"
            
        node.active_vertex_attribute = len(node.vertex_attributes) - 1
        return {'FINISHED'}


class SSMT_OT_PostProcess_RemoveVertexAttribute(bpy.types.Operator):
    bl_idname = "ssmt_postprocess.remove_vertex_attribute"
    bl_label = "删除顶点属性"
    bl_description = "删除选中的顶点属性项"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        node = context.active_node
        if not node or node.bl_idname != 'SSMTNode_PostProcess_VertexAttrs':
            self.report({'ERROR'}, "请先选择顶点属性定义节点")
            return {'CANCELLED'}
        
        if node.active_vertex_attribute >= 0 and node.active_vertex_attribute < len(node.vertex_attributes):
            node.vertex_attributes.remove(node.active_vertex_attribute)
            if node.active_vertex_attribute >= len(node.vertex_attributes) and node.active_vertex_attribute > 0:
                node.active_vertex_attribute -= 1
        return {'FINISHED'}


classes = (
    VertexAttributeItem,
    SSMTNode_PostProcess_VertexAttrs,
    SSMT_UL_VERTEX_ATTRIBUTES,
    SSMT_OT_PostProcess_AddVertexAttribute,
    SSMT_OT_PostProcess_RemoveVertexAttribute,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
