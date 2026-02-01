import bpy
import os
import glob
import re
import shutil
from collections import OrderedDict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_MultiFile(SSMTNode_PostProcess_Base):
    '''多文件配置后处理节点：为指定哈希值的物体生成多文件动画配置'''
    bl_idname = 'SSMTNode_PostProcess_MultiFile'
    bl_label = '多文件配置'
    bl_description = '为指定哈希值的物体生成多文件动画配置，支持紧凑缓冲区和顶点增量存储'

    hash_values: bpy.props.StringProperty(
        name="哈希值",
        description="需要处理的哈希值，多个用逗号分隔（如：4816de84,5c0240db）",
        default=""
    )
    animation_swapkey: bpy.props.StringProperty(
        name="循环参数名",
        description="用于动画帧切换的参数名称",
        default="$swapkey100"
    )
    active_swapkey: bpy.props.StringProperty(
        name="激活参数名",
        description="用于控制动画执行的参数名称",
        default="$active0"
    )
    active_value: bpy.props.IntProperty(
        name="激活参数值",
        description="激活参数的值",
        default=1,
        min=0,
        max=100
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "hash_values")
        layout.prop(self, "animation_swapkey")
        layout.prop(self, "active_swapkey")
        layout.prop(self, "active_value")

        if not NUMPY_AVAILABLE:
            layout.label(text="警告: 未安装numpy库，功能不可用", icon='ERROR')

    def _get_vertex_attrs_node(self):
        """查找前序的顶点属性定义节点"""
        if not self.inputs[0].is_linked:
            return None
        
        source_node = self.inputs[0].links[0].from_node
        if source_node.bl_idname == 'SSMTNode_PostProcess_VertexAttrs':
            return source_node
        
        if source_node.inputs[0].is_linked:
            prev_node = source_node.inputs[0].links[0].from_node
            if prev_node.bl_idname == 'SSMTNode_PostProcess_VertexAttrs':
                return prev_node
        
        return None

    def _get_shader_source_path(self):
        """获取着色器模板文件路径"""
        try:
            addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            asset_source_dir = os.path.join(addon_dir, "超级工具集")
            shader_source_path = os.path.join(asset_source_dir, "合并anim_packed_delta.hlsl")
            return shader_source_path
        except Exception as e:
            print(f"获取着色器模板路径时出错: {e}")
            return None

    def _get_vertex_struct_definition(self):
        """获取顶点属性结构体定义"""
        vertex_attrs_node = self._get_vertex_attrs_node()
        if vertex_attrs_node:
            return vertex_attrs_node.get_vertex_struct_definition()
        return None

    def _update_shader_file(self, shader_path):
        """更新着色器文件"""
        try:
            with open(shader_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            vertex_struct = self._get_vertex_struct_definition()
            if vertex_struct:
                content = re.sub(r"struct VertexAttributes\s*\{[^}]*\};", vertex_struct, content, flags=re.DOTALL)
            
            with open(shader_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return True
        except Exception as e:
            print(f"更新着色器文件失败: {e}")
            return False

    def _parse_hash_values(self, hash_str):
        return [h.strip() for h in hash_str.split(',') if h.strip()]

    def _read_buffer_file(self, buffer_path):
        try:
            with open(buffer_path, 'rb') as f:
                return np.fromfile(f, dtype=np.float32)
        except Exception as e:
            print(f"读取缓冲区文件失败: {buffer_path}. 原因: {e}")
            return None

    def _write_buffer_file(self, buffer_data, buffer_path):
        try:
            os.makedirs(os.path.dirname(buffer_path), exist_ok=True)
            buffer_data.tofile(buffer_path)
            return True
        except Exception as e:
            print(f"写入缓冲区文件失败: {buffer_path}. 原因: {e}")
            return False

    def _calculate_deltas(self, base_buffer, target_buffer):
        return target_buffer - base_buffer

    def _create_packed_buffers(self, base_buffer, target_buffer, use_delta=True):
        try:
            if use_delta:
                deltas = self._calculate_deltas(base_buffer, target_buffer)
            else:
                deltas = target_buffer.copy()

            vertex_size = 10
            changed_indices = []
            changed_values = []

            if len(deltas) % vertex_size != 0:
                print(f"缓冲区长度不是顶点大小的整数倍: {len(deltas)} % {vertex_size} != 0")
                adjusted_length = (len(deltas) // vertex_size) * vertex_size
                deltas = deltas[:adjusted_length]
                if use_delta:
                    target_buffer = target_buffer[:adjusted_length]

            for i in range(0, len(deltas), vertex_size):
                position_delta = deltas[i:i+3]
                if not np.allclose(position_delta, [0, 0, 0], atol=1e-6):
                    changed_indices.append(i // vertex_size)
                    if use_delta:
                        changed_values.extend(position_delta)
                    else:
                        changed_values.extend(target_buffer[i:i+3])

            map_array = np.full(len(deltas) // vertex_size, -1, dtype=np.int32)
            for idx, vert_idx in enumerate(changed_indices):
                map_array[vert_idx] = idx

            position_deltas_array = np.array(changed_values, dtype=np.float32)

            print(f"创建紧凑缓冲区: {len(changed_indices)}个顶点变化，原始顶点数: {len(deltas) // vertex_size}")

            return map_array, position_deltas_array
        except Exception as e:
            print(f"创建紧凑缓冲区失败: {str(e)}")
            return np.array([], dtype=np.int32), np.array([], dtype=np.float32)

    def _get_vertex_count(self, ini_sections, hash_value):
        for section_name, lines in ini_sections.items():
            if section_name.startswith(f'[TextureOverride_{hash_value}_') and '_VertexLimitRaise' in section_name:
                for line in lines:
                    if line.strip().startswith('override_vertex_count ='):
                        try:
                            return int(line.split('=', 1)[1].strip())
                        except ValueError:
                            continue
        return None

    def _read_ini_to_ordered_dict(self, ini_file_path):
        sections = OrderedDict()
        current_section = None
        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line.startswith('[') and stripped_line.endswith(']'):
                        current_section = stripped_line
                        sections[current_section] = []
                    elif current_section is not None:
                        sections[current_section].append(line.rstrip())
        except FileNotFoundError:
            return None
        return sections

    def _write_ordered_dict_to_ini(self, sections, ini_file_path):
        with open(ini_file_path, 'w', encoding='utf-8') as f:
            for section_name, lines in sections.items():
                f.write(f"{section_name}\n")
                for line in lines:
                    f.write(f"{line}\n")
                f.write("\n")

    def execute_postprocess(self, mod_export_path):
        print(f"多文件配置后处理节点开始执行，Mod导出路径: {mod_export_path}")

        if not NUMPY_AVAILABLE:
            print("需要安装numpy库以使用紧凑缓冲区和增量存储功能")
            return

        hash_values = self._parse_hash_values(self.hash_values)
        if not hash_values:
            print("请至少输入一个有效的哈希值")
            return

        try:
            original_cwd = os.getcwd()
            os.chdir(mod_export_path)

            ini_files = glob.glob("*.ini")
            if not ini_files:
                print("在路径中未找到任何.ini文件")
                os.chdir(original_cwd)
                return

            for ini_file in ini_files:
                ini_file_path = os.path.join(mod_export_path, ini_file)
                self._create_cumulative_backup(ini_file_path, mod_export_path)
                sections = self._read_ini_to_ordered_dict(ini_file)
                if not sections:
                    continue

                for hash_value in hash_values:
                    resource_section = f'[Resource{hash_value}Position]'
                    if resource_section in sections:
                        original_lines = sections[resource_section]
                        new_section_lines = [f'[Resource{hash_value}Position_1]'] + original_lines
                        sections[resource_section] = new_section_lines

                        base_buffer_path = None
                        for line in original_lines:
                            if line.strip().startswith('filename ='):
                                base_buffer_path = line.split('=', 1)[1].strip()
                                break

                        if base_buffer_path:
                            base_dir = os.path.dirname(base_buffer_path)
                            base_filename = os.path.basename(base_buffer_path)

                            buffer_folders = []
                            for i in range(2, 100):
                                buffer_folder = os.path.join(mod_export_path, f"Buffer{i:02d}")
                                if os.path.exists(buffer_folder):
                                    buffer_folders.append(f"Buffer{i:02d}")
                                else:
                                    break

                            if buffer_folders:
                                base_buffer_full_path = os.path.join(mod_export_path, base_buffer_path)
                                base_buffer = self._read_buffer_file(base_buffer_full_path)
                                if base_buffer is None:
                                    continue

                                for i, buffer_folder in enumerate(buffer_folders, 2):
                                    target_filename = os.path.join(buffer_folder, f"{hash_value}-Position.buf")
                                    target_buffer_full_path = os.path.join(mod_export_path, target_filename)

                                    if os.path.exists(target_buffer_full_path):
                                        target_buffer = self._read_buffer_file(target_buffer_full_path)
                                        if target_buffer is None:
                                            continue

                                        map_array, pos_deltas_array = self._create_packed_buffers(
                                            base_buffer, target_buffer, True
                                        )

                                        pos_output_path = os.path.join(mod_export_path, buffer_folder, f"{hash_value}-Position_pos.buf")

                                        self._write_buffer_file(pos_deltas_array, pos_output_path)

                                        map_output_path = os.path.join(mod_export_path, buffer_folder, f"{hash_value}-Position_map.buf")
                                        self._write_buffer_file(map_array, map_output_path)

                                        pos_resource_section = f'[Resource{hash_value}Position{i:02d}_pos]'
                                        stride = 12

                                        sections[pos_resource_section] = [
                                            'type = Buffer',
                                            f'stride = {stride}',
                                            f'filename = {buffer_folder}/{hash_value}-Position_pos.buf'
                                        ]

                                        map_resource_section = f'[Resource{hash_value}Position{i:02d}_Map]'
                                        sections[map_resource_section] = [
                                            'type = Buffer',
                                            'stride = 4',
                                            f'filename = {buffer_folder}/{hash_value}-Position_map.buf'
                                        ]

                                shader_section = f'[CustomShader_{hash_value}_1Anim]'
                                shader_lines = []

                                for i, buffer_folder in enumerate(buffer_folders, 2):
                                    state_index = i - 2
                                    shader_lines.append(f"if {self.animation_swapkey} == {state_index}")
                                    shader_lines.append(f"      cs-t51 = copy Resource{hash_value}Position{i:02d}_pos")
                                    shader_lines.append(f"endif")

                                shader_lines.append("")

                                for i, buffer_folder in enumerate(buffer_folders, 2):
                                    state_index = i - 2
                                    shader_lines.append(f"if {self.animation_swapkey} == {state_index}")
                                    shader_lines.append(f"      cs-t75 = copy Resource{hash_value}Position{i:02d}_Map")
                                    shader_lines.append(f"endif")

                                shader_lines.append("")
                                shader_lines.append("    cs = ./res/合并anim_packed_delta.hlsl")
                                shader_lines.append(f"    cs-u5 = copy Resource{hash_value}Position_1")
                                shader_lines.append(f"    Resource{hash_value}Position = ref cs-u5")

                                shader_source_path = self._get_shader_source_path()
                                if shader_source_path and os.path.exists(shader_source_path):
                                    dest_res_dir = os.path.join(mod_export_path, "res")
                                    os.makedirs(dest_res_dir, exist_ok=True)
                                    shader_dest_path = os.path.join(dest_res_dir, "合并anim_packed_delta.hlsl")
                                    shutil.copy2(shader_source_path, shader_dest_path)
                                    self._update_shader_file(shader_dest_path)
                                    print(f"已复制并更新着色器文件: 合并anim_packed_delta.hlsl")

                                vertex_count = self._get_vertex_count(sections, hash_value)
                                if vertex_count:
                                    shader_lines.append(f"    Dispatch = {vertex_count}, 1, 1")
                                else:
                                    shader_lines.append("    Dispatch = 10000, 1, 1")

                                shader_lines.append("    cs-u5 = null")
                                shader_lines.append("    cs-t51 = null")
                                shader_lines.append("    cs-t75 = null")

                                sections[shader_section] = shader_lines

                constants_section = '[Constants]'
                constants_lines = sections.get(constants_section, [])

                animation_swapkey_defined = False
                active_swapkey_defined = False

                for line in constants_lines:
                    if self.animation_swapkey in line:
                        animation_swapkey_defined = True
                    if self.active_swapkey in line:
                        active_swapkey_defined = True

                if not animation_swapkey_defined:
                    constants_lines.append(f"global persist {self.animation_swapkey} = 0")
                if not active_swapkey_defined:
                    constants_lines.append(f"global persist {self.active_swapkey} = 0")

                for hash_value in hash_values:
                    post_copy_line = f"post Resource{hash_value}Position = copy_desc Resource{hash_value}Position_1"
                    post_run_line = f"post run = CustomShader_{hash_value}_1Anim"

                    if post_copy_line not in constants_lines:
                        constants_lines.append(post_copy_line)
                    if post_run_line not in constants_lines:
                        constants_lines.append(post_run_line)

                sections[constants_section] = constants_lines

                present_section = '[Present]'
                present_lines = sections.get(present_section, [])

                active_block_start = -1
                active_block_end = -1

                for i, line in enumerate(present_lines):
                    if line.strip() == f"if {self.active_swapkey} == {self.active_value}":
                        active_block_start = i
                    elif active_block_start >= 0 and line.strip() == "endif":
                        active_block_end = i
                        break

                if active_block_start >= 0 and active_block_end >= 0:
                    for hash_value in hash_values:
                        run_line = f"    run = CustomShader_{hash_value}_1Anim"
                        if run_line not in present_lines[active_block_start:active_block_end]:
                            present_lines.insert(active_block_end, run_line)
                else:
                    present_lines.append("")
                    present_lines.append(f"if {self.active_swapkey} == {self.active_value}")
                    for hash_value in hash_values:
                        present_lines.append(f"    run = CustomShader_{hash_value}_1Anim")
                    present_lines.append("endif")

                sections[present_section] = present_lines

                self._write_ordered_dict_to_ini(sections, ini_file)

            os.chdir(original_cwd)
            print("多文件配置生成完成！")

        except Exception as e:
            if 'original_cwd' in locals() and os.path.exists(original_cwd):
                os.chdir(original_cwd)
            print(f"多文件配置生成过程中出错: {str(e)}")
            import traceback
            traceback.print_exc()


classes = (
    SSMTNode_PostProcess_MultiFile,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
