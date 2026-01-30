import bpy
import os
import json
from bpy.types import Node, NodeSocket
from bpy.props import StringProperty

from ..utils.json_utils import JsonUtils
from ..config.main_config import GlobalConfig

from .blueprint_node_base import SSMTNodeBase


class SSMTNode_DataType(SSMTNodeBase):
    '''数据类型节点：用于覆盖指定DrawIB的数据类型'''
    bl_idname = 'SSMTNode_DataType'
    bl_label = '数据类型'
    bl_icon = 'FILE_TEXT'
    bl_width_min = 300

    # DrawIB 匹配（支持多个DrawIB，用逗号分隔）
    draw_ib_match: bpy.props.StringProperty(
        name="匹配 DrawIB",
        description="输入要匹配的DrawIB（支持多个，用逗号分隔）",
        default=""
    )

    # tmp.json 文件路径
    tmp_json_path: bpy.props.StringProperty(
        name="tmp.json 文件",
        description="选择 tmp.json 文件路径",
        default=""
    )

    # 加载的数据
    loaded_data: bpy.props.StringProperty(
        name="已加载数据",
        description="显示已加载的 tmp.json 数据摘要",
        default="未加载"
    )

    def init(self, context):
        self.inputs.new('SSMTSocketObject', "Input")
        self.outputs.new('SSMTSocketObject', "Output")
        self.width = 300

    def draw_buttons(self, context, layout):
        # DrawIB 匹配输入框
        box = layout.box()
        box.label(text="DrawIB 匹配", icon='GROUP_VCOL')
        box.prop(self, "draw_ib_match", text="")
        box.label(text="支持多个DrawIB，用逗号分隔", icon='INFO')
        
        # 数据类型配置
        box = layout.box()
        box.label(text="数据类型配置", icon='FILE_FOLDER')
        
        # 文件选择按钮
        row = box.row(align=True)
        row.prop(self, "tmp_json_path", text="")
        row.operator("ssmt.datatype_browse_tmp_json", text="", icon='FILEBROWSER').node_name = self.name
        
        # 显示加载状态
        if self.loaded_data != "未加载":
            box.separator()
            box.label(text="已加载数据:", icon='INFO')
            box.label(text=self.loaded_data, icon='CHECKMARK')
        else:
            box.separator()
            box.label(text="请选择 tmp.json 文件", icon='ERROR')

    def load_tmp_json(self):
        """加载 tmp.json 文件"""
        if not self.tmp_json_path:
            return False
        
        if not os.path.exists(self.tmp_json_path):
            return False
        
        try:
            with open(self.tmp_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 更新加载状态
            work_game_type = data.get("WorkGameType", "未知")
            element_count = len(data.get("D3D11ElementList", []))
            
            self.loaded_data = f"{work_game_type} ({element_count} 个元素)"
            return True
        except Exception as e:
            print(f"加载 tmp.json 失败: {e}")
            return False

    def is_draw_ib_matched(self, draw_ib: str) -> bool:
        """检查给定的 DrawIB 是否匹配"""
        if not self.draw_ib_match:
            return False
        
        # 支持多个 DrawIB，用逗号分隔
        matched_draw_ib_list = [ib.strip() for ib in self.draw_ib_match.split(',')]
        return draw_ib in matched_draw_ib_list

    def get_d3d11_element_list(self):
        """获取 D3D11ElementList"""
        if not self.tmp_json_path:
            return None
        
        if not os.path.exists(self.tmp_json_path):
            return None
        
        try:
            with open(self.tmp_json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            return data.get("D3D11ElementList", None)
        except Exception as e:
            print(f"读取 D3D11ElementList 失败: {e}")
            return None


class SSMT_OT_DataType_BrowseTmpJson(bpy.types.Operator):
    '''浏览并选择 tmp.json 文件'''
    bl_idname = "ssmt.datatype_browse_tmp_json"
    bl_label = "选择 tmp.json"
    
    filepath: bpy.props.StringProperty(subtype='FILE_PATH')
    node_name: bpy.props.StringProperty()
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def execute(self, context):
        # 获取节点树
        space_data = getattr(context, "space_data", None)
        if not space_data or space_data.type != 'NODE_EDITOR':
            self.report({'ERROR'}, "请在节点编辑器中使用此功能")
            return {'CANCELLED'}
        
        node_tree = getattr(space_data, "edit_tree", None) or getattr(space_data, "node_tree", None)
        if not node_tree:
            self.report({'ERROR'}, "未找到节点树")
            return {'CANCELLED'}
        
        # 获取节点
        node = node_tree.nodes.get(self.node_name)
        if not node:
            self.report({'ERROR'}, "未找到节点")
            return {'CANCELLED'}
        
        # 设置文件路径
        node.tmp_json_path = self.filepath
        
        # 加载文件
        if node.load_tmp_json():
            self.report({'INFO'}, f"已加载: {self.filepath}")
        else:
            self.report({'ERROR'}, "加载文件失败")
        
        return {'FINISHED'}


classes = (
    SSMTNode_DataType,
    SSMT_OT_DataType_BrowseTmpJson,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
