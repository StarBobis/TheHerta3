import bpy
import json
import math
import bmesh
import os

from mathutils import *
from math import * 

from typing import List, Dict, Union
from dataclasses import dataclass, field, asdict

from .format_utils import Fatal
from operator import attrgetter, itemgetter


def assert_object(obj):
    if isinstance(obj, str):
        obj = get_object(obj)
    elif obj not in bpy.data.objects.values():
        raise ValueError('Not of object type: %s' % str(obj))
    return obj


def get_mode(context):
    if context.active_object:
        return context.active_object.mode


def set_mode(context, mode):
    active_object = get_active_object(context)
    if active_object is not None and mode is not None:
        if not object_is_hidden(active_object):
            bpy.ops.object.mode_set(mode=mode)


@dataclass
class UserContext:
    active_object: bpy.types.Object
    selected_objects: bpy.types.Object
    mode: str


def get_user_context(context):
    return UserContext(
        active_object = get_active_object(context),
        selected_objects = get_selected_objects(context),
        mode = get_mode(context),
    )


def set_user_context(context, user_context):
    deselect_all_objects()
    for object in user_context.selected_objects:
        try:
            select_object(object)
        except ReferenceError as e:
            pass
    if user_context.active_object:
        set_active_object(context, user_context.active_object)
        set_mode(context, user_context.mode)


def get_object(obj_name):
    return bpy.data.objects[obj_name]
        

def get_active_object(context):
    return context.view_layer.objects.active


def get_selected_objects(context):
    return context.selected_objects


def link_object_to_scene(context, obj):
    context.scene.collection.objects.link(obj)


def unlink_object_from_scene(context, obj):
    context.scene.collection.objects.unlink(obj)


def object_exists(obj_name):
    return obj_name in bpy.data.objects.keys()


def link_object_to_collection(obj, col):
    obj = assert_object(obj)
    col = assert_collection(col)
    col.objects.link(obj)


def unlink_object_from_collection(obj, col):
    obj = assert_object(obj)
    col = assert_collection(col)
    col.objects.unlink(obj) 


def rename_object(obj, obj_name):
    obj = assert_object(obj)
    obj.name = obj_name
    

def select_object(obj):
    obj = assert_object(obj)
    obj.select_set(True)


def deselect_object(obj):
    obj = assert_object(obj)
    obj.select_set(False)


def deselect_all_objects():
    for obj in bpy.context.selected_objects:
        deselect_object(obj)
    bpy.context.view_layer.objects.active = None


def object_is_selected(obj):
    return obj.select_get()


def set_active_object(context, obj):
    obj = assert_object(obj)
    context.view_layer.objects.active = obj


def object_is_hidden(obj):
    return obj.hide_get()


def hide_object(obj):
    obj = assert_object(obj)
    obj.hide_set(True)


def unhide_object(obj):
    obj = assert_object(obj)
    obj.hide_set(False)


def set_custom_property(obj, property, value):
    obj = assert_object(obj)
    obj[property] = value


def remove_object(obj):
    obj = assert_object(obj)
    bpy.data.objects.remove(obj, do_unlink=True)


def get_modifiers(obj):
    obj = assert_object(obj)
    return obj.modifiers





def copy_object(context, obj, name=None, collection=None):
    with OpenObject(context, obj, mode='OBJECT') as obj:
        new_obj = obj.copy()
        new_obj.data = obj.data.copy()
        if name:
            rename_object(new_obj, name)
        if collection:
            link_object_to_collection(new_obj, collection)
        return new_obj


def assert_vertex_group(obj, vertex_group):
    obj = assert_object(obj)
    if isinstance(vertex_group, bpy.types.VertexGroup):
        vertex_group = vertex_group.name
    return obj.vertex_groups[vertex_group]


def get_vertex_groups(obj):
    obj = assert_object(obj)
    return obj.vertex_groups


def remove_vertex_groups(obj, vertex_groups):
    obj = assert_object(obj)
    for vertex_group in vertex_groups:
        obj.vertex_groups.remove(assert_vertex_group(obj, vertex_group))


def normalize_all_weights(context, obj):
    with OpenObject(context, obj, mode='WEIGHT_PAINT') as obj:
        bpy.ops.object.vertex_group_normalize_all()


def triangulate_object(context, obj):
    with OpenObject(context, obj, mode='OBJECT') as obj:
        me = obj.data
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()


class OpenObjects:
    def __init__(self, context, objects, mode='OBJECT'):
        self.mode = mode
        self.objects = [assert_object(obj) for obj in objects]
        self.context = context
        self.user_context = get_user_context(context)

    def __enter__(self):

        deselect_all_objects()
        
        for obj in self.objects:
            unhide_object(obj)
            select_object(obj)
            if obj.mode == 'EDIT':
                obj.update_from_editmode()
            
        set_active_object(bpy.context, self.objects[0])

        set_mode(self.context, mode=self.mode)

        return self.objects

    def __exit__(self, *args):
        set_user_context(self.context, self.user_context)


def assert_mesh(mesh):
    if isinstance(mesh, str):
        mesh = get_mesh(mesh)
    elif mesh not in bpy.data.meshes.values():
        raise ValueError('Not of mesh type: %s' % str(mesh))
    return mesh


def get_mesh(mesh_name):
    return bpy.data.meshes[mesh_name]


def remove_mesh(mesh):
    mesh = assert_mesh(mesh)
    bpy.data.meshes.remove(mesh, do_unlink=True)


def mesh_triangulate(me):
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()


def get_vertex_groups_from_bmesh(bm: bmesh.types.BMesh):
    layer_deform = bm.verts.layers.deform.active
    return [sorted(vert[layer_deform].items(), key=itemgetter(1), reverse=True) for vert in bm.verts]

def join_objects(context, objects):
    if len(objects) == 1:
        return
    unused_meshes = []
    with OpenObject(context, objects[0], mode='OBJECT'):
        for obj in objects[1:]:
            unused_meshes.append(obj.data)
            select_object(obj)  
            bpy.ops.object.join()
    for mesh in unused_meshes:
        remove_mesh(mesh)


def get_collection(col_name):
    return bpy.data.collections[col_name]


def get_layer_collection(col, layer_col=None):
    col_name = assert_collection(col).name
    if layer_col is None:
        #        layer_col = bpy.context.scene.collection
        layer_col = bpy.context.view_layer.layer_collection
    if layer_col.name == col_name:
        return layer_col
    for sublayer_col in layer_col.children:
        col = get_layer_collection(col_name, layer_col=sublayer_col)
        if col:
            return col


def collection_exists(col_name):
    return col_name in bpy.data.collections.keys()


def assert_collection(col):
    if isinstance(col, str):
        col = get_collection(col)
    elif col not in bpy.data.collections.values():
        raise ValueError('Not of collection type: %s' % str(col))
    return col


def get_collection_objects(col):
    col = assert_collection(col)
    return col.objects


def link_collection(col, col_parent):
    col = assert_collection(col)
    col_parent = assert_collection(col_parent)
    col_parent.children.link(col)


def new_collection(col_name, col_parent=None, allow_duplicate=True):
    if not allow_duplicate:
        try:
            col = get_collection(col_name)
            if col is not None:
                raise ValueError('Collection already exists: %s' % str(col_name))
        except Exception as e:
            pass
    new_col = bpy.data.collections.new(col_name)
    if col_parent:
        link_collection(new_col, col_parent)
    else:
        bpy.context.scene.collection.children.link(new_col)
    #    bpy.context.view_layer.layer_collection.children[col_name] = new_col
    #    bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[-1]
    #    bpy.context.scene.collection.children.link(new_col)
    return new_col


def hide_collection(col):
    col = assert_collection(col)
    #    col.hide_viewport = True
    #    for k, v in bpy.context.view_layer.layer_collection.children.items():
    #        print(k, " ", v)
    #    bpy.context.view_layer.layer_collection.children.get(col.name).hide_viewport = True
    get_layer_collection(col).hide_viewport = True


def unhide_collection(col):
    col = assert_collection(col)
    #    col.hide_viewport = False
    #    bpy.context.view_layer.layer_collection.children.get(col.name).hide_viewport = False
    get_layer_collection(col).hide_viewport = False


def collection_is_hidden(col):
    col = assert_collection(col)
    return get_layer_collection(col).hide_viewport


def get_scene_collections():
    return bpy.context.scene.collection.children


    
@dataclass
class TempObject:
    name: str
    object: bpy.types.Object
    vertex_count: int = 0
    index_count: int = 0
    index_offset: int = 0


@dataclass
class MergedObjectComponent:
    objects: List[TempObject]
    vertex_count: int = 0
    index_count: int = 0

@dataclass
class MergedObjectShapeKeys:
    vertex_count: int = 0


@dataclass
class MergedObject:
    object: bpy.types.Object
    mesh: bpy.types.Mesh
    components: List[MergedObjectComponent]
    shapekeys: MergedObjectShapeKeys
    vertex_count: int = 0
    index_count: int = 0
    vg_count: int = 0


class OpenObject:
    def __init__(self, context, obj, mode='OBJECT'):
        self.mode = mode
        self.object = assert_object(obj)
        self.context = context
        self.user_context = get_user_context(context)
        self.was_hidden = object_is_hidden(self.object)

    def __enter__(self):
        deselect_all_objects()

        unhide_object(self.object)
        select_object(self.object)
        set_active_object(bpy.context, self.object)

        if self.object.mode == 'EDIT':
            self.object.update_from_editmode()

        set_mode(self.context, mode=self.mode)

        return self.object

    def __exit__(self, *args):
        if self.was_hidden:
            hide_object(self.object)
        else:
            unhide_object(self.object)
        set_user_context(self.context, self.user_context)


class ObjUtils:

    @staticmethod
    def select_obj(target_obj:bpy.types.Object):
        # 假设 obj_copy 已经是你新建/复制的物体
        view_layer = bpy.context.view_layer

        # 1. 清空当前所有选中（可选，但通常需要）
        bpy.ops.object.select_all(action='DESELECT')

        # 2. 设活动对象
        view_layer.objects.active = target_obj

        # 3. 选中它
        target_obj.select_set(True)

        # 4. 强制刷新（某些模式下需要）
        view_layer.update()

    @staticmethod
    def get_obj_by_name(name: str) -> bpy.types.Object | None:
        """根据名称拿到 Object；找不到返回 None"""
        return bpy.data.objects.get(name)          # 等价于 bpy.data.objects[name]，但不会抛 KeyError
    
    @staticmethod
    def get_mesh_evaluate_from_obj(obj:bpy.types.Object) -> bpy.types.Mesh:
        '''
        Nico: 通过evaluated_get获取到的是一个新的mesh，用于导出，不影响原始Mesh
        '''
        return obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).to_mesh()

    @classmethod
    def split_obj_by_loose_parts_to_collection(cls,obj,collection_name:str):
        
        new_collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(new_collection)

        # 复制原对象并链接到新的集合
        obj_copy = obj.copy()
        obj_copy.data = obj.data.copy()
        new_collection.objects.link(obj_copy)
        
        # 取消原对象的选择状态
        obj.select_set(False)
        
        # 设置活动对象为副本，并进入编辑模式
        bpy.context.view_layer.objects.active = obj_copy
        obj_copy.select_set(True)  # 确保副本被选中
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 分离松散部分
        bpy.ops.mesh.separate(type='LOOSE')
        
        # 返回到对象模式
        bpy.ops.object.mode_set(mode='OBJECT')

        # 清理：取消副本的选择状态，以防影响后续操作
        obj_copy.select_set(False)

    @classmethod
    def merge_objects(cls,obj_list, target_collection=None):
        """
        合并给定的对象列表。
        
        :param obj_list: 要合并的对象列表
        :param target_collection: 目标集合，如果为None，则使用当前场景的活动集合
        """
        # 确保至少有一个对象可以进行合并
        if len(obj_list) < 1:
            print("没有足够的对象进行合并")
            return
        
        # 如果目标集合未指定，则使用当前场景的默认集合
        if target_collection is None:
            target_collection = bpy.context.collection
        
        # Deselect all objects
        bpy.ops.object.select_all(action='DESELECT')

        # Select and make one of the objects in the list active
        for obj in obj_list:
            obj.select_set(True)
            if obj.name in bpy.context.view_layer.objects:
                bpy.context.view_layer.objects.active = obj
        
        # Ensure the active object is set to one of the objects to be merged
        active_obj = bpy.context.view_layer.objects.active
        
        # Perform the join operation
        bpy.ops.object.join()

        # After joining, the result is a single object. We can rename it if needed.
        joined_obj = bpy.context.view_layer.objects.active
        joined_obj.name = "MeshObject"
        
        # Optionally move the merged object to the specified collection
        for col in joined_obj.users_collection:
            col.objects.unlink(joined_obj)
        target_collection.objects.link(joined_obj)

    @classmethod
    def normalize_all(cls,obj):
        # 调用前需确保选中了这个obj，也就是当前的active对象是这个obj
        cls.select_obj(obj)

        # print("Normalize All Weights For: " + obj.name)
        # 选择你要操作的对象，这里假设场景中只有一个导入的OBJ对象
        if obj and obj.type == 'MESH':
            # 进入权重编辑模式（如果需要）
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            
            # 确保该对象是活动的，并且被选中
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            
            # 对所有顶点组应用 Normalize All
            bpy.ops.object.vertex_group_normalize_all()

            # 回到物体模式
            bpy.ops.object.mode_set(mode='OBJECT')
        else:
            print("没有找到合适的网格对象来执行规范化操作。")

    @classmethod
    def mesh_triangulate(cls,me:bpy.types.Mesh):
        '''
        三角化一个mesh
        注意这个三角化之后就变成新的mesh了
        '''
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.triangulate(bm, faces=bm.faces)
        bm.to_mesh(me)
        bm.free()

    @classmethod
    def get_bpy_context_object(cls):
        '''
        获取当前场景中的obj对象,如果为None则抛出Fatal异常
        '''
        obj = bpy.context.object
        if obj is None:
            # 为空时不导出
            raise Fatal('No object selected')
        
        return obj

    @classmethod
    def selected_obj_delete_loose(cls):
        
        # 获取当前选中的对象
        selected_objects = bpy.context.selected_objects
        # 检查是否选中了一个Mesh对象
        for obj in selected_objects:
            if obj.type == 'MESH':
                # 设置当前对象为活动对象 （不设置的话后面没法切换编辑模式，就会报错）
                bpy.context.view_layer.objects.active = obj
                # 获取选中的网格对象
                bpy.ops.object.mode_set(mode='EDIT')
                # 选择所有的顶点
                bpy.ops.mesh.select_all(action='SELECT')
                # 执行删除孤立顶点操作
                bpy.ops.mesh.delete_loose()
                # 切换回对象模式
                bpy.ops.object.mode_set(mode='OBJECT')

    @classmethod
    def is_contains_locked_weights(cls,obj):
        locked_groups = []
        # 确保对象类型为MESH，因为只有这种类型的对象才有顶点组
        if obj.type == 'MESH':
            # 遍历对象的所有顶点组
            for vg in obj.vertex_groups:
                # 如果顶点组被锁定，则添加到列表中
                if vg.lock_weight:
                    locked_groups.append(vg.name)
        if len(locked_groups) != 0:
            return True
        else:
            return False
        
    @classmethod
    def is_all_vertex_groups_locked(cls,obj):
        '''
        判断是否所有的顶点组都被锁定了，因为所有的顶点组都被锁定的话就无法对权重执行Normalize All了
        '''
        vgs_number = 0
        locked_groups = []
        # 确保对象类型为MESH，因为只有这种类型的对象才有顶点组
        if obj.type == 'MESH':
            # 遍历对象的所有顶点组
            for vg in obj.vertex_groups:
                vgs_number = vgs_number + 1
                # 如果顶点组被锁定，则添加到列表中
                if vg.lock_weight:
                    locked_groups.append(vg.name)
        if len(locked_groups) == vgs_number:
            return True
        else:
            return False

    @classmethod
    def copy_object(cls,context, obj, name=None, collection=None):
        '''
        collection指的是复制后链接到哪个collection里
        '''
        with OpenObject(context, obj, mode='OBJECT') as obj:
            new_obj = obj.copy()
            new_obj.data = obj.data.copy()
            if name:
                rename_object(new_obj, name)
            if collection:
                link_object_to_collection(new_obj, collection)
            return new_obj
    
    
    @classmethod
    def reset_obj_rotation(cls,obj):
        if obj.type == "MESH":
            # 将旋转角度归零
            obj.rotation_euler[0] = 0.0  # X轴
            obj.rotation_euler[1] = 0.0  # Y轴
            obj.rotation_euler[2] = 0.0  # Z轴

    @classmethod
    def reset_obj_location(cls, obj):
        if obj.type == "MESH":
            # 将位置归零
            obj.location[0] = 0.0  # X轴
            obj.location[1] = 0.0  # Y轴
            obj.location[2] = 0.0  # Z轴
