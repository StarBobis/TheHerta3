import bpy
from bpy.types import Node, NodeSocket
from bpy.props import StringProperty, EnumProperty, PointerProperty

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

    blueprint_name: bpy.props.StringProperty(
        name="Blueprint Name",
        description="选择要嵌套的蓝图",
        default="",
        update=update_blueprint_name
    )

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop_search(self, "blueprint_name", bpy.data, "node_groups", text="", icon='NODETREE')
        
        op = row.operator("ssmt.create_blueprint_from_nest", text="", icon='ADD')
        op.node_name = self.name
        
        if self.blueprint_name and self.blueprint_name != 'NONE':
            blueprint = bpy.data.node_groups.get(self.blueprint_name)
            if blueprint and blueprint.bl_idname == 'SSMTBlueprintTreeType':
                box = layout.box()
                box.label(text=f"节点数: {len(blueprint.nodes)}", icon='NODE')
                box.label(text=f"连接数: {len(blueprint.links)}", icon='LINKED')
                
                output_nodes = [n for n in blueprint.nodes if n.bl_idname == 'SSMTNode_Result_Output']
                if output_nodes:
                    box.label(text=f"输出节点: {len(output_nodes)}", icon='FILE_TICK')
                else:
                    box.label(text="警告: 无输出节点", icon='ERROR')
                
                box.separator()
                row = box.row(align=True)
                row.operator("ssmt.blueprint_nest_navigate", text="进入嵌套蓝图", icon='FORWARD')
            elif blueprint:
                layout.label(text="警告: 选中的不是SSMT蓝图", icon='ERROR')
            else:
                layout.label(text="警告: 蓝图不存在", icon='ERROR')
