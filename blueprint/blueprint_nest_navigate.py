import bpy
from bpy.types import Operator
from bpy.props import StringProperty

from ..config.main_config import GlobalConfig


class SSMT_OT_BlueprintNestNavigate(Operator):
    '''Navigate through nested blueprints'''
    bl_idname = "ssmt.blueprint_nest_navigate"
    bl_label = "蓝图嵌套导航"
    bl_options = {'REGISTER', 'INTERNAL'}

    def execute(self, context):
        """执行导航操作"""
        space_data = getattr(context, "space_data", None)
        if not space_data or space_data.type != 'NODE_EDITOR':
            return {'CANCELLED'}
        
        # 获取当前选中的节点
        selected_nodes = [node for node in context.selected_nodes if hasattr(node, 'bl_idname')]
        if not selected_nodes:
            return {'CANCELLED'}
        
        # 只处理单个选中的节点
        if len(selected_nodes) > 1:
            return {'CANCELLED'}
        
        selected_node = selected_nodes[0]
        
        # 情况1: 选中蓝图嵌套节点，进入下一层级
        if selected_node.bl_idname == 'SSMTNode_Blueprint_Nest':
            self.enter_nested_blueprint(context, selected_node)
        
        # 情况2: 选中输出节点，返回上一层级
        elif selected_node.bl_idname == 'SSMTNode_Result_Output':
            self.return_to_parent_blueprint(context)
        
        return {'FINISHED'}
    
    def enter_nested_blueprint(self, context, nest_node):
        """进入嵌套蓝图"""
        blueprint_name = getattr(nest_node, 'blueprint_name', '')
        if not blueprint_name or blueprint_name == 'NONE':
            return
        
        nested_tree = bpy.data.node_groups.get(blueprint_name)
        if not nested_tree or nested_tree.bl_idname != 'SSMTBlueprintTreeType':
            return
        
        # 切换到嵌套蓝图
        space_data = getattr(context, "space_data", None)
        space_data.node_tree = nested_tree
        
        print(f"[Blueprint Nest] 进入嵌套蓝图: {blueprint_name}")
    
    def return_to_parent_blueprint(self, context):
        """返回父蓝图 - 基于引用关系查找"""
        # 获取当前蓝图树
        space_data = getattr(context, "space_data", None)
        current_tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
        
        if not current_tree:
            return
        
        current_blueprint_name = current_tree.name
        
        # 查找所有引用了当前蓝图的蓝图
        parent_blueprints = self.find_parent_blueprints(current_blueprint_name)
        
        if not parent_blueprints:
            print(f"[Blueprint Nest] 未找到引用蓝图 '{current_blueprint_name}' 的父蓝图")
            return
        
        # 如果有多个父蓝图，选择最近使用的（或者第一个）
        # 这里简单选择第一个找到的
        parent_tree, nest_node = parent_blueprints[0]
        
        if len(parent_blueprints) > 1:
            print(f"[Blueprint Nest] 警告: 找到 {len(parent_blueprints)} 个父蓝图，选择第一个: {parent_tree.name}")
            for tree, node in parent_blueprints:
                print(f"  - {tree.name} (节点: {node.name})")
        
        # 切换到父蓝图
        space_data.node_tree = parent_tree
        
        # 选中对应的嵌套节点
        if nest_node:
            nest_node.select = True
            # 取消其他节点的选中状态
            for node in parent_tree.nodes:
                if node != nest_node:
                    node.select = False
        
        print(f"[Blueprint Nest] 返回父蓝图: {parent_tree.name}")
        print(f"[Blueprint Nest] 选中嵌套节点: {nest_node.name}")
    
    def find_parent_blueprints(self, blueprint_name):
        """
        查找所有引用了指定蓝图的蓝图
        
        返回: [(父蓝图树, 嵌套节点), ...]
        """
        parent_blueprints = []
        
        # 遍历所有蓝图树
        for node_group in bpy.data.node_groups:
            # 只检查 SSMT 蓝图
            if node_group.bl_idname != 'SSMTBlueprintTreeType':
                continue
            
            # 跳过自己
            if node_group.name == blueprint_name:
                continue
            
            # 查找该蓝图中的所有嵌套节点
            for node in node_group.nodes:
                if node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    # 检查是否引用了目标蓝图
                    if getattr(node, 'blueprint_name', '') == blueprint_name:
                        parent_blueprints.append((node_group, node))
        
        return parent_blueprints
    
    @classmethod
    def poll(cls, context):
        """检查是否可以执行"""
        space_data = getattr(context, "space_data", None)
        if not space_data or space_data.type != 'NODE_EDITOR':
            return False
        
        # 检查是否有选中的节点
        selected_nodes = [node for node in context.selected_nodes if hasattr(node, 'bl_idname')]
        if not selected_nodes:
            return False
        
        # 只处理蓝图嵌套节点或输出节点
        selected_node = selected_nodes[0]
        if len(selected_nodes) > 1:
            return False
        
        return selected_node.bl_idname in ('SSMTNode_Blueprint_Nest', 'SSMTNode_Result_Output')


class SSMT_OT_CreateBlueprintFromNest(Operator):
    '''Create a new blueprint from nest node'''
    bl_idname = "ssmt.create_blueprint_from_nest"
    bl_label = "创建新蓝图"
    bl_options = {'REGISTER', 'INTERNAL'}
    
    blueprint_name: StringProperty(
        name="蓝图名称",
        description="输入新蓝图的名称",
        default=""
    )
    
    node_name: StringProperty(
        name="节点名称",
        default=""
    )
    
    def invoke(self, context, event):
        # 获取当前选中的嵌套节点
        if self.node_name:
            space_data = getattr(context, "space_data", None)
            if space_data and space_data.type == 'NODE_EDITOR':
                tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
                if tree:
                    node = tree.nodes.get(self.node_name)
                    if node and node.bl_idname == 'SSMTNode_Blueprint_Nest':
                        # 设置默认名称
                        if not self.blueprint_name:
                            self.blueprint_name = f"SSMT_Blueprint_{len(bpy.data.node_groups) + 1}"
                        return context.window_manager.invoke_props_dialog(self)
        
        return {'CANCELLED'}
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "blueprint_name")
        
        # 检查名称是否已存在
        if self.blueprint_name and bpy.data.node_groups.get(self.blueprint_name):
            layout.label(text="警告: 该名称已存在，将使用现有蓝图", icon='ERROR')
    
    def execute(self, context):
        if not self.blueprint_name:
            self.report({'WARNING'}, "请输入蓝图名称")
            return {'CANCELLED'}
        
        # 检查蓝图是否已存在
        existing_tree = bpy.data.node_groups.get(self.blueprint_name)
        
        if existing_tree and existing_tree.bl_idname == 'SSMTBlueprintTreeType':
            # 使用现有蓝图
            tree = existing_tree
            self.report({'INFO'}, f"使用现有蓝图: {self.blueprint_name}")
        else:
            # 创建新的蓝图
            tree = bpy.data.node_groups.new(self.blueprint_name, 'SSMTBlueprintTreeType')
            # 设置伪用户，防止在清理非使用数据时被清理掉
            tree.use_fake_user = True
            self.report({'INFO'}, f"创建新蓝图: {self.blueprint_name}")
            
            # 在新蓝图中添加一个输出节点
            from .blueprint_node_base import SSMTNodeBase
            output_node = tree.nodes.new('SSMTNode_Result_Output')
            output_node.location = (400, 0)
        
        # 更新嵌套节点的蓝图引用
        space_data = getattr(context, "space_data", None)
        if space_data and space_data.type == 'NODE_EDITOR':
            current_tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
            if current_tree:
                node = current_tree.nodes.get(self.node_name)
                if node and node.bl_idname == 'SSMTNode_Blueprint_Nest':
                    # 找到对应的枚举值并设置
                    node.blueprint_name = self.blueprint_name
        
        return {'FINISHED'}
    
    @classmethod
    def poll(cls, context):
        space_data = getattr(context, "space_data", None)
        return space_data and space_data.type == 'NODE_EDITOR'


# Tab 键映射
_keymaps = []


def register_keymaps():
    """注册 Tab 键映射"""
    wm = bpy.context.window_manager
    if not wm.keyconfigs.addon:
        return
    
    kc = wm.keyconfigs.addon
    
    # 节点编辑器的 Tab 键映射
    km = kc.keymaps.new(name='Node Editor', space_type='NODE_EDITOR')
    
    # Tab 键导航
    kmi = km.keymap_items.new(
        'ssmt.blueprint_nest_navigate', 
        type='TAB', 
        value='PRESS'
    )
    _keymaps.append((km, kmi))
    
    print("[Blueprint Nest] 已注册 Tab 键导航")


def unregister_keymaps():
    """注销 Tab 键映射"""
    for km, kmi in _keymaps:
        km.keymap_items.remove(kmi)
    _keymaps.clear()
    
    print("[Blueprint Nest] 已注销 Tab 键导航")


def register():
    bpy.utils.register_class(SSMT_OT_BlueprintNestNavigate)
    bpy.utils.register_class(SSMT_OT_CreateBlueprintFromNest)
    register_keymaps()


def unregister():
    unregister_keymaps()
    bpy.utils.unregister_class(SSMT_OT_CreateBlueprintFromNest)
    bpy.utils.unregister_class(SSMT_OT_BlueprintNestNavigate)
