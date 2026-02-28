# -*- coding: utf-8 -*-
import bpy
import bmesh
import re
import time
from bpy.types import PropertyGroup
from mathutils import Vector, kdtree

from .blueprint_node_base import SSMTNodeBase

_keymaps = []


class SSMTNode_VertexGroupMatch(SSMTNodeBase):
    '''顶点组名称匹配节点：基于位置匹配源物体和目标物体的顶点组，生成映射表'''
    bl_idname = 'SSMTNode_VertexGroupMatch'
    bl_label = '顶点组匹配'
    bl_description = '基于位置匹配源物体和目标物体的顶点组，生成映射表保存到文本编辑器'
    bl_icon = 'GROUP'
    bl_width_min = 300

    source_object: bpy.props.StringProperty(
        name="源物体",
        description="源物体名称",
        default=""
    )

    target_object: bpy.props.StringProperty(
        name="目标物体",
        description="目标物体名称",
        default=""
    )

    match_threshold: bpy.props.FloatProperty(
        name="匹配阈值",
        description="顶点组中心位置的匹配距离阈值",
        default=0.01,
        min=0.001,
        max=1.0
    )

    use_shape_key: bpy.props.BoolProperty(
        name="使用形态键",
        description="计算顶点组中心时考虑形态键变形",
        default=False
    )

    create_debug_objects: bpy.props.BoolProperty(
        name="创建调试物体",
        description="创建调试物体和连接线用于可视化匹配结果",
        default=True
    )

    rename_format: bpy.props.BoolProperty(
        name="重命名格式",
        description="使用 源名称=目标名称 格式",
        default=True
    )

    target_hash: bpy.props.StringProperty(
        name="目标哈希",
        description="应用此映射表的物体哈希标识（物体名称以'哈希-'开头时匹配），留空则应用于所有物体",
        default=""
    )

    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="顶点组匹配设置", icon='GROUP')
        
        row = box.row()
        row.prop_search(self, "source_object", bpy.data, "objects", text="源物体")
        
        row = box.row()
        row.prop_search(self, "target_object", bpy.data, "objects", text="目标物体")
        
        row = box.row()
        row.prop(self, "match_threshold")
        
        row = box.row()
        row.prop(self, "use_shape_key")
        
        row = box.row()
        row.prop(self, "create_debug_objects")
        
        row = box.row()
        row.prop(self, "rename_format")
        
        row = box.row()
        row.prop(self, "target_hash")
        
        layout.separator()
        row = layout.row(align=True)
        row.operator("ssmt.vertex_group_match_execute", text="执行匹配", icon='PLAY')
        row.operator("ssmt.vertex_group_match_clear", text="清除映射", icon='X')
        
        layout.separator()
        row = layout.row(align=True)
        row.operator("ssmt.vertex_group_match_sync", text="同步选中", icon='LINKED')
        row.operator("ssmt.vertex_group_match_delete_connection", text="删除连接", icon='X')
        
        layout.separator()
        row = layout.row(align=True)
        row.operator("ssmt.vertex_group_match_detect_multi", text="检测多连接", icon='VIEWZOOM')
        
        layout.separator()
        box = layout.box()
        box.label(text="快捷键:", icon='KEYINGSET')
        box.label(text="手动同步: Ctrl+Shift+Z")
        box.label(text="快速权重: Alt+W")

    def get_deformed_vertices(self, context, obj):
        """获取经过骨骼和形态键变换后的顶点世界坐标"""
        if not obj or obj.type != 'MESH':
            return None
        
        depsgraph = context.evaluated_depsgraph_get()
        eval_obj = obj.evaluated_get(depsgraph)
        
        if not eval_obj or not eval_obj.data:
            return None
        
        vertices = []
        for vert in eval_obj.data.vertices:
            world_pos = eval_obj.matrix_world @ vert.co
            vertices.append(world_pos)
        
        return vertices

    def get_vertex_group_centers(self, context, obj, deformed_vertices=None):
        """获取物体所有顶点组的中心位置"""
        if not obj or obj.type != 'MESH':
            return {}

        mesh = obj.data
        group_centers = {}
        group_counts = {}

        for vg in obj.vertex_groups:
            original_name, _ = self.parse_vg_name(vg.name)
            group_centers[original_name] = Vector((0, 0, 0))
            group_counts[original_name] = 0

        for i, vert in enumerate(mesh.vertices):
            global_pos = deformed_vertices[i] if deformed_vertices else obj.matrix_world @ vert.co
            for vgroup in vert.groups:
                try:
                    vg = obj.vertex_groups[vgroup.group]
                    original_vg_name, _ = self.parse_vg_name(vg.name)
                    weight = vgroup.weight
                    if weight > 0 and original_vg_name in group_centers:
                        group_centers[original_vg_name] += global_pos * weight
                        group_counts[original_vg_name] += weight
                except (IndexError, RuntimeError):
                    continue

        result = {}
        for name, center in group_centers.items():
            if group_counts[name] > 0:
                result[name] = {'center': center / group_counts[name]}
        return result

    def parse_vg_name(self, name):
        """解析顶点组名称"""
        if self.rename_format and "=" in name:
            parts = name.split("=", 1)
            return parts[0].strip(), parts[1].strip()
        return name, name

    def create_debug_object(self, name, location, parent, is_connected=False):
        """创建调试物体"""
        is_source = name.startswith("Source_")

        if is_source:
            mesh = bpy.data.meshes.new(name + "_mesh")
            bm = bmesh.new()
            
            if is_connected:
                bmesh.ops.create_cube(bm, size=0.005)
                mat_name, color = "VGTP_Debug_Blue", (0.0, 0.2, 1.0, 1.0)
            else:
                bmesh.ops.create_cube(bm, size=0.006)
                mat_name, color = "VGTP_Debug_Green", (0.0, 1.0, 0.2, 1.0)
                
            bm.to_mesh(mesh)
            bm.free()
        else:
            mesh = bpy.data.meshes.new(name + "_mesh")
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=8, radius=(0.005 / 2))
            bm.to_mesh(mesh)
            bm.free()
            mat_name, color = "VGTP_Debug_Yellow", (1.0, 1.0, 0.0, 1.0)

        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            mat.diffuse_color = color

        debug_obj = bpy.data.objects.new(name, mesh)
        debug_obj.location = location
        debug_obj.data.materials.append(mat)
        debug_obj.parent = parent
        debug_obj["original_vg_name"] = name.split('_', 1)[1]
        debug_obj["is_connected"] = is_connected
        debug_obj.show_name = True
        bpy.context.scene.collection.objects.link(debug_obj)
        return debug_obj

    def create_match_curves(self, source_centers, target_centers, rename_map, parent, one_to_many_connections=None, target_to_sources=None):
        """创建匹配连接线"""
        if one_to_many_connections is None:
            one_to_many_connections = {}
        if target_to_sources is None:
            target_to_sources = {}
        
        for src_name, src_data in source_centers.items():
            if src_name in rename_map:
                new_name = rename_map[src_name]
                target_name = new_name
                if self.rename_format and "=" in new_name:
                    target_name = new_name.split("=", 1)[1].strip()

                if target_name in target_centers:
                    src_center = src_data['center']
                    target_center = target_centers[target_name]['center']

                    curve_data = bpy.data.curves.new(f"Match_{src_name}_to_{target_name}", 'CURVE')
                    curve_data.dimensions = '3D'
                    curve_data.bevel_depth = 0.001
                    curve_data.bevel_resolution = 2

                    polyline = curve_data.splines.new('POLY')
                    polyline.points.add(1)
                    polyline.points[0].co = (*src_center, 1)
                    polyline.points[1].co = (*target_center, 1)

                    curve_obj = bpy.data.objects.new(f"Match_{src_name}_to_{target_name}", curve_data)
                    curve_obj.parent = parent
                    
                    is_one_to_many = src_name in one_to_many_connections and len(one_to_many_connections[src_name]) > 1
                    
                    if is_one_to_many:
                        mat_name = "VGTP_Debug_Red_Error"
                        mat = bpy.data.materials.get(mat_name)
                        if not mat:
                            mat = bpy.data.materials.new(name=mat_name)
                            mat.diffuse_color = (1.0, 0.0, 0.0, 1.0)
                        curve_obj.data.materials.clear()
                        curve_obj.data.materials.append(mat)
                        curve_obj["is_one_to_many_connection"] = True
                        curve_obj["connected_targets"] = str(one_to_many_connections[src_name])
                    else:
                        mat_name = "VGTP_Debug_White_Normal"
                        mat = bpy.data.materials.get(mat_name)
                        if not mat:
                            mat = bpy.data.materials.new(name=mat_name)
                            mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
                        curve_obj.data.materials.clear()
                        curve_obj.data.materials.append(mat)
                        curve_obj["is_one_to_many_connection"] = False
                    
                    bpy.context.scene.collection.objects.link(curve_obj)

    def optimize_matching(self, target_centers):
        """构建KD树优化匹配"""
        size = len(target_centers)
        kd = kdtree.KDTree(size)
        positions = []
        for i, (name, data) in enumerate(target_centers.items()):
            kd.insert(data['center'], i)
            positions.append((name, data['center']))
        kd.balance()
        return kd, positions

    def execute_match(self, context):
        """执行顶点组匹配"""
        source_obj = bpy.data.objects.get(self.source_object)
        target_obj = bpy.data.objects.get(self.target_object)

        if not source_obj or not target_obj:
            return None, "请同时指定源物体和目标物体"
        
        if source_obj.type != 'MESH' or target_obj.type != 'MESH':
            return None, "源和目标都必须是网格物体"

        debug_parent = None
        if self.create_debug_objects:
            parent_name = f"Debug_Match_{source_obj.name}_to_{target_obj.name}_{int(time.time())}"
            debug_parent = bpy.data.objects.new(parent_name, None)
            context.scene.collection.objects.link(debug_parent)
            debug_parent["vgtp_source_name"] = source_obj.name
            debug_parent["vgtp_target_name"] = target_obj.name

        source_deformed_data = self.get_deformed_vertices(context, source_obj) if self.use_shape_key else None
        target_deformed_data = self.get_deformed_vertices(context, target_obj) if self.use_shape_key else None
        
        source_centers = self.get_vertex_group_centers(context, source_obj, source_deformed_data)
        target_centers = self.get_vertex_group_centers(context, target_obj, target_deformed_data)

        if not source_centers or not target_centers:
            if debug_parent: 
                bpy.data.objects.remove(debug_parent, do_unlink=True)
            return None, "物体缺少有效的顶点组"

        source_debug_objects = {}
        if self.create_debug_objects:
            for name, data in source_centers.items():
                debug_obj = self.create_debug_object(f"Source_{name}", data['center'], debug_parent, is_connected=False)
                source_debug_objects[name] = debug_obj
                
            for name, data in target_centers.items():
                self.create_debug_object(f"Target_{name}", data['center'], debug_parent, is_connected=False)

        kd_tree, positions = self.optimize_matching(target_centers)
        rename_map = {}
        target_to_sources = {}
        matched_count = 0
        
        for src_name, src_data in source_centers.items():
            src_center = src_data['center']
            found_targets = kd_tree.find_range(src_center, self.match_threshold)
            
            if found_targets:
                _, index, _ = found_targets[0]
                closest_name = positions[index][0]
                new_name = f"{src_name}={closest_name}" if self.rename_format else closest_name
                rename_map[src_name] = new_name
                matched_count += 1
                
                if closest_name not in target_to_sources:
                    target_to_sources[closest_name] = []
                target_to_sources[closest_name].append(src_name)
                
                if self.create_debug_objects and src_name in source_debug_objects:
                    source_debug_objects[src_name]["is_connected"] = True
                    mat_name = "VGTP_Debug_Blue"
                    mat = bpy.data.materials.get(mat_name)
                    if not mat:
                        mat = bpy.data.materials.new(name=mat_name)
                        mat.diffuse_color = (0.0, 0.2, 1.0, 1.0)
                    source_debug_objects[src_name].data.materials.clear()
                    source_debug_objects[src_name].data.materials.append(mat)

        if self.create_debug_objects and matched_count > 0:
            one_to_many_connections = {}
            self.create_match_curves(source_centers, target_centers, rename_map, debug_parent, one_to_many_connections, target_to_sources)
            
            many_to_one_count = 0
            for target_name, sources in target_to_sources.items():
                if len(sources) > 1:
                    many_to_one_count += 1

        text_name = f"VG_Match_{source_obj.name}_to_{target_obj.name}"
        
        if text_name in bpy.data.texts:
            text = bpy.data.texts[text_name]
            text.clear()
        else:
            text = bpy.data.texts.new(text_name)

        text.write(f"# 顶点组名称映射表\n")
        text.write(f"# 源物体: {source_obj.name}\n")
        text.write(f"# 目标物体: {target_obj.name}\n")
        text.write(f"# 匹配阈值: {self.match_threshold}\n")
        text.write(f"# 匹配时间: {int(time.time())}\n")
        text.write(f"# 成功匹配: {matched_count}/{len(source_centers)}\n")
        text.write(f"# 格式: 源名称=目标名称\n")

        for src_name, tgt_name in rename_map.items():
            if self.rename_format and "=" in tgt_name:
                text.write(f"{tgt_name}\n")
            else:
                text.write(f"{src_name}={tgt_name}\n")

        for src_name in source_centers:
            if src_name not in rename_map:
                text.write(f"# 未匹配: {src_name}\n")

        return rename_map, f"匹配完成！成功匹配 {matched_count}/{len(source_centers)} 个顶点组，映射表已保存到: {text_name}"


class SSMT_OT_VertexGroupMatchExecute(bpy.types.Operator):
    '''执行顶点组匹配'''
    bl_idname = "ssmt.vertex_group_match_execute"
    bl_label = "执行顶点组匹配"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space_data = getattr(context, "space_data", None)
        return space_data and space_data.type == 'NODE_EDITOR'

    def execute(self, context):
        selected_nodes = [node for node in context.selected_nodes if node.bl_idname == 'SSMTNode_VertexGroupMatch']
        
        if not selected_nodes:
            self.report({'WARNING'}, "请选中顶点组匹配节点")
            return {'CANCELLED'}
        
        node = selected_nodes[0]
        rename_map, message = node.execute_match(context)
        
        if rename_map is None:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        
        self.report({'INFO'}, message)
        return {'FINISHED'}


class SSMT_OT_VertexGroupMatchClear(bpy.types.Operator):
    '''清除顶点组映射表和调试物体'''
    bl_idname = "ssmt.vertex_group_match_clear"
    bl_label = "清除顶点组映射表"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space_data = getattr(context, "space_data", None)
        return space_data and space_data.type == 'NODE_EDITOR'

    def execute(self, context):
        selected_nodes = [node for node in context.selected_nodes if node.bl_idname == 'SSMTNode_VertexGroupMatch']
        
        if not selected_nodes:
            self.report({'WARNING'}, "请选中顶点组匹配节点")
            return {'CANCELLED'}
        
        node = selected_nodes[0]
        source_obj = bpy.data.objects.get(node.source_object)
        target_obj = bpy.data.objects.get(node.target_object)
        
        if source_obj and target_obj:
            text_name = f"VG_Match_{source_obj.name}_to_{target_obj.name}"
            
            debug_parent_prefix = f"Debug_Match_{source_obj.name}_to_{target_obj.name}"
            debug_objects_to_remove = []
            for obj in bpy.data.objects:
                if obj.name.startswith(debug_parent_prefix):
                    debug_objects_to_remove.append(obj)
            
            for debug_parent in debug_objects_to_remove:
                children_to_remove = list(debug_parent.children)
                for child in children_to_remove:
                    bpy.data.objects.remove(child, do_unlink=True)
                bpy.data.objects.remove(debug_parent, do_unlink=True)
            
            if text_name in bpy.data.texts:
                text = bpy.data.texts[text_name]
                bpy.data.texts.remove(text)
                self.report({'INFO'}, f"已清除映射表和调试物体: {text_name}")
            else:
                self.report({'INFO'}, f"已清除调试物体")
        else:
            self.report({'WARNING'}, "请先设置源物体和目标物体")
        
        return {'FINISHED'}


def find_debug_info(source_empty):
    """从调试物体查找关联的源物体、目标物体和调试父级"""
    debug_parent = source_empty.parent
    if not debug_parent:
        return None, None, None
    
    source_obj_name = debug_parent.get("vgtp_source_name")
    target_obj_name = debug_parent.get("vgtp_target_name")
    
    source_obj = bpy.data.objects.get(source_obj_name) if source_obj_name else None
    target_obj = bpy.data.objects.get(target_obj_name) if target_obj_name else None
    
    return source_obj, target_obj, debug_parent


class SSMT_OT_VertexGroupMatchSync(bpy.types.Operator):
    '''同步选中的顶点组关联到映射表'''
    bl_idname = "ssmt.vertex_group_match_sync"
    bl_label = "同步选中的顶点组关联"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return len(context.selected_objects) >= 2

    def find_mapping_text(self, source_obj_name, target_obj_name):
        """查找对应的映射表文本"""
        text_name = f"VG_Match_{source_obj_name}_to_{target_obj_name}"
        return bpy.data.texts.get(text_name)

    def update_mapping_text(self, text, source_vg_name, target_vg_name):
        """更新映射表中的条目 - 根据源名称找到对应行，替换等号后的目标名称"""
        lines = []
        found = False
        
        for line in text.lines:
            body = line.body.rstrip('\n\r')
            
            if not body.strip():
                continue
            
            if body.startswith('#'):
                if '未匹配:' in body and source_vg_name in body:
                    lines.append(f"{source_vg_name}={target_vg_name}")
                    found = True
                else:
                    lines.append(body)
                continue
            
            if '=' in body:
                parts = body.split('=', 1)
                src_name = parts[0].strip()
                if src_name == source_vg_name:
                    lines.append(f"{source_vg_name}={target_vg_name}")
                    found = True
                else:
                    lines.append(body)
            else:
                lines.append(body)
        
        if not found:
            lines.append(f"{source_vg_name}={target_vg_name}")
        
        text.clear()
        for line in lines:
            text.write(line + '\n')

    def execute(self, context):
        selected_objects = context.selected_objects

        source_empties = []
        target_empties = []
        for obj in selected_objects:
            if obj.name.startswith("Source_"):
                source_empties.append(obj)
            elif obj.name.startswith("Target_"):
                target_empties.append(obj)

        if not source_empties or not target_empties:
            self.report({'ERROR'}, "请选择至少一个源调试物体（绿色）和一个目标调试物体（黄色）")
            return {'CANCELLED'}

        target_empty = target_empties[0]
        target_vg_name = target_empty.get("original_vg_name")
        if not target_vg_name:
            self.report({'ERROR'}, "选择的目标调试物体缺少原始顶点组名称信息")
            return {'CANCELLED'}

        debug_parent = source_empties[0].parent
        if not debug_parent:
            self.report({'ERROR'}, "无法确定调试父级")
            return {'CANCELLED'}

        source_obj_name = debug_parent.get("vgtp_source_name")
        target_obj_name = debug_parent.get("vgtp_target_name")
        
        source_obj = bpy.data.objects.get(source_obj_name) if source_obj_name else None
        if not source_obj:
            self.report({'ERROR'}, "无法确定关联的源物体")
            return {'CANCELLED'}

        mapping_text = self.find_mapping_text(source_obj_name, target_obj_name)
        if not mapping_text:
            mapping_text = bpy.data.texts.new(f"VG_Match_{source_obj_name}_to_{target_obj_name}")
            mapping_text.write(f"# 顶点组名称映射表\n")
            mapping_text.write(f"# 源物体: {source_obj_name}\n")
            mapping_text.write(f"# 目标物体: {target_obj_name}\n")
            mapping_text.write(f"# 格式: 源名称=目标名称\n")

        for src in source_empties:
            if src.parent != debug_parent:
                self.report({'ERROR'}, "所有源调试物体必须属于同一个匹配分块")
                return {'CANCELLED'}

        mat_name = "VGTP_Debug_Blue"
        mat = bpy.data.materials.get(mat_name)
        if not mat:
            mat = bpy.data.materials.new(name=mat_name)
            mat.diffuse_color = (0.0, 0.2, 1.0, 1.0)

        success_count = 0
        for source_empty in source_empties:
            source_vg_name = source_empty.get("original_vg_name")
            if not source_vg_name:
                continue

            self.update_mapping_text(mapping_text, source_vg_name, target_vg_name)

            old_curve_name_prefix = f"Match_{source_vg_name}_"
            for child in debug_parent.children:
                if child.type == 'CURVE' and child.name.startswith(old_curve_name_prefix):
                    bpy.data.objects.remove(child, do_unlink=True)
                    break

            src_loc, tgt_loc = source_empty.location, target_empty.location
            curve_data = bpy.data.curves.new(f"Match_{source_vg_name}_to_{target_vg_name}", 'CURVE')
            curve_data.dimensions = '3D'
            curve_data.bevel_depth = 0.001
            curve_data.bevel_resolution = 2
            polyline = curve_data.splines.new('POLY')
            polyline.points.add(1)
            polyline.points[0].co = (*src_loc, 1)
            polyline.points[1].co = (*tgt_loc, 1)
            curve_obj = bpy.data.objects.new(f"Match_{source_vg_name}_to_{target_vg_name}", curve_data)
            curve_obj.parent = debug_parent
            context.scene.collection.objects.link(curve_obj)
            
            mat_white_name = "VGTP_Debug_White_Normal"
            mat_white = bpy.data.materials.get(mat_white_name)
            if not mat_white:
                mat_white = bpy.data.materials.new(name=mat_white_name)
                mat_white.diffuse_color = (1.0, 1.0, 1.0, 1.0)
            curve_obj.data.materials.clear()
            curve_obj.data.materials.append(mat_white)

            source_empty["is_connected"] = True
            source_empty.data.materials.clear()
            source_empty.data.materials.append(mat)
            success_count += 1

        self.report({'INFO'}, f"成功同步 {success_count} 个顶点组关联到映射表: {mapping_text.name}")
        return {'FINISHED'}


class SSMT_OT_VertexGroupMatchDeleteConnection(bpy.types.Operator):
    '''删除连接线并更新映射表'''
    bl_idname = "ssmt.vertex_group_match_delete_connection"
    bl_label = "删除连接线"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        selected_objects = context.selected_objects
        return any(obj.type == 'CURVE' and obj.name.startswith("Match_") for obj in selected_objects)

    def find_mapping_text(self, source_obj_name, target_obj_name):
        """查找对应的映射表文本"""
        text_name = f"VG_Match_{source_obj_name}_to_{target_obj_name}"
        return bpy.data.texts.get(text_name)

    def remove_from_mapping_text(self, text, source_vg_name):
        """从映射表中移除条目"""
        lines = []
        
        for line in text.lines:
            body = line.body.rstrip('\n\r')
            
            if not body.strip():
                continue
            
            if body.startswith('#'):
                lines.append(body)
                continue
            
            if '=' in body:
                parts = body.split('=', 1)
                src_name = parts[0].strip()
                if src_name == source_vg_name:
                    lines.append(f"# 已删除: {source_vg_name}")
                else:
                    lines.append(body)
            else:
                lines.append(body)
        
        text.clear()
        for line in lines:
            text.write(line + '\n')

    def execute(self, context):
        selected_objects = context.selected_objects
        match_curves = [obj for obj in selected_objects if obj.type == 'CURVE' and obj.name.startswith("Match_")]
        
        if not match_curves:
            self.report({'ERROR'}, "请选择至少一个Match_开头的连接线")
            return {'CANCELLED'}

        deleted_count = 0
        
        for active_obj in match_curves:
            match_result = re.match(r"Match_(.+?)_to_(.+)", active_obj.name)
            if not match_result:
                continue

            source_vg_name = match_result.group(1)
            
            source_empty_name = f"Source_{source_vg_name}"
            source_empty = bpy.data.objects.get(source_empty_name)
            
            if source_empty:
                source_empty["is_connected"] = False
                mat_name = "VGTP_Debug_Green"
                mat = bpy.data.materials.get(mat_name)
                if not mat:
                    mat = bpy.data.materials.new(name=mat_name)
                    mat.diffuse_color = (0.0, 1.0, 0.2, 1.0)
                source_empty.data.materials.clear()
                source_empty.data.materials.append(mat)
                
                source_obj, target_obj, debug_parent = find_debug_info(source_empty)
                if debug_parent:
                    source_obj_name = debug_parent.get("vgtp_source_name")
                    target_obj_name = debug_parent.get("vgtp_target_name")
                    mapping_text = self.find_mapping_text(source_obj_name, target_obj_name)
                    if mapping_text:
                        self.remove_from_mapping_text(mapping_text, source_vg_name)
            
            bpy.data.objects.remove(active_obj)
            deleted_count += 1
        
        self.report({'INFO'}, f"已删除 {deleted_count} 条连接线，映射表已更新")
        return {'FINISHED'}


class SSMT_OT_VertexGroupMatchDetectMulti(bpy.types.Operator):
    '''检测多分块连接'''
    bl_idname = "ssmt.vertex_group_match_detect_multi"
    bl_label = "检测多分块连接"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'WARNING'}, "请先选择Debug_Match_开头的匹配分块物体")
            return {'CANCELLED'}
            
        match_blocks = []
        for obj in selected_objects:
            if obj.name.startswith("Debug_Match_"):
                match_blocks.append(obj)
        
        if not match_blocks:
            self.report({'WARNING'}, "请选择名称以'Debug_Match_'开头的匹配分块物体")
            return {'CANCELLED'}
            
        all_match_curves = []
        for block in match_blocks:
            for child in block.children:
                if child.type == 'CURVE' and child.name.startswith("Match_"):
                    all_match_curves.append(child)
            
            if block.type == 'CURVE' and block.name.startswith("Match_"):
                all_match_curves.append(block)
        
        if not all_match_curves:
            self.report({'WARNING'}, "在选中的匹配分块中未找到Match_开头的连接线")
            return {'CANCELLED'}
            
        source_to_targets = {}
        
        for curve in all_match_curves:
            try:
                name_part = curve.name.replace("Match_", "")
                parts = name_part.split("_to_")
                if len(parts) == 2:
                    source_vg = parts[0]
                    target_vg = parts[1]
                    
                    source_vg_clean = source_vg
                    target_vg_clean = re.sub(r'\.\d+$', '', target_vg) if '.' in target_vg else target_vg
                    
                    if source_vg_clean not in source_to_targets:
                        source_to_targets[source_vg_clean] = []
                    if target_vg_clean not in source_to_targets[source_vg_clean]:
                        source_to_targets[source_vg_clean].append(target_vg_clean)
            except Exception as e:
                self.report({'WARNING'}, f"解析连接线名称失败: {curve.name}, 错误: {str(e)}")
                return {'CANCELLED'}
        
        multi_connections = {}
        for source_vg, target_vgs in source_to_targets.items():
            if len(target_vgs) > 1:
                multi_connections[source_vg] = target_vgs
        
        target_to_sources = {}
        for source_vg, target_vgs in source_to_targets.items():
            for target_vg in target_vgs:
                if target_vg not in target_to_sources:
                    target_to_sources[target_vg] = []
                target_to_sources[target_vg].append(source_vg)
        
        reverse_multi_connections = {}
        for target_vg, source_vgs in target_to_sources.items():
            if len(source_vgs) > 1:
                reverse_multi_connections[target_vg] = source_vgs
        
        white_mat_name = "VGTP_Debug_White_Normal"
        white_mat = bpy.data.materials.get(white_mat_name)
        if not white_mat:
            white_mat = bpy.data.materials.new(name=white_mat_name)
            white_mat.diffuse_color = (1.0, 1.0, 1.0, 1.0)
            
        for curve in all_match_curves:
            curve.data.materials.clear()
            curve.data.materials.append(white_mat)
            if "is_multi_connection" in curve:
                del curve["is_multi_connection"]
        
        has_multi_connections = False
        for source_vg_clean, target_vgs_clean in multi_connections.items():
            for target_vg_clean in target_vgs_clean:
                for curve in all_match_curves:
                    try:
                        name_part = curve.name.replace("Match_", "")
                        parts = name_part.split("_to_")
                        if len(parts) == 2:
                            source_vg = parts[0]
                            target_vg = parts[1]
                            
                            source_vg_current = source_vg
                            target_vg_current = re.sub(r'\.\d+$', '', target_vg) if '.' in target_vg else target_vg
                            
                            if source_vg_current == source_vg_clean and target_vg_current == target_vg_clean:
                                mat_name = "VGTP_Debug_Red_Error"
                                mat = bpy.data.materials.get(mat_name)
                                if not mat:
                                    mat = bpy.data.materials.new(name=mat_name)
                                    mat.diffuse_color = (1.0, 0.0, 0.0, 1.0)
                                curve.data.materials.clear()
                                curve.data.materials.append(mat)
                                curve["is_multi_connection"] = True
                                has_multi_connections = True
                                break
                    except Exception:
                        continue
        
        message_parts = []
        
        if multi_connections:
            message_parts.append("检测到以下源顶点组连接多个目标顶点组（已标红）:")
            for src_name, targets in multi_connections.items():
                message_parts.append(f"- {src_name} 连接到: {', '.join(targets)}")
        
        if reverse_multi_connections:
            message_parts.append("检测到以下目标顶点组被多个源顶点组连接:")
            for target_name, sources in reverse_multi_connections.items():
                message_parts.append(f"- {target_name} 被 {', '.join(sources)} 连接")
        
        if not message_parts:
            self.report({'INFO'}, f"在选中的{len(match_blocks)}个匹配分块中的{len(all_match_curves)}条连接线中未检测到多分块连接情况")
        else:
            full_message = "\n".join(message_parts)
            self.report({'INFO'}, full_message)
            
        return {'FINISHED'}


class SSMT_OT_VertexGroupMatchQuickWeight(bpy.types.Operator):
    '''快速权重绘制 (切换)'''
    bl_idname = "ssmt.vertex_group_match_quick_weight"
    bl_label = "快速权重绘制 (切换)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        active_obj = context.active_object
        if active_obj is None:
            return False
        if active_obj.type == 'CURVE' and active_obj.name.startswith("Match_"):
            return True
        return True

    def execute(self, context):
        active_obj = context.active_object

        if active_obj and active_obj.mode == 'WEIGHT_PAINT':
            obj_to_exit = active_obj
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            
            if obj_to_exit.get("vgtp_is_temp_merge"):
                bpy.data.objects.remove(obj_to_exit, do_unlink=True)
            else:
                obj_to_exit.hide_set(True)
            return {'FINISHED'}

        if active_obj.type == 'CURVE' and active_obj.name.startswith("Match_"):
            active_curve = active_obj

            match = re.match(r"Match_(.+?)_to_(.+)", active_curve.name)
            if not match:
                self.report({'ERROR'}, "连接线名称格式不正确")
                return {'CANCELLED'}

            source_vg_name = match.group(1)
            target_vg_name = match.group(2)
            temp_mesh_name = f"Temp_Merge_{source_vg_name}_{target_vg_name}"
            
            existing_temp_obj = bpy.data.objects.get(temp_mesh_name)
            
            if existing_temp_obj and existing_temp_obj.get("vgtp_is_temp_merge"):
                bpy.data.objects.remove(existing_temp_obj, do_unlink=True)
            
            source_empty_name = f"Source_{source_vg_name}"
            target_empty_name = f"Target_{target_vg_name}"

            source_empty = bpy.data.objects.get(source_empty_name)
            target_empty = bpy.data.objects.get(target_empty_name)

            if not source_empty or not target_empty:
                self.report({'ERROR'}, "无法找到关联的源或目标调试物体")
                return {'CANCELLED'}

            source_obj, target_obj, debug_parent = find_debug_info(source_empty)
            if not source_obj or not target_obj:
                self.report({'ERROR'}, "无法找到关联的源或目标物体")
                return {'CANCELLED'}

            source_vg = None
            for vg in source_obj.vertex_groups:
                if "=" in vg.name:
                    original_name = vg.name.split("=", 1)[0].strip()
                else:
                    original_name = vg.name
                
                if original_name == source_vg_name:
                    source_vg = vg
                    break

            target_vg = target_obj.vertex_groups.get(target_vg_name)

            if not source_vg:
                self.report({'ERROR'}, f"无法在源物体上找到顶点组: {source_vg_name}")
                return {'CANCELLED'}

            if not target_vg:
                self.report({'ERROR'}, f"无法在目标物体上找到顶点组: {target_vg_name}")
                return {'CANCELLED'}

            temp_mesh = bpy.data.meshes.new(temp_mesh_name)
            temp_obj = bpy.data.objects.new(temp_mesh_name, temp_mesh)
            context.scene.collection.objects.link(temp_obj)
            
            source_mesh = source_obj.data
            temp_mesh.vertices.add(len(source_mesh.vertices))
            temp_mesh.edges.add(len(source_mesh.edges))
            temp_mesh.loops.add(len(source_mesh.loops))
            temp_mesh.polygons.add(len(source_mesh.polygons))
            
            for i, vert in enumerate(source_mesh.vertices):
                temp_mesh.vertices[i].co = vert.co
            
            for i, edge in enumerate(source_mesh.edges):
                temp_mesh.edges[i].vertices = edge.vertices
            
            for i, loop in enumerate(source_mesh.loops):
                temp_mesh.loops[i].vertex_index = loop.vertex_index
                temp_mesh.loops[i].edge_index = loop.edge_index
            
            for i, poly in enumerate(source_mesh.polygons):
                temp_mesh.polygons[i].loop_start = poly.loop_start
                temp_mesh.polygons[i].loop_total = poly.loop_total
            
            temp_mesh.update()
            
            for vg in source_obj.vertex_groups:
                new_vg = temp_obj.vertex_groups.new(name=vg.name)
                for i, vert in enumerate(source_mesh.vertices):
                    try:
                        weight = vg.weight(i)
                        new_vg.add([i], weight, 'REPLACE')
                    except RuntimeError:
                        pass
            
            temp_obj["vgtp_is_temp_merge"] = True
            temp_obj["vgtp_source_obj"] = source_obj.name
            temp_obj["vgtp_source_vg"] = source_vg.name
            temp_obj["vgtp_target_obj"] = target_obj.name
            temp_obj["vgtp_target_vg"] = target_vg.name
            
            bpy.ops.object.select_all(action='DESELECT')
            temp_obj.select_set(True)
            context.view_layer.objects.active = temp_obj
            
            bpy.ops.object.mode_set(mode='WEIGHT_PAINT')
            
            self.report({'INFO'}, f"已进入权重绘制模式，正在编辑: {source_vg_name}")
            return {'FINISHED'}
        
        self.report({'WARNING'}, "请选择一条Match_开头的连接线")
        return {'CANCELLED'}


def register_keymaps():
    """注册快捷键"""
    wm = bpy.context.window_manager
    if not wm.keyconfigs.addon:
        return
    
    kc = wm.keyconfigs.addon
    
    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
    
    kmi_sync = km.keymap_items.new(
        SSMT_OT_VertexGroupMatchSync.bl_idname, 
        'Z', 'PRESS', 
        ctrl=True, shift=True
    )
    _keymaps.append((km, kmi_sync))
    
    kmi_wp = km.keymap_items.new(
        SSMT_OT_VertexGroupMatchQuickWeight.bl_idname, 
        'W', 'PRESS', 
        alt=True
    )
    _keymaps.append((km, kmi_wp))
    
    print("[VertexGroupMatch] 已注册快捷键: Ctrl+Shift+Z (同步), Alt+W (快速权重)")


def unregister_keymaps():
    """注销快捷键"""
    for km, kmi in _keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass
    _keymaps.clear()
    
    print("[VertexGroupMatch] 已注销快捷键")


classes = (
    SSMTNode_VertexGroupMatch,
    SSMT_OT_VertexGroupMatchExecute,
    SSMT_OT_VertexGroupMatchClear,
    SSMT_OT_VertexGroupMatchSync,
    SSMT_OT_VertexGroupMatchDeleteConnection,
    SSMT_OT_VertexGroupMatchDetectMulti,
    SSMT_OT_VertexGroupMatchQuickWeight,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    register_keymaps()


def unregister():
    unregister_keymaps()
    
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
