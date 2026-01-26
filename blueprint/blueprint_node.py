
import bpy
from bpy.types import NodeTree, Node, NodeSocket

# Custom Socket Types
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


# 对象信息节点
class SSMTNode_Object_Info(SSMTNodeBase):
    '''Object Info Node'''
    bl_idname = 'SSMTNode_Object_Info'
    bl_label = 'Object Info'
    bl_icon = 'OBJECT_DATAMODE'
    bl_width_min = 300
    
    # 定义属性用于存储信息
    # 使用 props.PointerProperty 指向 Object 可能会有上下文问题（特别是跨文件保存时），
    # 但在 Runtime UI 中通常结合 prop_search 使用 StringProperty 来模拟体验。
    # 为了更好的体验，我们使用 StringProperty 并配合 prop_search 绘制。
    
    def update_object_name(self, context):
        if self.object_name:
            self.label = self.object_name
        else:
            self.label = "Object Info"

    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    object_name: bpy.props.StringProperty(name="Object Name", default="", update=update_object_name) # type: ignore

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Object")
        # self.width = 300 # 让节点宽一点

    def draw_buttons(self, context, layout):
        # 1. 物体选择：使用 prop_search 让用户可以像属性面板一样搜索选择
        # 但是 node 本身没有 PointerProperty 指向 ID 类型的简单 GUI 支持，
        # 所以通常是用 search 指向 bpy.data.objects
        layout.prop_search(self, "object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        
        # 2. DrawIB 和 Component 自由修改
        layout.prop(self, "draw_ib", text="DrawIB")
        layout.prop(self, "component", text="Component")

# 组合节点：用于将多个 Object Info 按顺序组合
class SSMTNode_Object_Group(SSMTNodeBase):
    '''Merge multiple objects in order'''
    bl_idname = 'SSMTNode_Object_Group'
    bl_label = 'Group'
    bl_icon = 'GROUP'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        # 移除中间断开的连接，或者整理列表（可选）
        # 这里实现一个简单的逻辑：如果倒数第二个也没有连接，就移除最后一个
        # 防止无限增长，或者用户断开最后一个连接的情况
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


class SSMTNode_ToggleKey(SSMTNodeBase):
    '''【按键开关】会控制所有连接到它输入端口的对象'''
    bl_idname = 'SSMTNode_ToggleKey'
    bl_label = 'Toggle Key'
    bl_icon = 'GROUP'

    key_name: bpy.props.StringProperty(name="Key Name", default="") # type: ignore
    default_on: bpy.props.BoolProperty(name="Default On", default=False) # type: ignore

    def init(self, context):
        self.label = "按键开关"
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def draw_buttons(self, context, layout):
        layout.prop(self, "key_name", text="按键")
        layout.prop(self, "default_on", text="默认开启")

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        # 移除中间断开的连接，或者整理列表（可选）
        # 这里实现一个简单的逻辑：如果倒数第二个也没有连接，就移除最后一个
        # 防止无限增长，或者用户断开最后一个连接的情况
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


class SSMTNode_SwitchKey(SSMTNodeBase):
    '''【按键切换】会把每个连入的分支分配到单独的变量'''
    bl_idname = 'SSMTNode_SwitchKey'
    bl_label = 'Switch Key'
    bl_icon = 'GROUP'

    key_name: bpy.props.StringProperty(name="Key Name", default="") # type: ignore

    def init(self, context):
        self.label = "按键切换"
        self.inputs.new('SSMTSocketObject', "分支 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def draw_buttons(self, context, layout):
        layout.prop(self, "key_name", text="按键")

    def update(self):
        # 类似 Join Geometry 的逻辑：总保持最后一个为空，方便连接新的
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"分支 {len(self.inputs) + 1}")
        
        # 移除中间断开的连接，或者整理列表（可选）
        # 这里实现一个简单的逻辑：如果倒数第二个也没有连接，就移除最后一个
        # 防止无限增长，或者用户断开最后一个连接的情况
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


# 结果输出节点
class SSMTNode_Result_Output(SSMTNodeBase):
    '''Result Output Node'''
    bl_idname = 'SSMTNode_Result_Output'
    bl_label = 'Generate Mod'
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

# 3. 注册列表
classes = (
    SSMTSocketObject,
    SSMTBlueprintTree,
    SSMTNode_Object_Info,
    SSMTNode_Object_Group,
    SSMTNode_Result_Output,
    SSMTNode_ToggleKey,
    SSMTNode_SwitchKey,
)

def draw_node_add_menu(self, context):
    if not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return
    if context.space_data.tree_type != 'SSMTBlueprintTreeType':
        return
    
    layout = self.layout
    layout.operator("node.add_node", text="Object Info", icon='OBJECT_DATAMODE').type = "SSMTNode_Object_Info"
    layout.operator("node.add_node", text="Group", icon='GROUP').type = "SSMTNode_Object_Group"
    layout.operator("node.add_node", text="Mod Output", icon='EXPORT').type = "SSMTNode_Result_Output"
    layout.operator("node.add_node", text="Toggle Key", icon='GROUP').type = "SSMTNode_ToggleKey"
    layout.operator("node.add_node", text="Switch Key", icon='GROUP').type = "SSMTNode_SwitchKey"
    layout.separator()

    # Frame节点没有任何功能，它是Blender自带的一种辅助节点，用于在节点编辑器中组织和分组节点
    # 反正就当一个区域划分来用就行了
    layout.operator("node.add_node", text="Frame", icon='FILE_PARENT').type = "NodeFrame"
    layout.separator()

# 注册与注销函数，在大型Blender插件开发中，不能在最外面的__init__.py中直接注册
# 否则会导致__init__.py过于臃肿，不利于维护，所以在各自的模块中定义register和unregister函数
def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            pass # Already registered
        
    bpy.types.NODE_MT_add.prepend(draw_node_add_menu)

def unregister():
    bpy.types.NODE_MT_add.remove(draw_node_add_menu)

    for cls in classes:
        try:
            bpy.utils.unregister_class(cls)
        except ValueError:
            pass


