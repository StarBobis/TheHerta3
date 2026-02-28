# -*- coding: utf-8 -*-
import bpy
import re
from collections import defaultdict

from .blueprint_node_base import SSMTNodeBase


class SSMTNode_VertexGroupProcess(SSMTNodeBase):
    '''顶点组处理节点：在前处理流程中自动执行顶点组重命名、合并、清理、填充和排序'''
    bl_idname = 'SSMTNode_VertexGroupProcess'
    bl_label = '顶点组处理'
    bl_description = '在前处理流程中自动执行顶点组重命名、合并、清理、填充和排序'
    bl_icon = 'GROUP'
    bl_width_min = 300

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "物体")
        self.inputs.new('SSMTSocketObject', "映射表 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        box = layout.box()
        box.label(text="顶点组处理", icon='GROUP')
        
        connected_count = self._get_connected_mapping_count()
        box.label(text=f"已连接映射表: {connected_count}", icon='TEXT')
        
        box.separator()
        box.label(text="映射表配置:", icon='SETTINGS')
        
        for i, socket in enumerate(self.inputs):
            if i > 0:
                row = box.row(align=True)
                row.label(text=f"映射表 {i}:")
                
                if socket.is_linked:
                    for link in socket.links:
                        node_name = link.from_node.name if link.from_node else "未知"
                        target_hash = getattr(link.from_node, 'target_hash', '') if link.from_node else ''
                        
                        if target_hash:
                            row.label(text=f"→ {node_name[:15]} (哈希: {target_hash})", icon='LINKED')
                        else:
                            row.label(text=f"→ {node_name[:15]} (全局)", icon='LINKED')
                else:
                    row.label(text="(未连接)")

    def update(self):
        if self.inputs and len(self.inputs) >= 2:
            if self.inputs[-1].is_linked:
                self.inputs.new('SSMTSocketObject', f"映射表 {len(self.inputs)}")
            
            while len(self.inputs) > 2 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
                self.inputs.remove(self.inputs[-1])

    def _get_connected_mapping_count(self):
        count = 0
        for i, socket in enumerate(self.inputs):
            if i > 0 and socket.is_linked:
                count += 1
        return count

    def get_connected_mapping_nodes(self):
        mapping_nodes = []
        for i, socket in enumerate(self.inputs):
            if i > 0 and socket.is_linked:
                for link in socket.links:
                    from_node = link.from_node
                    target_hash = getattr(from_node, 'target_hash', '')
                    
                    if from_node.bl_idname == 'SSMTNode_VertexGroupMatch':
                        if hasattr(from_node, 'source_object') and hasattr(from_node, 'target_object'):
                            mapping_nodes.append({
                                'node': from_node,
                                'target_hash': target_hash,
                                'index': i,
                                'type': 'match'
                            })
                    elif from_node.bl_idname == 'SSMTNode_VertexGroupMappingInput':
                        mapping_nodes.append({
                            'node': from_node,
                            'target_hash': target_hash,
                            'index': i,
                            'type': 'input'
                        })
        return mapping_nodes

    def get_merged_mapping_for_object(self, obj_name, mapping_nodes):
        merged_mapping = {}
        
        sorted_nodes = sorted(mapping_nodes, key=lambda x: x['index'])
        
        for node_info in sorted_nodes:
            node = node_info['node']
            target_hash = node_info['target_hash']
            node_type = node_info.get('type', 'match')
            
            if target_hash and not obj_name.startswith(target_hash):
                continue
            
            if node_type == 'input':
                if hasattr(node, 'get_mapping_dict'):
                    mapping = node.get_mapping_dict()
                    merged_mapping.update(mapping)
            else:
                source_obj_name = getattr(node, 'source_object', '')
                target_obj_name = getattr(node, 'target_object', '')
                
                text_name = f"VG_Match_{source_obj_name}_to_{target_obj_name}"
                text = bpy.data.texts.get(text_name)
                
                if text:
                    mapping = self.parse_mapping_text(text)
                    merged_mapping.update(mapping)
        
        return merged_mapping

    def parse_mapping_text(self, text):
        mapping = {}
        for line in text.lines:
            clean_line = re.sub(r'[#//].*', '', line.body).strip()
            if '=' in clean_line:
                parts = clean_line.split('=', 1)
                if len(parts) == 2:
                    left = parts[0].strip()
                    right = parts[1].strip()
                    if left and right:
                        mapping[left] = right
        return mapping

    def generate_unique_name(self, base_name, collection):
        if base_name not in collection:
            return base_name
        suffix = 1
        while f"{base_name}.{suffix:03d}" in collection:
            suffix += 1
        return f"{base_name}.{suffix:03d}"

    def process_object(self, obj):
        if not obj or obj.type != 'MESH':
            return {"renamed": 0, "merged": 0, "cleaned": 0, "filled": 0}
        
        stats = {"renamed": 0, "merged": 0, "cleaned": 0, "filled": 0}
        
        try:
            print(f"[VGProcess] {self.name}: 开始获取映射表节点")
            mapping_nodes = self.get_connected_mapping_nodes()
            print(f"[VGProcess] {self.name}: 获取到 {len(mapping_nodes)} 个映射表节点")
            
            if mapping_nodes:
                print(f"[VGProcess] {self.name}: 开始合并映射表")
                merged_mapping = self.get_merged_mapping_for_object(obj.name, mapping_nodes)
                print(f"[VGProcess] {self.name}: 合并后映射表大小: {len(merged_mapping)}")
                if merged_mapping:
                    print(f"[VGProcess] {self.name}: 开始重命名顶点组")
                    stats["renamed"] = self._rename_vertex_groups(obj, merged_mapping)
                    print(f"[VGProcess] {self.name}: 重命名完成，数量: {stats['renamed']}")
            
            print(f"[VGProcess] {self.name}: 开始合并顶点组")
            stats["merged"] = self._merge_vertex_groups_by_prefix(obj)
            print(f"[VGProcess] {self.name}: 合并完成，数量: {stats['merged']}")
            
            print(f"[VGProcess] {self.name}: 开始清理非数字顶点组")
            stats["cleaned"] = self._remove_non_numeric_vertex_groups(obj)
            print(f"[VGProcess] {self.name}: 清理完成，数量: {stats['cleaned']}")
            
            print(f"[VGProcess] {self.name}: 开始填充顶点组空缺")
            stats["filled"] = self._fill_vertex_group_gaps(obj)
            print(f"[VGProcess] {self.name}: 填充完成，数量: {stats['filled']}")
            
            print(f"[VGProcess] {self.name}: 开始排序顶点组")
            self._sort_vertex_groups(obj)
            print(f"[VGProcess] {self.name}: 排序完成")
        except Exception as e:
            print(f"[VGProcess] 处理物体 {obj.name} 时发生错误: {e}")
            import traceback
            traceback.print_exc()
        
        return stats

    def _rename_vertex_groups(self, obj, mapping):
        renamed_count = 0
        for vg in obj.vertex_groups:
            if vg.name in mapping:
                new_name = mapping[vg.name]
                if vg.name != new_name:
                    try:
                        if new_name in obj.vertex_groups:
                            obj.vertex_groups[new_name].name = self.generate_unique_name(new_name, obj.vertex_groups)
                        vg.name = new_name
                        renamed_count += 1
                    except Exception as e:
                        print(f"[VGProcess] 重命名顶点组 {vg.name} -> {new_name} 失败: {e}")
        return renamed_count

    def _merge_vertex_groups_by_prefix(self, obj):
        prefix_map = defaultdict(list)
        for vg in obj.vertex_groups:
            match = re.match(r'^(\d+)', vg.name)
            if match:
                prefix_map[match.group(1)].append(vg)
        
        merged_count = 0
        groups_to_delete = []
        
        for prefix, source_groups in prefix_map.items():
            if len(source_groups) > 1 or (len(source_groups) == 1 and source_groups[0].name != prefix):
                try:
                    target_vg = obj.vertex_groups.get(prefix)
                    if not target_vg:
                        target_vg = obj.vertex_groups.new(name=prefix)
                    
                    for vert in obj.data.vertices:
                        total_weight = 0.0
                        for source_vg in source_groups:
                            try:
                                total_weight += source_vg.weight(vert.index)
                            except RuntimeError:
                                continue
                        
                        if total_weight > 0:
                            target_vg.add([vert.index], min(1.0, total_weight), 'REPLACE')
                    
                    groups_to_delete.extend(g for g in source_groups if not g.name.isdigit())
                    merged_count += 1
                except Exception as e:
                    print(f"[VGProcess] 合并顶点组前缀 {prefix} 失败: {e}")
        
        for vg in set(groups_to_delete):
            try:
                if vg.name in obj.vertex_groups:
                    obj.vertex_groups.remove(vg)
            except Exception as e:
                print(f"[VGProcess] 删除顶点组 {vg.name} 失败: {e}")
        
        return merged_count

    def _remove_non_numeric_vertex_groups(self, obj):
        groups_to_remove = [vg for vg in obj.vertex_groups if not vg.name.isdigit()]
        for vg in reversed(groups_to_remove):
            try:
                obj.vertex_groups.remove(vg)
            except Exception as e:
                print(f"[VGProcess] 删除顶点组 {vg.name} 失败: {e}")
        return len(groups_to_remove)

    def _fill_vertex_group_gaps(self, obj):
        numeric_names = {vg.name for vg in obj.vertex_groups if vg.name.isdigit()}
        if not numeric_names:
            return 0
        
        try:
            max_num = max(int(name) for name in numeric_names)
            print(f"[VGProcess] {self.name}: 填充空缺 - 数字顶点组数量: {len(numeric_names)}, 最大数字: {max_num}")
        except (ValueError, TypeError) as e:
            print(f"[VGProcess] {self.name}: 计算最大数字失败: {e}")
            return 0
        
        if max_num > 1000:
            print(f"[VGProcess] {self.name}: 警告 - 最大数字 {max_num} 过大，跳过填充")
            return 0
        
        filled_count = 0
        
        for num in range(max_num + 1):
            name = str(num)
            if name not in numeric_names:
                try:
                    obj.vertex_groups.new(name=name)
                    filled_count += 1
                except Exception as e:
                    print(f"[VGProcess] 创建顶点组 {name} 失败: {e}")
        
        return filled_count

    def _sort_vertex_groups(self, obj):
        try:
            bpy.context.view_layer.objects.active = obj
            obj.select_set(True)
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.vertex_group_sort(sort_type='NAME')
        except Exception as e:
            print(f"[VGProcess] 排序顶点组失败: {e}")
            pass


classes = (
    SSMTNode_VertexGroupProcess,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
