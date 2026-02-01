import bpy
import os
import shutil
import datetime
from bpy.types import Node, NodeSocket

from ..blueprint.blueprint_node_base import SSMTNodeBase, SSMTSocketPostProcess


class SSMTNode_PostProcess_Base(SSMTNodeBase):
    '''后处理节点基类，所有后处理节点都应继承此类'''
    bl_icon = 'FILE_REFRESH'
    bl_width_min = 300

    def init(self, context):
        self.inputs.new('SSMTSocketPostProcess', "Input")
        self.outputs.new('SSMTSocketPostProcess', "Output")
        self.width = 300

    def execute_postprocess(self, mod_export_path):
        '''
        执行后处理逻辑的抽象方法，子类必须实现此方法
        
        Args:
            mod_export_path: Mod导出的完整路径
        '''
        raise NotImplementedError("子类必须实现 execute_postprocess 方法")

    def _create_cumulative_backup(self, ini_file_path, mod_export_path):
        '''
        创建累积备份（统一的备份逻辑）
        
        Args:
            ini_file_path: 要备份的INI文件完整路径
            mod_export_path: Mod导出的完整路径（用于确定备份目录位置）
        '''
        try:
            if not os.path.exists(ini_file_path):
                print(f"文件不存在，跳过备份: {ini_file_path}")
                return
            
            backup_dir = os.path.join(mod_export_path, "Backups")
            os.makedirs(backup_dir, exist_ok=True)
            
            base_filename = os.path.basename(ini_file_path)
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_filename = f"{base_filename}.{timestamp}.bak"
            backup_path = os.path.join(backup_dir, backup_filename)
            
            shutil.copy2(ini_file_path, backup_path)
            print(f"已创建备份: {backup_path}")
        except Exception as e:
            print(f"创建备份失败: {e}")
