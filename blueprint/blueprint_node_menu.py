
import bpy
from bpy.types import NodeTree, Node, NodeSocket

from ..config.main_config import GlobalConfig

from .blueprint_node_base import SSMTBlueprintTree, SSMTNodeBase


class SSMT_OT_CreateGroupFromSelection(bpy.types.Operator):
    '''Create nodes from selected objects and group them under a new Group node'''
    bl_idname = "ssmt.create_group_from_selection"
    bl_label = "将所选物体新建到组节点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "没有选择任何物体")
            return {'CANCELLED'}

        # 获取或创建与当前 Workspace 同名的 SSMT Blueprint 节点树
        workspace_name = "Mod_" + GlobalConfig.workspacename
        node_tree = bpy.data.node_groups.get(workspace_name)
        
        if not node_tree or node_tree.bl_idname != 'SSMTBlueprintTreeType':
            node_tree = bpy.data.node_groups.new(name=workspace_name, type='SSMTBlueprintTreeType')

        # 切换到节点编辑器并设置该节点树（可选，视需求而定，这里主要负责创建节点）
        # 如果需要跳转可以使用 context.area.type etc. 但在 3D View 操作不一定需要跳转

        # 计算节点位置偏移，防止重叠
        # 简单策略：找到当前最右侧/最下方的节点，或者直接在原点附近偏移
        # 这里使用一个简单的网格布局
        
        # 查找一个放置基准点
        base_x = 0
        base_y = 0
        if node_tree.nodes:
             # 如果已有节点，往右下角找个空地，或者直接往右
             pass

        # 创建 Group 节点
        group_node = node_tree.nodes.new(type='SSMTNode_Object_Group')
        group_node.location = (base_x + 400, base_y)
        
        # 创建 Object Nodes 并连接
        for i, obj in enumerate(selected_objects):
            obj_node = node_tree.nodes.new(type='SSMTNode_Object_Info')
            obj_node.location = (base_x, base_y - i * 150)
            
            # 设置物体
            obj_node.object_name = obj.name
            # 手动触发 update 如果需要，但属性设置通常会自动 update 
            # (注意: 这里 update_object_name 是 property update callback)
            
            # 连接到 group_node
            # Group Node 会自动根据连接增加 input socket (在 update() 中)
            # 但首次连接时可能只有一个 input, 连接后 update 会增加新的
            
            # 获取当前可用的 input
            # 因为 SSMTNode_Object_Group.update() 逻辑是：如果有连接到 inputs[-1]，则 new socket remove...
            # 所以我们需要确保连接
            
            # 找到第一个未连接的 input，或者最后一个
            target_socket = None
            if len(group_node.inputs) > 0:
                 target_socket = group_node.inputs[-1]
            
            if target_socket:
                node_tree.links.new(obj_node.outputs[0], target_socket)
                # 强制更新一下 group node 以生成新的插槽，以便下一个物体连接
                group_node.update()

        return {'FINISHED'}


def draw_objects_context_menu_add(self, context):
    layout = self.layout
    layout.separator()
    layout.menu("SSMT_MT_ObjectContextMenuSub", text="SSMT蓝图架构", icon='NODETREE')

class SSMT_MT_ObjectContextMenuSub(bpy.types.Menu):
    bl_label = "SSMT蓝图架构"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("ssmt.create_group_from_selection", text="将所选物体新建到组节点", icon='GROUP')


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



def register():
    bpy.utils.register_class(SSMT_OT_CreateGroupFromSelection)
    bpy.utils.register_class(SSMT_MT_ObjectContextMenuSub)

    bpy.types.NODE_MT_add.prepend(draw_node_add_menu)
    # 添加到 3D 视图物体右键菜单
    bpy.types.VIEW3D_MT_object_context_menu.append(draw_objects_context_menu_add)

def unregister():
    bpy.types.NODE_MT_add.remove(draw_node_add_menu)
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_objects_context_menu_add)

    bpy.utils.unregister_class(SSMT_MT_ObjectContextMenuSub)
    bpy.utils.unregister_class(SSMT_OT_CreateGroupFromSelection)
