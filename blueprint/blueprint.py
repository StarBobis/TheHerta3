
import bpy
from bpy.types import NodeTree, Node, NodeSocket
import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem

# Custom Socket Types
class SSMTSocketFlow(NodeSocket):
    '''Custom Socket for Execution Flow'''
    bl_idname = 'SSMTSocketFlow'
    bl_label = 'Flow Socket'

    def draw_color(self, context, node):
        return (0.9, 0.9, 0.9, 1.0) # White

    def draw(self, context, layout, node, text):
        layout.label(text=text)

class SSMTSocketObject(NodeSocket):
    '''Custom Socket for Object Data'''
    bl_idname = 'SSMTSocketObject'
    bl_label = 'Object Socket'

    def draw_color(self, context, node):
        return (0.0, 0.8, 0.8, 1.0) # Cyan/Teal

    def draw(self, context, layout, node, text):
        layout.label(text=text)

# 1. 定义自定义节点树类型
class SSMTBlueprintTree(NodeTree):
    '''SSMT Mod Logic Blueprint'''
    bl_idname = 'SSMTBlueprintTreeType'
    bl_label = 'SSMT BluePrint'
    bl_icon = 'NODETREE'

# 2. 定义基础节点
class SSMTNodeBase(Node):
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'SSMTBlueprintTreeType'

# 示例节点：开始节点
class SSMTNode_Event_Start(SSMTNodeBase):
    '''SSMT Start Node'''
    bl_idname = 'SSMTNode_Event_Start'
    bl_label = 'Event: Mod Generation'
    bl_icon = 'PLAY'

    def init(self, context):
        self.outputs.new('SSMTSocketFlow', "Next")

# 示例节点：打印日志节点
class SSMTNode_Action_Print(SSMTNodeBase):
    '''Print Log'''
    bl_idname = 'SSMTNode_Action_Print'
    bl_label = 'Print Log'
    bl_icon = 'INFO'

    def init(self, context):
        self.inputs.new('SSMTSocketFlow', "Prev")
        self.inputs.new('NodeSocketString', "Message").default_value = "Hello World"
        self.outputs.new('SSMTSocketFlow', "Next")

# 对象信息节点
class SSMTNode_Object_Info(SSMTNodeBase):
    '''Object Info Node'''
    bl_idname = 'SSMTNode_Object_Info'
    bl_label = 'Object Info'
    bl_icon = 'OBJECT_DATAMODE'
    
    # 定义属性用于存储信息
    # 使用 props.PointerProperty 指向 Object 可能会有上下文问题（特别是跨文件保存时），
    # 但在 Runtime UI 中通常结合 prop_search 使用 StringProperty 来模拟体验。
    # 为了更好的体验，我们使用 StringProperty 并配合 prop_search 绘制。
    
    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    object_name: bpy.props.StringProperty(name="Object Name", default="") # type: ignore

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Object")
        self.width = 220 # 让节点宽一点

    def draw_buttons(self, context, layout):
        # 1. 物体选择：使用 prop_search 让用户可以像属性面板一样搜索选择
        # 但是 node 本身没有 PointerProperty 指向 ID 类型的简单 GUI 支持，
        # 所以通常是用 search 指向 bpy.data.objects
        layout.prop_search(self, "object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        
        # 2. DrawIB 和 Component 自由修改
        layout.prop(self, "draw_ib", text="DrawIB")
        layout.prop(self, "component", text="Component")
        
        # 自动根据选择的物体更新 Label (可选)
        if self.object_name:
            self.label = self.object_name

# 结果输出节点
class SSMTNode_Result_Output(SSMTNodeBase):
    '''Result Output Node'''
    bl_idname = 'SSMTNode_Result_Output'
    bl_label = 'Mod Output'
    bl_icon = 'EXPORT'

    def init(self, context):
        self.inputs.new('SSMTSocketFlow', "Prev")
        self.inputs.new('SSMTSocketObject', "Object")

# 3. 注册列表
classes = (
    SSMTSocketFlow,
    SSMTSocketObject,
    SSMTBlueprintTree,
    SSMTNode_Event_Start,
    SSMTNode_Action_Print,
    SSMTNode_Object_Info,
    SSMTNode_Result_Output
)

# 4. 节点分类菜单配置
class SSMTNodeCategory(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'SSMTBlueprintTreeType'

node_categories = [
    SSMTNodeCategory("SSMT_EVENTS", "Events", items=[
        NodeItem("SSMTNode_Event_Start"),
    ]),
    SSMTNodeCategory("SSMT_ACTIONS", "Actions", items=[
        NodeItem("SSMTNode_Action_Print"),
    ]),
    SSMTNodeCategory("SSMT_DATA", "Data", items=[
        NodeItem("SSMTNode_Object_Info"),
    ]),
    SSMTNodeCategory("SSMT_OUTPUTS", "Outputs", items=[
        NodeItem("SSMTNode_Result_Output"),
    ]),
]

def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass # Already registered
    
    try:
        nodeitems_utils.register_node_categories('SSMT_NODES', node_categories)
    except:
        pass

def unregister():
    try:
        nodeitems_utils.unregister_node_categories('SSMT_NODES')
    except:
        pass

    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass


