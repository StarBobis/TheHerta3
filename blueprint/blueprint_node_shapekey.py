
import bpy

from .blueprint_node_base import SSMTNodeBase


# 形态键定义节点
class SSMTNode_ShapeKey(SSMTNodeBase):
    '''ShapeKey Node'''
    bl_idname = 'SSMTNode_ShapeKey'
    bl_label = 'Shape Key'
    bl_icon = 'SHAPEKEY_DATA'

    def update_shapekey_name(self, context):
        self.update_node_width([self.shapekey_name, self.key, self.comment])
    
    def update_key(self, context):
        self.update_node_width([self.shapekey_name, self.key, self.comment])
    
    def update_comment(self, context):
        self.update_node_width([self.shapekey_name, self.key, self.comment])
    
    shapekey_name: bpy.props.StringProperty(name="ShapeKey Name", default="", update=update_shapekey_name) # type: ignore
    key: bpy.props.StringProperty(name="Key", default="", update=update_key) # type: ignore
    comment: bpy.props.StringProperty(name="备注", description="备注信息，会以注释形式生成到配置表中", default="", update=update_comment) # type: ignore
    
    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def draw_buttons(self, context, layout):
        layout.prop(self, "shapekey_name", text="Name")
        
        row = layout.row(align=True)
        row.prop(self, "key", text="Key")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
        layout.prop(self, "comment", text="备注")


# 结果输出节点
class SSMTNode_ShapeKey_Output(SSMTNodeBase):
    '''ShapeKey Output Node'''
    bl_idname = 'SSMTNode_ShapeKey_Output'
    bl_label = 'Generate ShapeKey Buffer'
    bl_icon = 'EXPORT'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Group 1")
        self.width = 200

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Group {len(self.inputs) + 1}")
        
        # 移除中间断开的连接
        # 保留 inputs[0](至少一个Group)
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


classes = (
    SSMTNode_ShapeKey,
    SSMTNode_ShapeKey_Output,
    
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in classes:
        bpy.utils.unregister_class(cls)
