import bpy
import os
import glob
import re

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_BufferCleanup(SSMTNode_PostProcess_Base):
    '''缓冲区清理后处理节点：扫描并删除未被任何INI文件引用的.buf文件'''
    bl_idname = 'SSMTNode_PostProcess_BufferCleanup'
    bl_label = '缓冲区清理'
    bl_description = '扫描并删除配置表路径下所有未被任何INI文件引用的.buf文件'

    def draw_buttons(self, context, layout):
        layout.label(text="此操作将永久删除未引用的.buf文件", icon='ERROR')
        layout.label(text="建议先备份文件夹", icon='INFO')

    def _find_unused_buffers(self, config_path):
        referenced_files = set()
        filename_pattern = re.compile(r'^\s*filename\s*=\s*(.+)', re.IGNORECASE)
        for ini_file in glob.glob(os.path.join(config_path, "*.ini")):
            try:
                with open(ini_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        match = filename_pattern.match(line)
                        if match:
                            referenced_files.add(os.path.normpath(os.path.join(config_path, match.group(1).strip().replace('/', os.sep))))
            except Exception as e:
                print(f"读取INI文件失败 {ini_file}: {e}")
        disk_buf_files = glob.glob(os.path.join(config_path, '**', '*.buf'), recursive=True)
        return [abs_path for buf_file in disk_buf_files if (abs_path := os.path.normpath(buf_file)) not in referenced_files]

    def execute_postprocess(self, mod_export_path):
        print(f"缓冲区清理后处理节点开始执行，Mod导出路径: {mod_export_path}")

        print("正在扫描未引用的.buf文件...")
        files_to_delete = self._find_unused_buffers(mod_export_path)

        if not files_to_delete:
            print("未找到任何未被引用的.buf文件。")
            return

        print(f"找到 {len(files_to_delete)} 个未引用的.buf文件，开始删除...")
        deleted_count = 0
        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                deleted_count += 1
                print(f"  已删除: {os.path.relpath(file_path, mod_export_path)}")
            except OSError as e:
                print(f"  删除文件失败 {file_path}: {e}")

        print(f"清理完成！成功删除了 {deleted_count} 个未引用的 .buf 文件。")


classes = (
    SSMTNode_PostProcess_BufferCleanup,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
