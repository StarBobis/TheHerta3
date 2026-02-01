import bpy
import os
import glob
import re
from collections import OrderedDict

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_ResourceMerge(SSMTNode_PostProcess_Base):
    '''资源合并后处理节点：合并相同哈希值的资源引用并删除重复文件'''
    bl_idname = 'SSMTNode_PostProcess_ResourceMerge'
    bl_label = '资源合并'
    bl_description = '合并相同哈希值的资源引用并删除重复文件'

    resource_key_logic: bpy.props.EnumProperty(
        name="哈希匹配逻辑",
        items=[
            ('FIRST_AND_LAST', "前后哈希", ""),
            ('FIRST_ONLY', "仅前哈希", ""),
            ('LAST_ONLY', "仅后哈希", "")
        ],
        default='FIRST_AND_LAST'
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "resource_key_logic")

    def extract_resource_key(self, resource_name):
        hash_parts = re.findall(r'[a-f0-9]{8,}', resource_name, re.IGNORECASE)
        if not hash_parts:
            return resource_name

        logic = self.resource_key_logic
        if logic == 'FIRST_ONLY':
            return hash_parts[0]
        elif logic == 'LAST_ONLY':
            return hash_parts[-1]
        elif logic == 'FIRST_AND_LAST':
            if len(hash_parts) >= 2:
                return f"{hash_parts[0]}_{hash_parts[-1]}"
            else:
                return resource_name
        return resource_name

    def execute_postprocess(self, mod_export_path):
        print(f"资源合并后处理节点开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("在路径中未找到任何.ini文件")
            return

        for ini_file in ini_files:
            self.process_ini_file(ini_file, mod_export_path)

        print("资源引用合并完成！")

    def process_ini_file(self, ini_file, mod_export_path):
        self._create_cumulative_backup(ini_file, mod_export_path)

        with open(ini_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        sections = OrderedDict()
        current_section = None

        for line in lines:
            stripped = line.strip()
            if stripped.startswith('[') and stripped.endswith(']'):
                current_section = stripped
                sections[current_section] = []
            elif current_section:
                sections[current_section].append(line.rstrip())

        key_to_first_ref = {}
        files_to_delete = set()

        for section_name, section_lines in sections.items():
            if not section_name.startswith('[Resource_'):
                continue

            filename = next(
                (l.split('=', 1)[1].strip() for l in section_lines if l.strip().startswith('filename =')),
                None
            )
            if not filename:
                continue

            resource_key = self.extract_resource_key(filename)
            if not resource_key:
                continue

            if resource_key in key_to_first_ref:
                file_path = os.path.join(mod_export_path, filename)
                if os.path.exists(file_path):
                    files_to_delete.add(file_path)
            else:
                key_to_first_ref[resource_key] = {
                    'section': section_name,
                    'filename': filename
                }

        modified = False
        for section_name, section_lines in sections.items():
            if section_name.startswith('[Resource_'):
                for i, line in enumerate(section_lines):
                    if line.strip().startswith('filename ='):
                        original_filename = line.split('=', 1)[1].strip()
                        resource_key = self.extract_resource_key(original_filename)

                        if resource_key and resource_key in key_to_first_ref:
                            primary_filename = key_to_first_ref[resource_key]['filename']
                            if original_filename != primary_filename:
                                section_lines[i] = f"filename = {primary_filename}"
                                modified = True
                        break

        if modified:
            new_content = []
            for section_name, lines in sections.items():
                new_content.append(section_name)
                new_content.extend(lines)
                new_content.append('')

            with open(ini_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(new_content))

        for file_path in files_to_delete:
            try:
                os.remove(file_path)
                print(f"  已删除重复文件: {os.path.relpath(file_path, mod_export_path)}")
            except OSError as e:
                print(f"删除文件失败 {file_path}: {e}")


classes = (
    SSMTNode_PostProcess_ResourceMerge,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
