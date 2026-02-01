
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


class SSMT_MT_NodeMenu_Branch(bpy.types.Menu):
    bl_label = "分支"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("node.add_node", text="Object Info", icon='OBJECT_DATAMODE').type = "SSMTNode_Object_Info"
        layout.operator("node.add_node", text="Group", icon='GROUP').type = "SSMTNode_Object_Group"
        layout.operator("node.add_node", text="Mod Output", icon='EXPORT').type = "SSMTNode_Result_Output"
        layout.operator("node.add_node", text="Toggle Key", icon='GROUP').type = "SSMTNode_ToggleKey"
        layout.operator("node.add_node", text="Switch Key", icon='GROUP').type = "SSMTNode_SwitchKey"

class SSMT_MT_NodeMenu_ShapeKey(bpy.types.Menu):
    bl_label = "形态键"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("node.add_node", text="Shape Key", icon='SHAPEKEY_DATA').type = "SSMTNode_ShapeKey"
        layout.operator("node.add_node", text="Generate ShapeKey Buffer", icon='EXPORT').type = "SSMTNode_ShapeKey_Output"


class SSMT_OT_AddCommonKeySwitches(bpy.types.Operator):
    '''Add 9 Toggle Key nodes (CTRL 1-9), group them and connect to Output'''
    bl_idname = "ssmt.add_common_key_switches"
    bl_label = "常用按键开关"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 1. Get/Create Node Tree
        workspace_name = "Mod_" + GlobalConfig.workspacename
        node_tree = bpy.data.node_groups.get(workspace_name)
        if not node_tree or node_tree.bl_idname != 'SSMTBlueprintTreeType':
            node_tree = bpy.data.node_groups.new(name=workspace_name, type='SSMTBlueprintTreeType')

        # 2. Add Nodes
        nodes = node_tree.nodes
        links = node_tree.links
        
        # Base location
        base_x, base_y = 0, 0
        
        # Create Frame Node
        frame_node = nodes.new(type='NodeFrame')
        frame_node.label = "常用按键开关组"
        frame_node.location = (base_x - 50, base_y + 100)

        # Create Group Node
        group_node = nodes.new(type='SSMTNode_Object_Group')
        group_node.location = (base_x + 300, base_y)
        group_node.parent = frame_node
        
        # Create or Find Output Node
        output_node = None
        for node in nodes:
            if node.bl_idname == 'SSMTNode_Result_Output':
                output_node = node
                break
        
        if not output_node:
            output_node = nodes.new(type='SSMTNode_Result_Output')
            output_node.location = (base_x + 600, base_y)
        else:
            # If finding existing one, maybe move it if it's far? No, keep it.
            pass

        # Connect Group -> Output
        if output_node.inputs:
            target_socket = output_node.inputs[-1]
            links.new(group_node.outputs[0], target_socket)
            if hasattr(output_node, "update"):
                output_node.update()

        # Create 9 Keys
        key_names = [f"CTRL {i}" for i in range(1, 10)]
        
        for i, key_name in enumerate(key_names):
            key_node = nodes.new(type='SSMTNode_ToggleKey')
            key_node.location = (base_x, base_y - i * 200)
            key_node.key_name = key_name
            key_node.default_on = True
            key_node.parent = frame_node
            # key_node.label = key_name # Optional: override label? No need.
            
            # Connect Key -> Group
            if group_node.inputs:
                target_socket = group_node.inputs[-1]
                links.new(key_node.outputs[0], target_socket)
                if hasattr(group_node, "update"):
                    group_node.update()

        return {'FINISHED'}


class SSMT_OT_BatchConnectNodes(bpy.types.Operator):
    '''批量连接选中的节点：支持一对一或多对一连接'''
    bl_idname = "ssmt.batch_connect_nodes"
    bl_label = "批量连接节点"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        # 获取当前节点树
        space_data = getattr(context, "space_data", None)
        if not space_data or space_data.type != 'NODE_EDITOR':
            self.report({'ERROR'}, "请在节点编辑器中使用此功能")
            return {'CANCELLED'}

        node_tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
        if not node_tree:
            self.report({'ERROR'}, "未找到节点树")
            return {'CANCELLED'}

        # 获取选中的节点
        selected_nodes = [node for node in node_tree.nodes if node.select]
        if len(selected_nodes) < 2:
            self.report({'WARNING'}, "请至少选择2个节点")
            return {'CANCELLED'}

        # 统计节点类型分布
        type_count_dict = {}
        for node in selected_nodes:
            node_type = node.bl_idname
            type_count_dict[node_type] = type_count_dict.get(node_type, 0) + 1

        # 检查节点类型数量
        if len(type_count_dict) > 2:
            self.report({'ERROR'}, f"所选节点类型过多（{len(type_count_dict)}种），请选择1-2种类型的节点")
            return {'CANCELLED'}

        # 判断连接模式
        if len(type_count_dict) == 1:
            # 只有一种类型：无法连接
            self.report({'ERROR'}, "所选节点类型相同，无法连接")
            return {'CANCELLED'}
        else:
            # 两种类型：判断是一对一还是多对一
            type_items = list(type_count_dict.items())
            type_items.sort(key=lambda x: x[1], reverse=True)  # 按数量降序排序
            
            majority_type, majority_count = type_items[0]
            minority_type, minority_count = type_items[1]

            if majority_count == minority_count:
                # 数量相等：一对一连接
                return self.connect_one_to_one(selected_nodes, type_count_dict, node_tree)
            else:
                # 数量不等：多对一连接
                return self.connect_many_to_one(selected_nodes, type_count_dict, node_tree)

    def connect_one_to_one(self, selected_nodes, type_count_dict, node_tree):
        """一对一连接模式"""
        # 获取两种类型
        type_items = list(type_count_dict.items())
        type_a, count_a = type_items[0]
        type_b, count_b = type_items[1]

        # 按类型分组
        nodes_a = [node for node in selected_nodes if node.bl_idname == type_a]
        nodes_b = [node for node in selected_nodes if node.bl_idname == type_b]

        # 判断哪个是源节点（有输出端口），哪个是目标节点（有输入端口）
        if len(nodes_a[0].outputs) > 0 and len(nodes_a[0].inputs) > 0:
            # 类型A既有输入又有输出，需要判断类型B
            if len(nodes_b[0].outputs) > 0:
                # 类型B也有输出，无法确定连接方向
                self.report({'ERROR'}, "无法确定连接方向，请手动连接")
                return {'CANCELLED'}
            else:
                # 类型B只有输入，A->B
                source_nodes, target_nodes = nodes_a, nodes_b
        elif len(nodes_b[0].outputs) > 0 and len(nodes_b[0].inputs) > 0:
            # 类型B既有输入又有输出，类型A只有输出
            if len(nodes_a[0].inputs) > 0:
                # 类型A也有输入，无法确定
                self.report({'ERROR'}, "无法确定连接方向，请手动连接")
                return {'CANCELLED'}
            else:
                # 类型A只有输出，B->A
                source_nodes, target_nodes = nodes_b, nodes_a
        elif len(nodes_a[0].outputs) > 0:
            # 类型A只有输出
            source_nodes, target_nodes = nodes_a, nodes_b
        elif len(nodes_b[0].outputs) > 0:
            # 类型B只有输出
            source_nodes, target_nodes = nodes_b, nodes_a
        else:
            self.report({'ERROR'}, "所选节点都没有输出端口，无法连接")
            return {'CANCELLED'}

        # 检查目标节点是否有输入端口
        for node in target_nodes:
            if len(node.inputs) == 0:
                self.report({'ERROR'}, f"节点 '{node.name}' 没有输入端口")
                return {'CANCELLED'}

        # 清除现有连接
        for source_node in source_nodes:
            for output in source_node.outputs:
                for link in output.links:
                    if link.to_node in target_nodes:
                        node_tree.links.remove(link)

        # 按位置排序（从左到右，从上到下）
        source_nodes.sort(key=lambda n: (n.location.x, -n.location.y))
        target_nodes.sort(key=lambda n: (n.location.x, -n.location.y))

        # 一对一连接
        connection_info = []
        for i in range(min(len(source_nodes), len(target_nodes))):
            source_node = source_nodes[i]
            target_node = target_nodes[i]

            # 查找可用的输入端口
            available_input = None
            for input_socket in target_node.inputs:
                if not input_socket.is_linked:
                    available_input = input_socket
                    break

            # 如果没有可用的输入端口，尝试创建新端口
            if not available_input:
                try:
                    if hasattr(target_node, 'update'):
                        target_node.inputs.new('SSMTSocketObject', f"Input {len(target_node.inputs) + 1}")
                        available_input = target_node.inputs[-1]
                except:
                    self.report({'WARNING'}, f"节点 '{target_node.name}' 没有可用的输入端口")
                    continue

            # 创建连接
            if available_input and len(source_node.outputs) > 0:
                node_tree.links.new(source_node.outputs[0], available_input)
                connection_info.append(f"{source_node.name} -> {target_node.name}")

        # 触发节点更新
        for node in target_nodes:
            if hasattr(node, 'update'):
                node.update()

        # 提供反馈
        total_connections = len(connection_info)
        self.report({'INFO'}, f"一对一连接：成功连接 {total_connections} 个节点对")
        print(f"一对一连接完成，共创建 {total_connections} 个连接:")
        for info in connection_info:
            print(f"  {info}")

        return {'FINISHED'}

    def connect_many_to_one(self, selected_nodes, type_count_dict, node_tree):
        """多对一连接模式"""
        # 识别多数节点和少数节点
        type_items = list(type_count_dict.items())
        type_items.sort(key=lambda x: x[1], reverse=True)
        
        majority_type, majority_count = type_items[0]
        minority_type, minority_count = type_items[1]

        # 按类型分组节点
        majority_nodes = [node for node in selected_nodes if node.bl_idname == majority_type]
        minority_nodes = [node for node in selected_nodes if node.bl_idname == minority_type]

        # 检查节点是否有合适的输入/输出端口
        for node in majority_nodes:
            if len(node.outputs) == 0:
                self.report({'ERROR'}, f"多数节点 '{node.name}' 没有输出端口")
                return {'CANCELLED'}

        for node in minority_nodes:
            if len(node.inputs) == 0:
                self.report({'ERROR'}, f"少数节点 '{node.name}' 没有输入端口")
                return {'CANCELLED'}

        # 清除现有连接（只清除选中节点之间的连接）
        for node in majority_nodes:
            for output in node.outputs:
                for link in output.links:
                    if link.to_node in minority_nodes:
                        node_tree.links.remove(link)

        # 分配连接：将多数节点平均分配到各个少数节点
        nodes_per_target = majority_count // minority_count
        remainder = majority_count % minority_count

        connection_info = []
        majority_index = 0

        for minority_index, minority_node in enumerate(minority_nodes):
            # 计算当前少数节点应该连接的多数节点数量
            current_batch_size = nodes_per_target + (1 if minority_index < remainder else 0)

            for i in range(current_batch_size):
                if majority_index >= len(majority_nodes):
                    break

                majority_node = majority_nodes[majority_index]

                # 查找可用的输入端口
                available_input = None
                for input_socket in minority_node.inputs:
                    if not input_socket.is_linked:
                        available_input = input_socket
                        break

                # 如果没有可用的输入端口，尝试创建新端口（针对支持动态端口的节点）
                if not available_input:
                    try:
                        # 某些节点（如Group、Output）支持动态添加端口
                        if hasattr(minority_node, 'update'):
                            minority_node.inputs.new('SSMTSocketObject', f"Input {len(minority_node.inputs) + 1}")
                            available_input = minority_node.inputs[-1]
                    except:
                        self.report({'WARNING'}, f"节点 '{minority_node.name}' 没有可用的输入端口")
                        majority_index += 1
                        continue

                # 创建连接
                if available_input and len(majority_node.outputs) > 0:
                    node_tree.links.new(majority_node.outputs[0], available_input)
                    connection_info.append(f"{majority_node.name} -> {minority_node.name}")

                majority_index += 1

        # 触发节点更新
        for node in minority_nodes:
            if hasattr(node, 'update'):
                node.update()

        # 提供成功反馈
        total_connections = len(connection_info)
        self.report({'INFO'}, f"多对一连接：成功连接 {total_connections} 个节点对")
        print(f"多对一连接完成，共创建 {total_connections} 个连接:")
        for info in connection_info:
            print(f"  {info}")

        return {'FINISHED'}


class SSMT_MT_NodeMenu_Advanced(bpy.types.Menu):
    bl_label = "高级功能"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("node.add_node", text="数据类型", icon='FILE_TEXT').type = "SSMTNode_DataType"
        layout.operator("node.add_node", text="多文件导出", icon='FILE_FOLDER').type = "SSMTNode_MultiFile_Export"


class SSMT_MT_NodeMenu_Preset(bpy.types.Menu):
    bl_label = "预设"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("ssmt.add_common_key_switches", text="常用按键开关", icon='PRESET')

class SSMT_MT_NodeMenu_PostProcess(bpy.types.Menu):
    bl_label = "后处理"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("node.add_node", text="顶点属性定义", icon='PROPERTIES').type = "SSMTNode_PostProcess_VertexAttrs"
        layout.separator()
        layout.operator("node.add_node", text="形态键配置", icon='SHAPEKEY_DATA').type = "SSMTNode_PostProcess_ShapeKey"
        layout.operator("node.add_node", text="多文件配置", icon='FILE_FOLDER').type = "SSMTNode_PostProcess_MultiFile"
        layout.separator()
        layout.operator("node.add_node", text="缓冲区清理", icon='X').type = "SSMTNode_PostProcess_BufferCleanup"
        layout.operator("node.add_node", text="资源合并", icon='LINKED').type = "SSMTNode_PostProcess_ResourceMerge"
        layout.operator("node.add_node", text="材质转资源", icon='MATERIAL').type = "SSMTNode_PostProcess_Material"
        layout.separator()
        layout.operator("node.add_node", text="血量检测", icon='DOT').type = "SSMTNode_PostProcess_HealthDetection"
        layout.operator("node.add_node", text="滑块面板", icon='DOT').type = "SSMTNode_PostProcess_SliderPanel"

def draw_node_add_menu(self, context):
    if not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return
    if context.space_data.tree_type != 'SSMTBlueprintTreeType':
        return
    
    layout = self.layout
    layout.menu("SSMT_MT_NodeMenu_Advanced", text="高级功能", icon='OPTIONS')
    layout.menu("SSMT_MT_NodeMenu_Preset", text="预设", icon='PRESET')
    layout.menu("SSMT_MT_NodeMenu_Branch", text="分支", icon='RNA')
    layout.menu("SSMT_MT_NodeMenu_ShapeKey", text="形态键", icon='SHAPEKEY_DATA')
    layout.menu("SSMT_MT_NodeMenu_PostProcess", text="后处理", icon='FILE_REFRESH')
    layout.separator()

    # Frame节点没有任何功能，它是Blender自带的一种辅助节点，用于在节点编辑器中组织和分组节点
    # 反正就当一个区域划分来用就行了
    layout.operator("node.add_node", text="Frame", icon='FILE_PARENT').type = "NodeFrame"
    layout.separator()



def draw_node_context_menu(self, context):
    """在节点编辑器右键菜单中添加批量连接选项"""
    if not isinstance(context.space_data, bpy.types.SpaceNodeEditor):
        return
    if context.space_data.tree_type != 'SSMTBlueprintTreeType':
        return
    
    # 检查是否有选中的节点
    selected_nodes = [node for node in context.space_data.edit_tree.nodes if node.select] if context.space_data.edit_tree else []
    
    if len(selected_nodes) >= 2:
        layout = self.layout
        layout.separator()
        layout.operator("ssmt.batch_connect_nodes", text="批量连接节点", icon='LINKED')


def register():
    bpy.utils.register_class(SSMT_OT_CreateGroupFromSelection)
    bpy.utils.register_class(SSMT_OT_AddCommonKeySwitches)
    bpy.utils.register_class(SSMT_OT_BatchConnectNodes)
    bpy.utils.register_class(SSMT_MT_ObjectContextMenuSub)
    bpy.utils.register_class(SSMT_MT_NodeMenu_Advanced)
    bpy.utils.register_class(SSMT_MT_NodeMenu_Preset)
    bpy.utils.register_class(SSMT_MT_NodeMenu_Branch)
    bpy.utils.register_class(SSMT_MT_NodeMenu_ShapeKey)
    bpy.utils.register_class(SSMT_MT_NodeMenu_PostProcess)

    bpy.types.NODE_MT_add.prepend(draw_node_add_menu)
    # 添加到 3D 视图物体右键菜单
    bpy.types.VIEW3D_MT_object_context_menu.append(draw_objects_context_menu_add)
    # 添加到节点编辑器右键菜单
    bpy.types.NODE_MT_context_menu.append(draw_node_context_menu)

def unregister():
    bpy.types.NODE_MT_context_menu.remove(draw_node_context_menu)
    bpy.types.NODE_MT_add.remove(draw_node_add_menu)
    bpy.types.VIEW3D_MT_object_context_menu.remove(draw_objects_context_menu_add)

    bpy.utils.unregister_class(SSMT_MT_NodeMenu_PostProcess)
    bpy.utils.unregister_class(SSMT_MT_NodeMenu_ShapeKey)
    bpy.utils.unregister_class(SSMT_MT_NodeMenu_Branch)
    bpy.utils.unregister_class(SSMT_MT_NodeMenu_Preset)
    bpy.utils.unregister_class(SSMT_MT_NodeMenu_Advanced)
    bpy.utils.unregister_class(SSMT_MT_ObjectContextMenuSub)
    bpy.utils.unregister_class(SSMT_OT_BatchConnectNodes)
    bpy.utils.unregister_class(SSMT_OT_AddCommonKeySwitches)
    bpy.utils.unregister_class(SSMT_OT_CreateGroupFromSelection)
