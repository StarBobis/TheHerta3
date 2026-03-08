import bpy
import os
import shutil
from bpy.types import Node, PropertyGroup
from bpy.props import StringProperty, CollectionProperty, BoolProperty, EnumProperty

from .blueprint_node_base import SSMTNodeBase, SSMTSocketObject
from ..config.main_config import GlobalConfig


class CrossIBItem(PropertyGroup):
    source_ib: StringProperty(
        name="源IB",
        description="源IB前缀，例如: 9f387166 或 9f387166-2（表示第2个分块）",
        default=""
    )
    target_ib: StringProperty(
        name="目标IB",
        description="目标IB前缀，例如: a55afe59 或 a55afe59-2（表示第2个分块）",
        default=""
    )
    
    @classmethod
    def parse_ib_with_component(cls, ib_str):
        """
        解析 IB 字符串，返回 (ib_hash, component_index)
        例如:
        - "27966f80" -> ("27966f80", 1)
        - "27966f80-2" -> ("27966f80", 2)
        """
        if not ib_str:
            return "", 1
        
        parts = ib_str.split("-")
        ib_hash = parts[0]
        
        if len(parts) > 1 and parts[1].isdigit():
            component_index = int(parts[1])
        else:
            component_index = 1
        
        return ib_hash, component_index


class CrossIBMethodEnum:
    END_FIELD = 'END_FIELD'
    END_FIELD_LABEL = '终末地跨 IB'
    END_FIELD_LOGIC_NAME = 'EFMI'
    
    VB_COPY = 'VB_COPY'
    VB_COPY_LABEL = 'VB 复制'
    VB_COPY_LOGIC_NAME = 'ZZMI'
    
    @classmethod
    def get_items(cls):
        return [
            (cls.END_FIELD, cls.END_FIELD_LABEL, "终末地跨 IB 方式 (仅 EFMI)"),
            (cls.VB_COPY, cls.VB_COPY_LABEL, "VB 复制方式 (仅 ZZMI)"),
        ]
    
    @classmethod
    def get_items_for_logic_name(cls, logic_name):
        items = []
        for item in cls.get_items():
            method_id = item[0]
            method_logic_name = getattr(cls, f"{method_id}_LOGIC_NAME", None)
            if method_logic_name and method_logic_name == logic_name:
                items.append(item)
        return items
    
    @classmethod
    def get_available_methods(cls, logic_name):
        available_methods = []
        for item in cls.get_items():
            method_id = item[0]
            method_logic_name = getattr(cls, f"{method_id}_LOGIC_NAME", None)
            if method_logic_name and method_logic_name == logic_name:
                available_methods.append(method_id)
        return available_methods


class SSMT_OT_CrossIB_AddItem(bpy.types.Operator):
    bl_idname = "ssmt.cross_ib_add_item"
    bl_label = "添加跨IB映射"
    bl_description = "添加一个新的跨IB映射项"

    node_name: StringProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node:
            new_item = node.cross_ib_list.add()
            new_item.source_ib = ""
            new_item.target_ib = ""
        
        return {'FINISHED'}


class SSMT_OT_CrossIB_RemoveItem(bpy.types.Operator):
    bl_idname = "ssmt.cross_ib_remove_item"
    bl_label = "删除跨IB映射"
    bl_description = "删除选中的跨IB映射项"

    node_name: StringProperty()
    item_index: bpy.props.IntProperty()

    def execute(self, context):
        tree = getattr(context.space_data, "edit_tree", None) or getattr(context.space_data, "node_tree", None)
        if not tree:
            return {'CANCELLED'}
        
        node = tree.nodes.get(self.node_name)
        if node and self.item_index >= 0 and self.item_index < len(node.cross_ib_list):
            node.cross_ib_list.remove(self.item_index)
        
        return {'FINISHED'}


class SSMTNode_CrossIB(SSMTNodeBase):
    bl_idname = 'SSMTNode_CrossIB'
    bl_label = 'Cross IB'
    bl_icon = 'ARROW_LEFTRIGHT'
    bl_width_min = 350

    cross_ib_list: CollectionProperty(type=CrossIBItem)
    
    cross_ib_method: EnumProperty(
        name="跨 IB 方式",
        description="选择跨 IB 的实现方式",
        items=CrossIBMethodEnum.get_items(),
        default=CrossIBMethodEnum.END_FIELD,
        update=lambda self, context: self._update_cross_ib_method()
    )
    
    current_logic_name: StringProperty(
        name="当前运行模式",
        description="当前游戏的运行模式",
        default="",
        get=lambda self: self._get_current_logic_name()
    )

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input 1")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 350
        self.use_custom_color = True
        self.color = (0.6, 0.3, 0.6)
        
        self._update_cross_ib_method()

    def _get_current_logic_name(self):
        from ..config.main_config import GlobalConfig
        return GlobalConfig.logic_name or "未知"
    
    def _update_cross_ib_method(self):
        from ..config.main_config import GlobalConfig
        logic_name = GlobalConfig.logic_name
        
        available_methods = CrossIBMethodEnum.get_available_methods(logic_name)
        
        if available_methods:
            if self.cross_ib_method not in available_methods:
                self.cross_ib_method = available_methods[0]
        else:
            self.cross_ib_method = ''

    def draw_buttons(self, context, layout):
        logic_name = self._get_current_logic_name()
        
        row = layout.row()
        row.label(text=f"当前运行模式: {logic_name}", icon='INFO')
        
        available_methods = CrossIBMethodEnum.get_available_methods(logic_name)
        
        if available_methods:
            if len(available_methods) == 1:
                row = layout.row()
                row.label(text=f"跨 IB 方式: {CrossIBMethodEnum.__dict__[available_methods[0] + '_LABEL']}", icon='CHECKMARK')
            else:
                row = layout.row()
                row.prop(self, "cross_ib_method", expand=True)
        else:
            row = layout.row()
            row.label(text="当前运行模式不支持跨 IB", icon='ERROR')
        
        box = layout.box()
        box.label(text="跨IB映射列表 (源IB >> 目标IB)", icon='ARROW_LEFTRIGHT')
        
        for i, item in enumerate(self.cross_ib_list):
            row = box.row(align=True)
            row.prop(item, "source_ib", text="源")
            row.label(text=">>")
            row.prop(item, "target_ib", text="目标")
            op = row.operator("ssmt.cross_ib_remove_item", text="", icon='X')
            op.node_name = self.name
            op.item_index = i
        
        row = layout.row()
        op = row.operator("ssmt.cross_ib_add_item", text="添加映射", icon='ADD')
        op.node_name = self.name

    def update(self):
        if self.inputs and self.inputs[-1].is_linked:
            self.inputs.new('SSMTSocketObject', f"Input {len(self.inputs) + 1}")
        
        if len(self.inputs) > 1 and not self.inputs[-1].is_linked and not self.inputs[-2].is_linked:
            self.inputs.remove(self.inputs[-1])

    def get_cross_ib_mappings(self):
        mappings = []
        for item in self.cross_ib_list:
            if item.source_ib and item.target_ib:
                mappings.append({
                    'source_ib': item.source_ib,
                    'target_ib': item.target_ib
                })
        return mappings

    def get_source_ib_list(self):
        source_list = []
        for item in self.cross_ib_list:
            if item.source_ib:
                source_list.append(item.source_ib)
        return list(set(source_list))

    def get_target_ib_list(self):
        target_list = []
        for item in self.cross_ib_list:
            if item.target_ib:
                target_list.append(item.target_ib)
        return list(set(target_list))

    def get_ib_mapping_dict(self):
        ib_mapping = {}
        for item in self.cross_ib_list:
            if item.source_ib and item.target_ib:
                source_hash, source_component = CrossIBItem.parse_ib_with_component(item.source_ib)
                target_hash, target_component = CrossIBItem.parse_ib_with_component(item.target_ib)
                
                mapping_key = f"{source_hash}_{source_component}"
                if mapping_key not in ib_mapping:
                    ib_mapping[mapping_key] = []
                
                target_key = f"{target_hash}_{target_component}"
                if target_key not in ib_mapping[mapping_key]:
                    ib_mapping[mapping_key].append(target_key)
        return ib_mapping


class SSMTNode_PostProcess_CrossIB(SSMTNodeBase):
    bl_idname = 'SSMTNode_PostProcess_CrossIB'
    bl_label = 'Cross IB PostProcess'
    bl_icon = 'FILE_REFRESH'
    bl_width_min = 300

    def init(self, context):
        self.inputs.new('SSMTSocketPostProcess', "Input")
        self.outputs.new('SSMTSocketPostProcess', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        layout.label(text="跨IB后处理节点", icon='FILE_REFRESH')
        layout.label(text="自动复制HLSL文件到res目录")

    def execute_postprocess(self, mod_export_path):
        self._copy_hlsl_files(mod_export_path)

    def _copy_hlsl_files(self, mod_export_path):
        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        source_dir = os.path.join(addon_dir, "超级工具集")
        
        if not os.path.exists(source_dir):
            print(f"[CrossIB] 警告: 超级工具集目录不存在: {source_dir}")
            return
        
        hlsl_files = [
            'extract_cb1_ps.hlsl',
            'extract_cb1_vs.hlsl',
            'record_bones_cs.hlsl',
            'redirect_cb1_cs.hlsl'
        ]
        
        res_dir = os.path.join(mod_export_path, "res")
        os.makedirs(res_dir, exist_ok=True)
        
        copied_count = 0
        for hlsl_file in hlsl_files:
            source_file = os.path.join(source_dir, hlsl_file)
            target_file = os.path.join(res_dir, hlsl_file)
            
            if os.path.exists(source_file):
                if not os.path.exists(target_file):
                    shutil.copy2(source_file, target_file)
                    print(f"[CrossIB] 已复制: {hlsl_file}")
                    copied_count += 1
                else:
                    print(f"[CrossIB] 文件已存在，跳过: {hlsl_file}")
            else:
                print(f"[CrossIB] 警告: 源文件不存在: {source_file}")
        
        print(f"[CrossIB] 共复制 {copied_count} 个HLSL文件到 {res_dir}")


classes = (
    CrossIBItem,
    SSMT_OT_CrossIB_AddItem,
    SSMT_OT_CrossIB_RemoveItem,
    SSMTNode_CrossIB,
    SSMTNode_PostProcess_CrossIB,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
