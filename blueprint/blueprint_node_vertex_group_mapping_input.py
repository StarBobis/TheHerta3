# -*- coding: utf-8 -*-
import bpy
import re

from .blueprint_node_base import SSMTNodeBase


class SSMTNode_VertexGroupMappingInput(SSMTNodeBase):
    '''顶点组映射表输入节点：直接选择文本编辑器中的映射表作为输入'''
    bl_idname = 'SSMTNode_VertexGroupMappingInput'
    bl_label = '映射表输入'
    bl_description = '直接选择文本编辑器中的映射表作为顶点组处理节点的输入'
    bl_icon = 'TEXT'
    bl_width_min = 300

    mapping_text: bpy.props.StringProperty(
        name="映射表文本",
        description="选择文本编辑器中的映射表文本",
        default=""
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
        box.label(text="映射表输入", icon='TEXT')
        
        row = box.row()
        row.prop_search(self, "mapping_text", bpy.data, "texts", text="映射表")
        
        row = box.row()
        row.prop(self, "target_hash", text="目标哈希")
        
        if self.mapping_text:
            text = bpy.data.texts.get(self.mapping_text)
            if text:
                mapping_count = self._count_mapping_entries(text)
                box.label(text=f"映射条目数: {mapping_count}", icon='INFO')
            else:
                box.label(text="未找到映射表文本", icon='ERROR')

    def _count_mapping_entries(self, text):
        count = 0
        for line in text.lines:
            clean_line = re.sub(r'[#//].*', '', line.body).strip()
            if '=' in clean_line:
                parts = clean_line.split('=', 1)
                if len(parts) == 2 and parts[0].strip() and parts[1].strip():
                    count += 1
        return count

    def get_mapping_dict(self):
        if not self.mapping_text:
            return {}
        
        text = bpy.data.texts.get(self.mapping_text)
        if not text:
            return {}
        
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


classes = (
    SSMTNode_VertexGroupMappingInput,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
