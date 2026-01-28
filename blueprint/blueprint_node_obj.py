
import bpy
from bpy.types import NodeTree, Node, NodeSocket

from ..config.main_config import GlobalConfig

from .blueprint_node_base import SSMTBlueprintTree, SSMTNodeBase


class SSMT_OT_SelectNodeObject(bpy.types.Operator):
    '''Select this object in 3D View'''
    bl_idname = "ssmt.select_node_object"
    bl_label = "Select Object"
    
    object_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        obj_name = self.object_name
        if not obj_name:
            return {'CANCELLED'}
        
        obj = bpy.data.objects.get(obj_name)
        if obj:
            # Deselect all
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except:
                pass
                
            # Select target
            obj.select_set(True)
            context.view_layer.objects.active = obj
            self.report({'INFO'}, f"Selected: {obj_name}")
        else:
            self.report({'WARNING'}, f"Object '{obj_name}' not found")
        
        return {'FINISHED'}


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
            if "-" in self.object_name:
                obj_name_split = self.object_name.split("-")
                self.draw_ib = obj_name_split[0]
                self.component = obj_name_split[1]
                self.alias_name = obj_name_split[2]
        else:
            self.label = "Object Info"
    object_name: bpy.props.StringProperty(name="Object Name", default="", update=update_object_name) # type: ignore


    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    alias_name: bpy.props.StringProperty(name="Alias Name", default="") # type: ignore

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Object")
        # self.width = 300 # 让节点宽一点

    def draw_buttons(self, context, layout):
        # 1. 物体选择：使用 prop_search 让用户可以像属性面板一样搜索选择
        # 但是 node 本身没有 PointerProperty 指向 ID 类型的简单 GUI 支持，
        # 所以通常是用 search 指向 bpy.data.objects
        
        row = layout.row(align=True)
        row.prop_search(self, "object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        
        if self.object_name:
            op = row.operator("ssmt.select_node_object", text="", icon='RESTRICT_SELECT_OFF')
            op.object_name = self.object_name

        # 2. DrawIB 和 Component 自由修改
        layout.prop(self, "draw_ib", text="DrawIB")
        layout.prop(self, "component", text="Component")
        layout.prop(self, "alias_name", text="Alias Name")


# 组合节点：用于将多个 Object Info 按顺序组合
class SSMTNode_Object_Group(SSMTNodeBase):
    '''单纯用于分组的节点，可以接受任何节点作为输入，放在一个组里'''
    bl_idname = 'SSMTNode_Object_Group'
    bl_label = 'Group'
    bl_icon = 'GROUP'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200

    def draw_buttons(self, context, layout):
        layout.operator("ssmt.view_group_objects", text="查看递归解析预览", icon='HIDE_OFF').node_name = self.name

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
    '''【按键开关】会控制所有连接到它输入端口的对象,是【按键切换】的一个特殊情况，因为常用所以单独做成了一个节点'''
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
        self.use_custom_color = True
        self.color = (0.41, 0.42, 0.66)

    def draw_buttons(self, context, layout):
        # layout.prop(self, "key_name", text="按键")
        row = layout.row(align=True)
        row.prop(self, "key_name", text="按键")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
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



class SSMT_OT_SwitchKey_AddSocket(bpy.types.Operator):
    '''Add a new socket to the switch node'''
    bl_idname = "ssmt.switch_add_socket"
    bl_label = "Add Socket"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node:
             node.inputs.new('SSMTSocketObject', f"Status {len(node.inputs)}")
        return {'FINISHED'}


class SSMT_OT_SwitchKey_RemoveSocket(bpy.types.Operator):
    '''Remove the last socket from the switch node'''
    bl_idname = "ssmt.switch_remove_socket"
    bl_label = "Remove Socket"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if node and len(node.inputs) > 0:
            node.inputs.remove(node.inputs[-1])
        return {'FINISHED'}


class SSMTNode_SwitchKey(SSMTNodeBase):
    '''【按键切换】会把每个连入的分支分配到单独的变量'''
    bl_idname = 'SSMTNode_SwitchKey'
    bl_label = 'Switch Key'
    bl_icon = 'GROUP'

    key_name: bpy.props.StringProperty(name="Key Name", default="") # type: ignore

    def init(self, context):
        self.label = "按键切换"
        self.inputs.new('SSMTSocketObject', "Status 0")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200
        self.use_custom_color = True
        self.color = (0.34, 0.54, 0.34)

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "key_name", text="按键")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
        row = layout.row(align=True)
        op_add = row.operator("ssmt.switch_add_socket", text="Add", icon='ADD')
        op_add.node_name = self.name
        
        op_rem = row.operator("ssmt.switch_remove_socket", text="Remove", icon='REMOVE')
        op_rem.node_name = self.name


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



class SSMT_OT_View_Group_Objects(bpy.types.Operator):
    '''递归解析当前组下面所有的物体并放到一个新的窗口中展示，注意组节点最好不要包含按键切换，否则会同时展示所有切换分支内容'''
    bl_idname = "ssmt.view_group_objects"
    bl_label = "View Group Objects"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or context.space_data.node_tree
        if not tree:
             return {'CANCELLED'}
        node = tree.nodes.get(self.node_name)
        if not node:
             return {'CANCELLED'}

        objects_to_show = set()
        checked_nodes = set()

        def collect_objects(current_node):
            if current_node in checked_nodes: return
            checked_nodes.add(current_node)

            if getattr(current_node, "bl_idname", "") == 'SSMTNode_Object_Info':
                obj_name = getattr(current_node, "object_name", "")
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        objects_to_show.add(obj)

            if hasattr(current_node, "inputs"):
                for inp in current_node.inputs:
                    if inp.is_linked:
                        for link in inp.links:
                            collect_objects(link.from_node)

        collect_objects(node)
        
        if not objects_to_show:
            self.report({'WARNING'}, "No objects found in this group")
            return {'CANCELLED'}

        # Ensure Object Mode
        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        # Deselect all
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects_to_show:
            obj.select_set(True)

        # Open new window
        bpy.ops.wm.window_new()
        new_window = context.window_manager.windows[-1]

        # Use the first area of the new window and convert it to 3D View
        if new_window.screen and new_window.screen.areas:
            area = new_window.screen.areas[0]
            area.type = 'VIEW_3D'
            area.ui_type = 'VIEW_3D'
            
            # Find the WINDOW region for proper context
            region = next((r for r in area.regions if r.type == 'WINDOW'), None)
            
            if region:
                with context.temp_override(window=new_window, area=area, region=region):
                    # Enter Local View to isolate selected objects
                    try:
                        if area.spaces.active.region_3d.is_perspective:
                            bpy.ops.view3d.view_persportho() # Switch to Orthographic
                        
                        bpy.ops.view3d.localview() 
                        bpy.ops.view3d.view_axis(type='FRONT')
                        bpy.ops.view3d.view_selected()
                        
                        # Optional: Set shading to Solid or Material
                        if area.spaces.active:
                            area.spaces.active.shading.type = 'SOLID'
                    except Exception as e:
                        print(f"View setup warning: {e}")

        return {'FINISHED'}



classes = (
    SSMT_OT_SelectNodeObject,
    SSMT_OT_View_Group_Objects,
    SSMTNode_Object_Info,
    SSMTNode_Object_Group,
    SSMTNode_Result_Output,
    SSMTNode_ToggleKey,
    SSMTNode_SwitchKey,
    SSMT_OT_SwitchKey_AddSocket,
    SSMT_OT_SwitchKey_RemoveSocket,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():

    for cls in classes:
        bpy.utils.unregister_class(cls)



