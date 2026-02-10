import bpy
from bpy.types import NodeTree, Node, NodeSocket

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_generate_mod import Properties_GenerateMod
from .blueprint_node_base import SSMTBlueprintTree, SSMTNodeBase

BLENDER_VERSION = bpy.app.version[:2]

_picking_node_name = None
_picking_tree_name = None
_is_viewing_group_objects = False


class SSMT_OT_RefreshNodeObjectIDs(bpy.types.Operator):
    '''刷新节点树中所有节点的物体ID关联'''
    bl_idname = "ssmt.refresh_node_object_ids"
    bl_label = "刷新物体ID关联"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        updated_count = 0
        
        for node in tree.nodes:
            if node.bl_idname == 'SSMTNode_Object_Info':
                obj_name = getattr(node, 'object_name', '')
                obj_id = getattr(node, 'object_id', '')
                
                if obj_name and not obj_id:
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        node.object_id = str(obj.as_pointer())
                        updated_count += 1
        
        if updated_count > 0:
            self.report({'INFO'}, f"已更新 {updated_count} 个节点的物体ID关联")
        else:
            self.report({'INFO'}, "所有节点都已建立物体ID关联")
        
        return {'FINISHED'}


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
            try:
                bpy.ops.object.select_all(action='DESELECT')
            except:
                pass
                
            obj.select_set(True)
            context.view_layer.objects.active = obj
            self.report({'INFO'}, f"Selected: {obj_name}")
        else:
            self.report({'WARNING'}, f"Object '{obj_name}' not found")
        
        return {'FINISHED'}


class SSMT_OT_StartPickObject(bpy.types.Operator):
    '''Start picking an object from 3D View'''
    bl_idname = "ssmt.start_pick_object"
    bl_label = "Pick Object"
    bl_description = "点击后在3D视图中选择一个物体"
    
    node_name: bpy.props.StringProperty() # type: ignore
    
    def execute(self, context):
        global _picking_node_name, _picking_tree_name
        
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        _picking_node_name = self.node_name
        _picking_tree_name = tree.name
        self.report({'INFO'}, "请在3D视图中点击选择一个物体")
        
        bpy.ops.ssmt.pick_object_modal('INVOKE_DEFAULT')
        
        return {'FINISHED'}


class SSMT_OT_PickObjectModal(bpy.types.Operator):
    '''Modal operator for picking objects in 3D View'''
    bl_idname = "ssmt.pick_object_modal"
    bl_label = "Pick Object"
    bl_options = {'REGISTER', 'INTERNAL'}
    
    def invoke(self, context, event):
        global _picking_node_name
        
        if not _picking_node_name:
            return {'CANCELLED'}
        
        self._initial_selected_objs = set(context.selected_objects)
        if context.selected_objects:
            self._last_selected_obj = context.selected_objects[0]
        else:
            self._last_selected_obj = None
        
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}
    
    def modal(self, context, event):
        global _picking_node_name, _picking_tree_name
        
        if event.type == 'ESC':
            _picking_node_name = None
            _picking_tree_name = None
            return {'CANCELLED'}
        
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            for area in context.screen.areas:
                if area.type == 'VIEW_3D':
                    region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                    if region and area.x <= event.mouse_x <= area.x + area.width and area.y <= event.mouse_y <= area.y + area.height:
                        return {'PASS_THROUGH'}
        
        if event.type == 'MOUSEMOVE':
            current_selected = context.selected_objects
            if current_selected:
                current_obj = current_selected[0]
                if current_obj != self._last_selected_obj and current_obj not in self._initial_selected_objs:
                    tree = bpy.data.node_groups.get(_picking_tree_name)
                    if tree:
                        node = tree.nodes.get(_picking_node_name)
                        if node:
                            node.object_name = current_obj.name
                            self.report({'INFO'}, f"已选择物体: {current_obj.name}")
                    
                    _picking_node_name = None
                    _picking_tree_name = None
                    return {'FINISHED'}
        
        return {'PASS_THROUGH'}


def draw_view3d_header(self, context):
    global _picking_node_name
    if _picking_node_name:
        self.layout.label(text="请在3D视图中点击选择一个物体...", icon='EYEDROPPER')


class SSMTNode_Object_Info(SSMTNodeBase):
    '''Object Info Node'''
    bl_idname = 'SSMTNode_Object_Info'
    bl_label = 'Object Info'
    bl_icon = 'OBJECT_DATAMODE'
    bl_width_min = 300
    
    def update_object_name(self, context):
        if self.object_name:
            self.label = self.object_name
            if "-" in self.object_name:
                obj_name_split = self.object_name.split("-")
                self.draw_ib = obj_name_split[0]
                self.component = obj_name_split[1]
                self.alias_name = obj_name_split[2]
            
            obj = bpy.data.objects.get(self.object_name)
            if obj:
                self.object_id = str(obj.as_pointer())
        else:
            self.label = "Object Info"
            self.object_id = ""
        
        self.update_node_width([self.object_name, self.draw_ib, self.component, self.alias_name])
    object_name: bpy.props.StringProperty(name="Object Name", default="", update=update_object_name)
    object_id: bpy.props.StringProperty(name="Object ID", default="")


    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    alias_name: bpy.props.StringProperty(name="Alias Name", default="") # type: ignore

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Object")

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)

        row.prop_search(self, "object_name", bpy.data, "objects", text="", icon='OBJECT_DATA')
        
        op = row.operator("ssmt.start_pick_object", text="", icon='EYEDROPPER')
        op.node_name = self.name

        if self.object_name:
            op = row.operator("ssmt.select_node_object", text="", icon='RESTRICT_SELECT_OFF')
            op.object_name = self.object_name

        layout.prop(self, "draw_ib", text="DrawIB")
        layout.prop(self, "component", text="Component")
        layout.prop(self, "alias_name", text="Alias Name")


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
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


class SSMTNode_ToggleKey(SSMTNodeBase):
    '''【按键开关】会控制所有连接到它输入端口的对象,是【按键切换】的一个特殊情况，因为常用所以单独做成了一个节点'''
    bl_idname = 'SSMTNode_ToggleKey'
    bl_label = 'Toggle Key'
    bl_icon = 'GROUP'

    def update_key_name(self, context):
        self.update_node_width([self.key_name, self.comment])
    
    def update_comment(self, context):
        self.update_node_width([self.key_name, self.comment])
    
    key_name: bpy.props.StringProperty(name="Key Name", default="", update=update_key_name) # type: ignore
    default_on: bpy.props.BoolProperty(name="Default On", default=False) # type: ignore
    comment: bpy.props.StringProperty(name="备注", description="备注信息，会以注释形式生成到配置表中", default="", update=update_comment) # type: ignore
    
    def init(self, context):
        self.label = "按键开关"
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 200
        self.use_custom_color = True
        self.color = (0.41, 0.42, 0.66)

    def draw_buttons(self, context, layout):
        row = layout.row(align=True)
        row.prop(self, "key_name", text="按键")
        row.operator("wm.url_open", text="", icon='HELP').url = "https://learn.microsoft.com/en-us/windows/win32/inputdev/virtual-key-codes"
        
        layout.prop(self, "default_on", text="默认开启")
        layout.prop(self, "comment", text="备注")

    def update(self):
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
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

    def update_key_name(self, context):
        self.update_node_width([self.key_name, self.comment])
    
    def update_comment(self, context):
        self.update_node_width([self.key_name, self.comment])
    
    key_name: bpy.props.StringProperty(name="Key Name", default="", update=update_key_name) # type: ignore
    comment: bpy.props.StringProperty(name="备注", description="备注信息，会以注释形式生成到配置表中", default="", update=update_comment) # type: ignore
    
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
        
        layout.prop(self, "comment", text="备注")
        
        row = layout.row(align=True)
        op_add = row.operator("ssmt.switch_add_socket", text="Add", icon='ADD')
        op_add.node_name = self.name
        
        op_rem = row.operator("ssmt.switch_remove_socket", text="Remove", icon='REMOVE')
        op_rem.node_name = self.name


class SSMTNode_Result_Output(SSMTNodeBase):
    '''Result Output Node'''
    bl_idname = 'SSMTNode_Result_Output'
    bl_label = 'Generate Mod'
    bl_icon = 'EXPORT'

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Group 1")
        self.outputs.new('SSMTSocketPostProcess', "Post Process")
        self.width = 400

    def draw_buttons(self, context, layout):
        op = layout.operator("ssmt.generate_mod_blueprint", text="Generate Mod", icon='EXPORT')
        if hasattr(self, "id_data") and self.id_data:
             op.node_tree_name = self.id_data.name
        
        if GlobalConfig.logic_name == LogicName.WWMI or GlobalConfig.logic_name == LogicName.WuWa:
            layout.prop(context.scene.properties_wwmi, "ignore_muted_shape_keys")
            layout.prop(context.scene.properties_wwmi, "apply_all_modifiers")
            layout.prop(context.scene.properties_wwmi, "export_add_missing_vertex_groups")

        layout.prop(context.scene.properties_generate_mod, 
                    "forbid_auto_texture_ini",text="禁止自动贴图流程")

        if GlobalConfig.logic_name != LogicName.UnityCPU:
            layout.prop(context.scene.properties_generate_mod,
                        "recalculate_tangent",text="向量归一化法线存入TANGENT(全局)")

        if GlobalConfig.logic_name == LogicName.HIMI:
            layout.prop(context.scene.properties_generate_mod,
                        "recalculate_color",text="算术平均归一化法线存入COLOR(全局)")

        if GlobalConfig.logic_name == LogicName.ZZMI:
            layout.prop(context.scene.properties_generate_mod, "zzz_use_slot_fix")

        if GlobalConfig.logic_name == LogicName.GIMI:
            layout.prop(context.scene.properties_generate_mod, "gimi_use_orfix")

        layout.prop(context.scene.properties_generate_mod, "generate_branch_mod_gui",text="生成分支架构Mod面板(测试中)")

        layout.prop(context.scene.properties_generate_mod, "open_mod_folder_after_generate_mod",text="生成Mod后打开Mod所在文件夹")

        layout.prop(context.scene.properties_generate_mod, "use_specific_generate_mod_folder_path")

        if Properties_GenerateMod.use_specific_generate_mod_folder_path():
            box = layout.box()
            box.label(text="当前生成Mod位置文件夹:")
            box.label(text=context.scene.properties_generate_mod.generate_mod_folder_path)

            layout.operator("ssmt.select_generate_mod_folder", icon='FILE_FOLDER')

    def update(self):
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Group {len(self.inputs) + 1}")
        
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
             self.inputs.remove(self.inputs[-1])


class SSMT_OT_View_Group_Objects(bpy.types.Operator):
    '''递归解析当前组下面所有的物体并放到一个新的窗口中展示，注意组节点最好不要包含按键切换，否则会同时展示所有切换分支内容'''
    bl_idname = "ssmt.view_group_objects"
    bl_label = "View Group Objects"
    
    node_name: bpy.props.StringProperty() # type: ignore

    def execute(self, context):
        global _is_viewing_group_objects
        
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

        if context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.select_all(action='DESELECT')
        for obj in objects_to_show:
            obj.select_set(True)

        _is_viewing_group_objects = True
        
        try:
            bpy.ops.wm.window_new()
            new_window = context.window_manager.windows[-1]

            if new_window.screen and new_window.screen.areas:
                area = new_window.screen.areas[0]
                area.type = 'VIEW_3D'
                area.ui_type = 'VIEW_3D'
                
                region = next((r for r in area.regions if r.type == 'WINDOW'), None)
                
                if region:
                    with context.temp_override(window=new_window, area=area, region=region):
                        try:
                            if area.spaces.active.region_3d.is_perspective:
                                bpy.ops.view3d.view_persportho() 
                            
                            bpy.ops.view3d.localview() 
                            bpy.ops.view3d.view_axis(type='FRONT')
                            bpy.ops.view3d.view_selected()
                            
                            if area.spaces.active:
                                area.spaces.active.shading.type = 'SOLID'
                        except Exception as e:
                            print(f"View setup warning: {e}")
        finally:
            _is_viewing_group_objects = False

        return {'FINISHED'}


classes = (
    SSMT_OT_RefreshNodeObjectIDs,
    SSMT_OT_SelectNodeObject,
    SSMT_OT_StartPickObject,
    SSMT_OT_PickObjectModal,
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
    bpy.types.VIEW3D_HT_header.append(draw_view3d_header)


def unregister():
    bpy.types.VIEW3D_HT_header.remove(draw_view3d_header)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
