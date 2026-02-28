import bpy
import traceback
from bpy.types import Node, NodeSocket
from bpy.props import StringProperty, CollectionProperty, BoolProperty, IntProperty

from ..config.main_config import GlobalConfig
from .blueprint_node_base import SSMTNodeBase
from ..utils.obj_utils import mesh_triangulate_beauty


class SSMT_OT_MultiFileExport_SplitAnimation(bpy.types.Operator):
    '''Split animation for single object in multi-file export'''
    bl_idname = "ssmt.multifile_export_split_animation"
    bl_label = "拆分动画"
    bl_description = "对选中物体进行动画拆分，拆分后的物体将自动添加到列表"
    bl_options = {'REGISTER', 'UNDO'}
    
    node_name: bpy.props.StringProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if not node:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
            return {'CANCELLED'}
        
        # 获取当前选中的物体
        if not context.selected_objects:
            self.report({'WARNING'}, "请先选择要拆分的物体")
            return {'CANCELLED'}
        
        if len(context.selected_objects) != 1:
            self.report({'WARNING'}, "请只选择一个物体进行拆分")
            return {'CANCELLED'}
        
        obj = context.selected_objects[0]
        
        # 检查是否有动画
        if not obj.animation_data or not obj.animation_data.action:
            self.report({'WARNING'}, "选中物体没有动画数据")
            return {'CANCELLED'}
        
        # 获取节点设置的帧范围
        start_frame = node.split_start_frame
        end_frame = node.split_end_frame
        
        # 验证帧范围
        if start_frame >= end_frame:
            self.report({'WARNING'}, "起始帧不能大于结束帧")
            return {'CANCELLED'}
        
        scene = context.scene
        
        # 保存原始状态
        original_frame = scene.frame_current
        original_selection = context.selected_objects[:]
        original_active = context.active_object
        
        # 创建或清空目标集合
        target_collection_name = f"{obj.name}_Split"
        target_collection = bpy.data.collections.get(target_collection_name)
        
        if not target_collection:
            # 创建新集合
            target_collection = bpy.data.collections.new(target_collection_name)
            scene.collection.children.link(target_collection)
        else:
            # 清空现有集合
            for obj_to_remove in list(target_collection.objects):
                bpy.data.objects.remove(obj_to_remove, do_unlink=True)
        
        # 保存原始插值类型并设置线性插值
        original_interpolations = {}
        if node.split_set_linear and obj.animation_data and obj.animation_data.action:
            for fcurve in obj.animation_data.action.fcurves:
                if fcurve.keyframe_points:
                    # 保存原始插值类型
                    original_interpolations[fcurve] = [kf.interpolation for kf in fcurve.keyframe_points]
                    # 设置为线性插值
                    for keyframe in fcurve.keyframe_points:
                        keyframe.interpolation = 'LINEAR'
        
        # 拆分动画
        split_objects = []
        try:
            for frame in range(start_frame, end_frame + 1):
                # 根据选项选择跳转模式
                if node.split_use_precise_mode:
                    # 高精度模式：从第0帧开始播放到目标帧
                    for f in range(0, frame + 1):
                        scene.frame_set(f)
                else:
                    # 普通模式：直接跳转到目标帧
                    scene.frame_set(frame)
                
                # 使用依赖图创建网格数据（支持曲线、曲面等各种类型）
                depsgraph = context.evaluated_depsgraph_get()
                eval_obj = obj.evaluated_get(depsgraph)
                mesh_data = bpy.data.meshes.new_from_object(eval_obj)
                matrix = eval_obj.matrix_world.copy()
                mesh_data.transform(matrix)
                
                # 创建新物体
                obj_name = f"{obj.name}_{frame:03d}"
                new_obj = bpy.data.objects.new(obj_name, mesh_data)
                
                # 复制材质
                for slot in obj.material_slots:
                    if slot.material:
                        new_obj.data.materials.append(slot.material)
                
                # 移动到目标集合
                target_collection.objects.link(new_obj)
                
                split_objects.append(new_obj.name)
                
                self.report({'INFO'}, f"已创建帧 {frame}: {new_obj.name}")
                
                # 清理
                eval_obj.to_mesh_clear()
        
        except Exception as e:
            self.report({'ERROR'}, f"动画拆分失败: {e}")
            import traceback
            traceback.print_exc()
            return {'CANCELLED'}
        
        finally:
            # 恢复原始插值类型
            if node.split_set_linear and original_interpolations:
                for fcurve, original_interp_list in original_interpolations.items():
                    if fcurve.keyframe_points and len(original_interp_list) == len(fcurve.keyframe_points):
                        for i, keyframe in enumerate(fcurve.keyframe_points):
                            keyframe.interpolation = original_interp_list[i]
            
            # 恢复原始状态
            scene.frame_set(original_frame)
            bpy.ops.object.select_all(action='DESELECT')
            for o in original_selection:
                if o.name in bpy.data.objects:
                    o.select_set(True)
            if original_active and original_active.name in bpy.data.objects:
                context.view_layer.objects.active = original_active
        
        # 隐藏拆分集合
        if target_collection:
            # 隐藏集合中的所有物体
            for split_obj in target_collection.objects:
                split_obj.hide_set(True)
                # 确保物体不在视图中显示
                if split_obj.name in context.view_layer.objects:
                    context.view_layer.objects[split_obj.name].hide_viewport = True
        
        # 将拆分出来的物体添加到多文件导出列表
        for obj_name in split_objects:
            node.add_object_to_list(obj_name)
        
        self.report({'INFO'}, f"动画拆分完成！共拆分出 {len(split_objects)} 个物体，已添加到列表")
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_RemoveObject(bpy.types.Operator):
    '''Remove object from multi-file export list'''
    bl_idname = "ssmt.multifile_export_remove_object"
    bl_label = "移除物体"
    bl_description = "从列表中移除物体"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            node.remove_object_from_list(self.index)
            self.report({'INFO'}, f"已移除物体索引: {self.index}")
        else:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_ParseCollection(bpy.types.Operator):
    '''Parse collection and add all objects'''
    bl_idname = "ssmt.multifile_export_parse_collection"
    bl_label = "解析合集"
    bl_description = "解析合集中的所有物体（识别_001、_002等序列）"
    
    node_name: bpy.props.StringProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            count = node.parse_collection(node.temp_collection_name)
            self.report({'INFO'}, f"已解析合集: {node.temp_collection_name}，找到 {count} 个物体")
        else:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_CheckVertexCount(bpy.types.Operator):
    '''Check vertex count for all objects in list'''
    bl_idname = "ssmt.multifile_export_check_vertex_count"
    bl_label = "检查顶点数"
    bl_description = "统计列表中每个物体的顶点数，确保所有物体顶点数相同"
    
    node_name: bpy.props.StringProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            self.report({'WARNING'}, "无法获取节点树上下文")
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if not node:
            self.report({'WARNING'}, f"无法找到节点: {self.node_name}")
            return {'CANCELLED'}
        
        if len(node.object_list) == 0:
            self.report({'WARNING'}, "列表为空，没有物体可检查")
            return {'CANCELLED'}
        
        vertex_counts = []
        object_info = []
        missing_objects = []
        
        for i, item in enumerate(node.object_list):
            obj_name = item.object_name
            obj = bpy.data.objects.get(obj_name)
            
            if not obj:
                missing_objects.append(obj_name)
                continue
            
            if obj.type != 'MESH':
                self.report({'WARNING'}, f"物体 '{obj_name}' 不是网格类型")
                return {'CANCELLED'}
            
            vertex_count = len(obj.data.vertices)
            vertex_counts.append(vertex_count)
            object_info.append((i + 1, obj_name, vertex_count))
        
        if missing_objects:
            self.report({'WARNING'}, f"以下物体不存在: {', '.join(missing_objects)}")
            return {'CANCELLED'}
        
        print("\n" + "=" * 60)
        print("多文件导出节点 - 顶点数统计")
        print("=" * 60)
        
        for idx, name, count in object_info:
            print(f"  {idx}. {name}: {count} 顶点")
        
        print("=" * 60)
        
        unique_counts = set(vertex_counts)
        
        if len(unique_counts) == 1:
            vertex_count = vertex_counts[0]
            print(f"✓ 所有物体顶点数一致: {vertex_count} 顶点")
            self.report({'INFO'}, f"✓ 所有物体顶点数一致: {vertex_count} 顶点")
        else:
            print(f"✗ 顶点数不一致！发现 {len(unique_counts)} 种不同的顶点数:")
            for count in sorted(unique_counts):
                objects_with_count = [name for idx, name, c in object_info if c == count]
                print(f"  - {count} 顶点: {len(objects_with_count)} 个物体")
            
            min_count = min(vertex_counts)
            max_count = max(vertex_counts)
            self.report({'ERROR'}, f"✗ 顶点数不一致！范围: {min_count} - {max_count}")
        
        print("=" * 60 + "\n")
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_MoveUp(bpy.types.Operator):
    '''Move object up in list'''
    bl_idname = "ssmt.multifile_export_move_up"
    bl_label = "上移"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.index > 0:
            node.move_object_in_list(self.index, self.index - 1)
        
        return {'FINISHED'}


class SSMT_OT_MultiFileExport_MoveDown(bpy.types.Operator):
    '''Move object down in list'''
    bl_idname = "ssmt.multifile_export_move_down"
    bl_label = "下移"
    
    node_name: bpy.props.StringProperty() # type: ignore
    index: bpy.props.IntProperty() # type: ignore
    
    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.index < len(node.object_list) - 1:
            node.move_object_in_list(self.index, self.index + 1)
        
        return {'FINISHED'}


class MultiFileExportObjectItem(bpy.types.PropertyGroup):
    object_name: bpy.props.StringProperty(name="物体名称", default="") # type: ignore
    original_object_name: bpy.props.StringProperty(name="原始物体名称", default="") # type: ignore
    draw_ib: bpy.props.StringProperty(name="DrawIB", default="") # type: ignore
    component: bpy.props.StringProperty(name="Component", default="") # type: ignore
    alias_name: bpy.props.StringProperty(name="别名", default="") # type: ignore


class SSMTNode_MultiFile_Export(SSMTNodeBase):
    '''多文件导出节点：支持自动切换多个物体进行多次导出'''
    bl_idname = 'SSMTNode_MultiFile_Export'
    bl_label = '多文件导出'
    bl_icon = 'FILE_FOLDER'
    bl_width_min = 350
    
    object_list: bpy.props.CollectionProperty(type=MultiFileExportObjectItem) # type: ignore
    current_export_index: bpy.props.IntProperty(name="当前导出次数", default=1) # type: ignore
    split_start_frame: bpy.props.IntProperty(
        name="起始帧",
        description="动画拆分的起始帧",
        default=1,
        min=1
    ) # type: ignore
    split_end_frame: bpy.props.IntProperty(
        name="结束帧",
        description="动画拆分的结束帧",
        default=250,
        min=1
    ) # type: ignore
    split_use_precise_mode: bpy.props.BoolProperty(
        name="高精度模式",
        description="使用高精度模式逐帧跳转，确保动画准确性",
        default=True
    ) # type: ignore
    split_set_linear: bpy.props.BoolProperty(
        name="线性插值",
        description="将关键帧插值设为线性，防止拆分时出现过冲",
        default=True
    ) # type: ignore
    
    def init(self, context):
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 350
    
    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="物体列表", icon='GROUP_VCOL')
        
        if len(self.object_list) == 0:
            box.label(text="列表为空，请添加物体", icon='ERROR')
        else:
            box.label(text=f"共 {len(self.object_list)} 个物体", icon='INFO')
        
        box.separator()
        
        for i, item in enumerate(self.object_list):
            row = box.row(align=True)
            
            object_label = item.object_name
            if item.object_name:
                if "-" in item.object_name:
                    parts = item.object_name.split("-")
                    if len(parts) >= 3:
                        object_label = f"{parts[0]}-{parts[1]} ({parts[2]})"
            
            row.label(text=f"{i + 1}. {object_label}", icon='OBJECT_DATA')
            
            op_up = row.operator("ssmt.multifile_export_move_up", text="", icon='TRIA_UP')
            op_up.node_name = self.name
            op_up.index = i
            
            op_down = row.operator("ssmt.multifile_export_move_down", text="", icon='TRIA_DOWN')
            op_down.node_name = self.name
            op_down.index = i
            
            op_remove = row.operator("ssmt.multifile_export_remove_object", text="", icon='X')
            op_remove.node_name = self.name
            op_remove.index = i
            
            box.separator()
        
        box.separator()
        
        row = box.row(align=True)
        row.prop_search(self, "temp_collection_name", bpy.data, "collections", text="", icon='GROUP')
        row.operator("ssmt.multifile_export_parse_collection", text="解析合集", icon='FILE_REFRESH').node_name = self.name
        
        box.separator()
        
        row = box.row(align=True)
        row.operator("ssmt.multifile_export_check_vertex_count", text="检查顶点数", icon='CHECKMARK').node_name = self.name
        
        box.separator()
        box.label(text="动画拆分", icon='ANIM')
        
        row = box.row(align=True)
        row.prop(self, "split_start_frame", text="起始")
        row.prop(self, "split_end_frame", text="结束")
        
        row = box.row(align=True)
        row.prop(self, "split_use_precise_mode", text="高精度模式")
        row.prop(self, "split_set_linear", text="线性插值")
        
        row = box.row(align=True)
        row.operator("ssmt.multifile_export_split_animation", text="拆分选中物体动画", icon='ANIM').node_name = self.name
        row.label(text="选择一个物体后点击", icon='INFO')
    
    def get_current_object_info(self, export_index):
        """获取当前导出次数对应的物体信息"""
        if export_index < 0 or export_index >= len(self.object_list):
            return None
        
        item = self.object_list[export_index]
        return {
            "object_name": item.object_name,
            "original_object_name": getattr(item, 'original_object_name', item.object_name),
            "draw_ib": item.draw_ib,
            "component": item.component,
            "alias_name": item.alias_name
        }
    
    def add_object_to_list(self, object_name):
        """添加物体到列表"""
        if not object_name:
            return
        
        obj = bpy.data.objects.get(object_name)
        if not obj:
            return
        
        item = self.object_list.add()
        item.object_name = object_name
        
        if "-" in object_name:
            parts = object_name.split("-")
            if len(parts) >= 2:
                item.draw_ib = parts[0]
                item.component = parts[1]
                if len(parts) >= 3:
                    item.alias_name = "-".join(parts[2:])
        
        self.update_node_width([item.object_name for item in self.object_list])
    
    def remove_object_from_list(self, index):
        """从列表中移除物体"""
        if index >= 0 and index < len(self.object_list):
            self.object_list.remove(index)
            self.update_node_width([item.object_name for item in self.object_list])
    
    def move_object_in_list(self, from_index, to_index):
        """移动物体在列表中的位置"""
        if (from_index < 0 or from_index >= len(self.object_list) or
            to_index < 0 or to_index >= len(self.object_list)):
            return
        
        item = self.object_list[from_index]
        self.object_list.remove(from_index)
        self.object_list.move(len(self.object_list), to_index)
    
    def parse_collection(self, collection_name):
        """解析合集中的所有物体，识别序列号并按顺序添加"""
        if not collection_name:
            return 0
        
        collection = bpy.data.collections.get(collection_name)
        if not collection:
            return 0
        
        import re
        
        objects_dict = {}
        
        for obj in collection.objects:
            if not obj.name:
                continue
            
            object_name = obj.name
            
            pattern = r'_(\d+)$'
            match = re.search(pattern, object_name)
            
            if match:
                sequence_num = int(match.group(1))
                base_name = object_name[:match.start()]
                
                if base_name not in objects_dict:
                    objects_dict[base_name] = []
                
                objects_dict[base_name].append((sequence_num, object_name))
        
        count = 0
        for base_name in sorted(objects_dict.keys()):
            objects_dict[base_name].sort(key=lambda x: x[0])
            
            for seq_num, obj_name in objects_dict[base_name]:
                self.add_object_to_list(obj_name)
                count += 1
        
        return count
    
    def update_temp_collection_name(self, context):
        self.update_node_width([self.temp_collection_name])
    
    temp_collection_name: bpy.props.StringProperty(name="临时合集名称", default="", update=update_temp_collection_name) # type: ignore


classes = (
    MultiFileExportObjectItem,
    SSMTNode_MultiFile_Export,
    SSMT_OT_MultiFileExport_RemoveObject,
    SSMT_OT_MultiFileExport_ParseCollection,
    SSMT_OT_MultiFileExport_MoveUp,
    SSMT_OT_MultiFileExport_MoveDown,
    SSMT_OT_MultiFileExport_CheckVertexCount,
    SSMT_OT_MultiFileExport_SplitAnimation,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
