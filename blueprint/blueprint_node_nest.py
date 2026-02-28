import bpy
from bpy.types import Node, NodeSocket
from bpy.props import StringProperty, EnumProperty

from .blueprint_node_base import SSMTNodeBase


class SSMTNode_Blueprint_Nest(SSMTNodeBase):
    '''Blueprint Nest Node - 嵌套外部蓝图到当前蓝图'''
    bl_idname = 'SSMTNode_Blueprint_Nest'
    bl_label = 'Blueprint Nest'
    bl_icon = 'NODETREE'
    bl_width_min = 300

    def update_blueprint_name(self, context):
        if self.blueprint_name and self.blueprint_name != 'NONE':
            self.label = f"嵌套: {self.blueprint_name}"
        else:
            self.label = "Blueprint Nest"
        self.update_node_width([self.blueprint_name])

    def get_available_blueprints(self, context):
        """获取所有可用的蓝图树列表"""
        items = [('NONE', '无', '不嵌套任何蓝图')]
        for node_group in bpy.data.node_groups:
            if node_group.bl_idname == 'SSMTBlueprintTreeType':
                items.append((node_group.name, node_group.name, f"嵌套蓝图: {node_group.name}"))
        return items

    blueprint_name: bpy.props.EnumProperty(
        name="Blueprint Name",
        description="选择要嵌套的蓝图",
        items=get_available_blueprints,
        update=update_blueprint_name
    )

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "blueprint_name", text="", icon='NODETREE')
        
        # 创建新蓝图按钮
        op = row.operator("ssmt.create_blueprint_from_nest", text="", icon='ADD')
        op.node_name = self.name
        
        if self.blueprint_name and self.blueprint_name != 'NONE':
            blueprint = bpy.data.node_groups.get(self.blueprint_name)
            if blueprint:
                # 显示嵌套蓝图的基本信息
                box = layout.box()
                box.label(text=f"节点数: {len(blueprint.nodes)}", icon='NODE')
                box.label(text=f"连接数: {len(blueprint.links)}", icon='LINKED')
                
                # 检查是否存在输出节点
                output_nodes = [n for n in blueprint.nodes if n.bl_idname == 'SSMTNode_Result_Output']
                if output_nodes:
                    box.label(text=f"输出节点: {len(output_nodes)}", icon='FILE_TICK')
                else:
                    box.label(text="警告: 无输出节点", icon='ERROR')
                
                # 添加导航按钮
                box.separator()
                row = box.row(align=True)
                row.operator("ssmt.blueprint_nest_navigate", text="进入嵌套蓝图", icon='FORWARD')


def register():
    bpy.utils.register_class(SSMTNode_Blueprint_Nest)


def unregister():
    bpy.utils.unregister_class(SSMTNode_Blueprint_Nest)
