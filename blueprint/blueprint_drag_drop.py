import bpy
from ..config.main_config import GlobalConfig
from ..utils.collection_utils import CollectionUtils
from .blueprint_node_obj import _is_viewing_group_objects


_workspace_objects_cache = set()
_workspace_object_ids_cache = set()
_object_to_node_mapping = {}
_node_to_object_id_mapping = {}
_is_importing = False
_syncing_selection = False
_node_selection_timer = None
_object_name_check_timer = None
_last_node_selection_state = {}
_syncing_from_node = False
_syncing_from_node_cooldown = 0
_last_synced_object = None
_cleanup_counter = 0


@bpy.app.handlers.persistent
def object_visibility_handler(scene):
    """处理物体可见性变化事件，同步更新对应节点的禁用状态"""
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    if obj_name:
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            current_mute = obj.hide_viewport
                            if node.mute != current_mute:
                                node.mute = current_mute


@bpy.app.handlers.persistent
def object_selection_handler(scene):
    """处理物体选中状态变化事件，同步更新对应节点的选中状态"""
    global _syncing_selection, _syncing_from_node_cooldown, _last_synced_object
    
    if _syncing_selection:
        return
    
    if _is_viewing_group_objects:
        return
    
    if _syncing_from_node_cooldown > 0:
        _syncing_from_node_cooldown -= 1
        return
    
    _syncing_selection = True
    
    try:
        for tree in bpy.data.node_groups:
            if tree.bl_idname == 'SSMTBlueprintTreeType':
                for node in tree.nodes:
                    if node.bl_idname == 'SSMTNode_Object_Info':
                        obj_name = getattr(node, 'object_name', '')
                        if obj_name:
                            obj = bpy.data.objects.get(obj_name)
                            if obj:
                                if obj == _last_synced_object:
                                    continue
                                current_select = obj.select_get()
                                if node.select != current_select:
                                    node.select = current_select
    finally:
        _syncing_selection = False


@bpy.app.handlers.persistent
def workspace_object_added_handler(scene):
    """处理工作合集中添加新物体的事件，确保工作合集中所有物体都有对应的物体信息节点"""
    global _workspace_objects_cache, _workspace_object_ids_cache, _object_to_node_mapping, _is_importing
    
    if _is_importing:
        return
    
    if not GlobalConfig.workspacename:
        return
    
    workspace_collection = bpy.data.collections.get(GlobalConfig.workspacename)
    if not workspace_collection:
        return
    
    current_objects = _get_objects_in_workspace(workspace_collection)
    current_object_ids = _get_object_ids_in_workspace(workspace_collection)
    
    new_object_ids = current_object_ids - _workspace_object_ids_cache
    
    if new_object_ids:
        for tree in bpy.data.node_groups:
            if tree.bl_idname == 'SSMTBlueprintTreeType':
                _ensure_all_objects_have_nodes(tree, current_objects)
    
    _workspace_objects_cache = current_objects
    _workspace_object_ids_cache = current_object_ids


def _ensure_all_objects_have_nodes(tree, workspace_objects):
    """确保工作合集中的所有物体都有对应的节点"""
    global _object_to_node_mapping, _node_to_object_id_mapping
    existing_object_names = set()
    
    for node in tree.nodes:
        if node.bl_idname == 'SSMTNode_Object_Info':
            obj_name = getattr(node, 'object_name', '')
            if obj_name:
                existing_object_names.add(obj_name)
    
    missing_objects = workspace_objects - existing_object_names
    
    for obj_name in missing_objects:
        node = _create_object_info_node(tree, obj_name)
        if node:
            _object_to_node_mapping[obj_name] = node
            obj_id = getattr(node, 'object_id', '')
            if obj_id:
                node_key = (tree.name, node.name)
                _node_to_object_id_mapping[node_key] = obj_id


def _get_objects_in_workspace(workspace_collection):
    """获取工作合集中所有物体，返回物体名称和ID的集合"""
    objects_in_workspace = set()
    
    def collect_objects(collection):
        for obj in collection.objects:
            if obj.type == 'MESH':
                objects_in_workspace.add(obj.name)
        for child in collection.children:
            collect_objects(child)
    
    collect_objects(workspace_collection)
    return objects_in_workspace


def _get_object_ids_in_workspace(workspace_collection):
    """获取工作合集中所有物体的ID，用于检测重命名"""
    object_ids_in_workspace = set()
    
    def collect_object_ids(collection):
        for obj in collection.objects:
            if obj.type == 'MESH':
                object_ids_in_workspace.add(str(obj.as_pointer()))
        for child in collection.children:
            collect_object_ids(child)
    
    collect_object_ids(workspace_collection)
    return object_ids_in_workspace


def _create_object_info_node(tree, obj_name):
    """创建物体信息节点并设置位置"""
    node = tree.nodes.new('SSMTNode_Object_Info')
    node.object_name = obj_name
    
    node.label = obj_name
    
    if "-" in obj_name:
        obj_name_split = obj_name.split("-")
        if len(obj_name_split) >= 3:
            node.draw_ib = obj_name_split[0]
            node.component = obj_name_split[1]
            node.alias_name = obj_name_split[2]
    
    object_info_count = 0
    for n in tree.nodes:
        if n.bl_idname == 'SSMTNode_Object_Info':
            object_info_count += 1
    
    _position_new_node(tree, node, object_info_count - 1)
    
    obj = bpy.data.objects.get(obj_name)
    if obj:
        node.object_id = str(obj.as_pointer())
    
    return node


def _position_new_node(tree, new_node, index):
    """为新节点设置位置，只对新节点进行位置设置"""
    NODE_WIDTH = 300
    NODE_HEIGHT = 150
    NODES_PER_ROW = 3
    
    row = index // NODES_PER_ROW
    col = index % NODES_PER_ROW
    new_node.location = (col * NODE_WIDTH, -row * NODE_HEIGHT)


def _initialize_workspace_cache():
    """初始化工作合集中物体的缓存"""
    global _workspace_objects_cache, _workspace_object_ids_cache, _object_to_node_mapping, _node_to_object_id_mapping, _is_importing
    
    if not GlobalConfig.workspacename:
        _workspace_objects_cache = set()
        _workspace_object_ids_cache = set()
        _object_to_node_mapping = {}
        _node_to_object_id_mapping = {}
        _is_importing = False
        return
    
    workspace_collection = bpy.data.collections.get(GlobalConfig.workspacename)
    if workspace_collection:
        _workspace_objects_cache = _get_objects_in_workspace(workspace_collection)
        _workspace_object_ids_cache = _get_object_ids_in_workspace(workspace_collection)
    else:
        _workspace_objects_cache = set()
        _workspace_object_ids_cache = set()
    
    _initialize_node_object_ids()
    _build_object_to_node_mapping()
    _update_node_to_object_id_mapping()
    _is_importing = False


def _initialize_node_object_ids():
    """为旧工程中的节点初始化物体ID，建立节点与物体的关联"""
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    obj_id = getattr(node, 'object_id', '')
                    
                    if obj_name and not obj_id:
                        obj = bpy.data.objects.get(obj_name)
                        if obj:
                            node.object_id = str(obj.as_pointer())


def _update_node_to_object_id_mapping():
    """更新节点到物体ID的映射关系"""
    global _node_to_object_id_mapping
    _node_to_object_id_mapping = {}
    
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_id = getattr(node, 'object_id', '')
                    if obj_id:
                        node_key = (tree.name, node.name)
                        _node_to_object_id_mapping[node_key] = obj_id


def _cleanup_invalid_mappings():
    """清理无效的映射关系"""
    global _object_to_node_mapping
    
    valid_object_names = set(obj.name for obj in bpy.data.objects)
    keys_to_remove = []
    
    for obj_name in _object_to_node_mapping:
        if obj_name not in valid_object_names:
            keys_to_remove.append(obj_name)
    
    for key in keys_to_remove:
        del _object_to_node_mapping[key]


def _build_object_to_node_mapping():
    """构建物体到节点的映射关系"""
    global _object_to_node_mapping
    _object_to_node_mapping = {}
    
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_name = getattr(node, 'object_name', '')
                    if obj_name:
                        _object_to_node_mapping[obj_name] = node


def set_importing_state(is_importing):
    """设置导入状态，避免导入时触发自动节点创建"""
    global _is_importing
    _is_importing = is_importing


def refresh_workspace_cache():
    """刷新工作合集中物体的缓存，用于导入完成后调用"""
    global _is_importing
    set_importing_state(False)
    _initialize_workspace_cache()


def sync_node_selection_to_objects():
    """同步节点选中状态到物体，当节点选中状态变化时调用"""
    global _syncing_selection
    
    if _syncing_selection:
        return
    
    _syncing_selection = True
    
    try:
        for tree in bpy.data.node_groups:
            if tree.bl_idname == 'SSMTBlueprintTreeType':
                for node in tree.nodes:
                    if node.bl_idname == 'SSMTNode_Object_Info':
                        obj_name = getattr(node, 'object_name', '')
                        if obj_name:
                            obj = bpy.data.objects.get(obj_name)
                            if obj:
                                obj.select_set(node.select)
    finally:
        _syncing_selection = False


def check_node_selection_changes():
    """定时检查节点选中状态变化，并同步到物体"""
    global _last_node_selection_state, _syncing_selection, _syncing_from_node_cooldown, _last_synced_object, _cleanup_counter
    
    if _syncing_selection:
        return 0.1
    
    if _is_viewing_group_objects:
        return 0.1
    
    _cleanup_counter += 1
    if _cleanup_counter >= 600:
        _cleanup_counter = 0
        _cleanup_invalid_mappings()
    
    changed_nodes = []
    current_node_keys = set()
    
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    node_key = (tree.name, node.name)
                    current_node_keys.add(node_key)
                    current_select = node.select
                    
                    if node_key in _last_node_selection_state:
                        if _last_node_selection_state[node_key] != current_select:
                            changed_nodes.append(node)
                            _last_node_selection_state[node_key] = current_select
                    else:
                        _last_node_selection_state[node_key] = current_select
    
    keys_to_remove = set(_last_node_selection_state.keys()) - current_node_keys
    for key in keys_to_remove:
        del _last_node_selection_state[key]
    
    if changed_nodes:
        _syncing_selection = True
        _syncing_from_node_cooldown = 5
        _last_synced_object = None
        try:
            for node in changed_nodes:
                obj_name = getattr(node, 'object_name', '')
                if obj_name:
                    obj = bpy.data.objects.get(obj_name)
                    if obj:
                        _last_synced_object = obj
                        obj.select_set(node.select)
        finally:
            _syncing_selection = False
    
    return 0.1


def check_object_name_changes():
    """定时检查物体名称变化，并更新对应节点的物体引用"""
    global _node_to_object_id_mapping, _object_to_node_mapping
    
    if not _node_to_object_id_mapping:
        return 2.0
    
    object_id_to_name = {str(obj.as_pointer()): obj.name for obj in bpy.data.objects}
    
    for tree in bpy.data.node_groups:
        if tree.bl_idname == 'SSMTBlueprintTreeType':
            for node in tree.nodes:
                if node.bl_idname == 'SSMTNode_Object_Info':
                    obj_id = getattr(node, 'object_id', '')
                    if not obj_id:
                        continue
                    
                    obj_name = getattr(node, 'object_name', '')
                    if not obj_name:
                        continue
                    
                    current_obj = bpy.data.objects.get(obj_name)
                    if current_obj and str(current_obj.as_pointer()) == obj_id:
                        continue
                    
                    if obj_id in object_id_to_name:
                        new_name = object_id_to_name[obj_id]
                        if node.object_name != new_name:
                            old_name = node.object_name
                            node.object_name = new_name
                            
                            if old_name in _object_to_node_mapping:
                                del _object_to_node_mapping[old_name]
                            _object_to_node_mapping[new_name] = node
    
    return 2.0


class SSMT_OT_CheckObjectNameChanges(bpy.types.Operator):
    '''手动检查物体名称变化，并更新对应节点的物体引用'''
    bl_idname = "ssmt.check_object_name_changes"
    bl_label = "检查物体名称变化"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        global _node_to_object_id_mapping
        
        if not _node_to_object_id_mapping:
            self.report({'INFO'}, "没有需要检查的节点")
            return {'CANCELLED'}
        
        object_id_to_name = {str(obj.as_pointer()): obj.name for obj in bpy.data.objects}
        updated_count = 0
        
        for tree in bpy.data.node_groups:
            if tree.bl_idname == 'SSMTBlueprintTreeType':
                for node in tree.nodes:
                    if node.bl_idname == 'SSMTNode_Object_Info':
                        obj_id = getattr(node, 'object_id', '')
                        if not obj_id:
                            continue
                        
                        obj_name = getattr(node, 'object_name', '')
                        if not obj_name:
                            continue
                        
                        current_obj = bpy.data.objects.get(obj_name)
                        if current_obj and str(current_obj.as_pointer()) == obj_id:
                            continue
                        
                        if obj_id in object_id_to_name:
                            new_name = object_id_to_name[obj_id]
                            if node.object_name != new_name:
                                node.object_name = new_name
                                updated_count += 1
        
        if updated_count > 0:
            self.report({'INFO'}, f"已更新 {updated_count} 个节点的物体引用")
        else:
            self.report({'INFO'}, "所有节点的物体引用都是最新的")
        
        return {'FINISHED'}


def register():
    global _node_selection_timer, _object_name_check_timer
    bpy.utils.register_class(SSMT_OT_CheckObjectNameChanges)
    _initialize_workspace_cache()
    bpy.app.handlers.depsgraph_update_post.append(object_visibility_handler)
    bpy.app.handlers.depsgraph_update_post.append(object_selection_handler)
    bpy.app.handlers.depsgraph_update_post.append(workspace_object_added_handler)
    
    _node_selection_timer = bpy.app.timers.register(check_node_selection_changes, persistent=True)
    _object_name_check_timer = bpy.app.timers.register(check_object_name_changes, persistent=True)


def unregister():
    global _node_selection_timer, _object_name_check_timer
    if _node_selection_timer:
        try:
            bpy.app.timers.unregister(_node_selection_timer)
        except:
            pass
        _node_selection_timer = None
    
    if _object_name_check_timer:
        try:
            bpy.app.timers.unregister(_object_name_check_timer)
        except:
            pass
        _object_name_check_timer = None
    
    if object_visibility_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(object_visibility_handler)
    if object_selection_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(object_selection_handler)
    if workspace_object_added_handler in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(workspace_object_added_handler)
    
    bpy.utils.unregister_class(SSMT_OT_CheckObjectNameChanges)
    
    global _workspace_objects_cache, _workspace_object_ids_cache, _object_to_node_mapping, _node_to_object_id_mapping, _is_importing, _syncing_selection, _last_node_selection_state, _cleanup_counter
    _workspace_objects_cache = set()
    _workspace_object_ids_cache = set()
    _object_to_node_mapping = {}
    _node_to_object_id_mapping = {}
    _is_importing = False
    _syncing_selection = False
    _last_node_selection_state = {}
    _cleanup_counter = 0
