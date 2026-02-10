import bpy
import os
import glob
import re
import shutil
import struct
import datetime
from collections import OrderedDict

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_ShapeKey(SSMTNode_PostProcess_Base):
    '''形态键配置后处理节点：生成支持多形态叠加混合的INI配置'''
    bl_idname = 'SSMTNode_PostProcess_ShapeKey'
    bl_label = '形态键配置'
    bl_description = '读取分类文本，生成支持多形态叠加混合的INI配置'

    INTENSITY_START_INDEX = 100
    VERTEX_RANGE_START_INDEX = 200

    use_packed_buffers: bpy.props.BoolProperty(
        name="使用紧凑缓冲区",
        description="仅存储变化的顶点数据，大幅减小体积。需要 'numpy' 库。",
        default=True
    )
    store_deltas: bpy.props.BoolProperty(
        name="存储顶点增量",
        description="不存储完整的顶点坐标，而是存储与基础模型的差值，进一步减小体积。需要 'numpy' 库。",
        default=True
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "use_packed_buffers")
        layout.prop(self, "store_deltas")

        if not NUMPY_AVAILABLE:
            layout.label(text="警告: 未安装numpy库，优化功能不可用", icon='ERROR')

    def _create_safe_var_name(self, text, prefix="", existing_names=None):
        if not text:
            text = "unnamed"

        safe_text = re.sub(r'\s+', '_', text)
        safe_text = re.sub(r'[^a-zA-Z0-9_]', '', safe_text)

        if safe_text and safe_text[0].isdigit():
            safe_text = "_" + safe_text

        if not safe_text:
            safe_text = "var"

        result = f"{prefix}{safe_text}"

        if existing_names is not None:
            original_result = result
            counter = 1
            while result in existing_names:
                result = f"{original_result}_{counter}"
                counter += 1
            existing_names.add(result)

        return result

    def _parse_ini_for_draw_info(self, sections, base_path):
        draw_info, resource_map = {}, {}
        for section_name, lines in sections.items():
            if section_name.lower().startswith('[resource'):
                filename = next((l.split('=', 1)[1].strip() for l in lines if l.strip().lower().startswith('filename =')), None)
                if filename: resource_map[section_name.strip('[]')] = os.path.join(base_path, filename.replace('/', os.sep))
        for section_name, lines in sections.items():
            if section_name.lower().startswith('[textureoverride_ib'):
                ib_resource_name = next((l.split('=', 1)[1].strip() for l in lines if l.strip().lower().startswith('ib =')), None)
                if not ib_resource_name or ib_resource_name not in resource_map: continue
                ib_path, current_mesh_name = resource_map[ib_resource_name], None
                for line in lines:
                    stripped_line = line.strip()
                    mesh_match = re.search(r'\[mesh:([^\]]+)\]', stripped_line)
                    if mesh_match: current_mesh_name = mesh_match.group(1).strip(); continue
                    if current_mesh_name and stripped_line.lower().startswith('drawindexed'):
                        try:
                            parts = [int(p.strip()) for p in stripped_line.split('=')[1].strip().split(',')]
                            if len(parts) == 3:
                                draw_info[current_mesh_name] = {'draw_params': tuple(parts), 'ib_path': ib_path}
                            current_mesh_name = None
                        except (ValueError, IndexError): current_mesh_name = None
        return draw_info

    def _calculate_vertex_range(self, ib_path, draw_params):
        index_count, start_index_location, base_vertex_location = draw_params
        if not os.path.isfile(ib_path): return None, None
        try:
            with open(ib_path, 'rb') as f:
                f.seek(start_index_location * 4)
                data = f.read(index_count * 4)
                if len(data) < index_count * 4: return None, None
                indices = [idx + base_vertex_location for idx in struct.unpack(f'<{index_count}I', data)]
                return (min(indices), max(indices)) if indices else (None, None)
        except Exception: return None, None

    def _parse_classification_text_final(self, text_content):
        slot_to_name_to_objects, hash_to_objects, all_objects = OrderedDict(), OrderedDict(), []
        current_slot, current_shapekey_name = None, None
        for line in text_content.splitlines():
            line = line.strip()
            if not line or line.startswith('#'): continue
            slot_match = re.search(r'槽位\s*(\d+):', line)
            if slot_match:
                current_slot = int(slot_match.group(1))
                if current_slot not in slot_to_name_to_objects: slot_to_name_to_objects[current_slot] = OrderedDict()
                current_shapekey_name = None; continue
            name_match = re.search(r'名称:\s*(.+)', line)
            if name_match and current_slot is not None:
                current_shapekey_name = name_match.group(1).strip()
                if current_shapekey_name not in slot_to_name_to_objects[current_slot]: slot_to_name_to_objects[current_slot][current_shapekey_name] = []
                continue
            obj_match = re.search(r'物体:\s*(.+)', line)
            if obj_match and current_slot is not None and current_shapekey_name is not None:
                obj_name = obj_match.group(1).strip()
                if obj_name not in slot_to_name_to_objects[current_slot][current_shapekey_name]:
                    slot_to_name_to_objects[current_slot][current_shapekey_name].append(obj_name)
                if obj_name not in all_objects: all_objects.append(obj_name)
                hash_match = re.search(r'([a-f0-9]{8})', obj_name)
                if hash_match:
                    obj_hash = hash_match.group(1)
                    if obj_hash not in hash_to_objects: hash_to_objects[obj_hash] = []
                    if obj_name not in hash_to_objects[obj_hash]: hash_to_objects[obj_hash].append(obj_name)
        return slot_to_name_to_objects, list(hash_to_objects.keys()), hash_to_objects, all_objects

    @staticmethod
    def parse_vertex_struct(struct_definition):
        """解析顶点属性结构体定义，计算总字节数和float数量"""
        if not struct_definition or not struct_definition.strip():
            return None
        
        TYPE_SIZES = {
            'float': 4,
            'float2': 8,
            'float3': 12,
            'float4': 16,
            'int': 4,
            'int2': 8,
            'int3': 12,
            'int4': 16,
            'uint': 4,
            'uint2': 8,
            'uint3': 12,
            'uint4': 16,
            'half': 2,
            'half2': 4,
            'half3': 6,
            'half4': 8,
            'double': 8,
            'double2': 16,
            'double3': 24,
            'double4': 32,
        }
        
        total_bytes = 0
        total_floats = 0
        attributes = []
        unrecognized_types = set()
        
        lines = struct_definition.split('\n')
        for line in lines:
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('/*') or line.startswith('*'):
                continue
            
            line = line.rstrip(';').strip()
            
            parts = line.split()
            if len(parts) >= 2:
                type_name = parts[0]
                var_name = parts[1].rstrip(';')
                
                if type_name in TYPE_SIZES:
                    byte_size = TYPE_SIZES[type_name]
                    total_bytes += byte_size
                    total_floats += byte_size // 4
                    attributes.append({'type': type_name, 'name': var_name, 'size': byte_size})
                elif type_name.lower() != 'struct' and not line.endswith('{') and not line.endswith('}'):
                    unrecognized_types.add(type_name)
        
        if unrecognized_types:
            print(f"警告: 发现未识别的顶点属性类型: {', '.join(unrecognized_types)}")
        
        if total_bytes == 0:
            print(f"警告: 无法解析顶点结构体定义，total_bytes为0")
            return None
        
        if not attributes:
            print(f"警告: 未找到有效的顶点属性")
            return None
        
        return (total_bytes, total_floats, attributes)


    def _detect_vertex_format(self, base_bytes, shapekey_bytes, struct_definition=None):
        VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX = 40, 10
        num_vertices = len(base_bytes) // VERTEX_STRIDE

        if struct_definition and struct_definition.strip():
            parsed = self.parse_vertex_struct(struct_definition)
            if parsed:
                VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, attributes = parsed
                num_vertices = len(base_bytes) // VERTEX_STRIDE
                print(f"使用结构体定义: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")
                return (VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices)
            else:
                print(f"警告: 结构体定义解析失败，使用默认值")
        
        print(f"使用默认值: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")
        return (VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices)

    def _process_shapekey_buffers(self, mod_export_path, slot_to_name_to_objects, hash_to_stride):
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas

        if not NUMPY_AVAILABLE:
            print("Numpy库未找到，无法执行缓冲区优化。")
            return False

        print(f"开始处理缓冲区 (紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'})...")

        buffers_to_process = set()
        for slot, names_data in slot_to_name_to_objects.items():
            for obj in [o for name, objs in names_data.items() for o in objs]:
                hash_match = re.search(r'([a-f0-9]{8})', obj)
                if hash_match: buffers_to_process.add((hash_match.group(1), slot))

        for h, slot in sorted(list(buffers_to_process)):
            base_filename = f"{h}-Position.buf"
            base_path = os.path.join(mod_export_path, "Buffer0000", base_filename)
            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
            shapekey_path = os.path.join(mod_export_path, folder_name, base_filename)
            output_dir = os.path.join(mod_export_path, folder_name)

            print(f"  处理槽位 {slot} (哈希: {h})...")
            if not all(os.path.exists(p) for p in [base_path, shapekey_path]):
                print(f"    -> 跳过：找不到基础或形态键文件 for hash {h}, slot {slot}")
                continue
            os.makedirs(output_dir, exist_ok=True)

            try:
                with open(base_path, 'rb') as f: base_bytes = f.read()
                with open(shapekey_path, 'rb') as f: shapekey_bytes = f.read()
                if len(base_bytes) != len(shapekey_bytes):
                    print(f"    -> 跳过：文件大小不匹配 for hash {h}, slot {slot}")
                    continue

                struct_definition = self._get_vertex_struct_definition()
                VERTEX_STRIDE, NUM_FLOATS_PER_VERTEX, num_vertices = self._detect_vertex_format(base_bytes, shapekey_bytes, struct_definition)
                print(f"    -> 检测到格式: 步长={VERTEX_STRIDE}字节, 每顶点{NUM_FLOATS_PER_VERTEX}个float, 顶点数={num_vertices}")

                if h not in hash_to_stride:
                    hash_to_stride[h] = VERTEX_STRIDE

                base_data = np.frombuffer(base_bytes, dtype='f').reshape((num_vertices, NUM_FLOATS_PER_VERTEX))
                shapekey_data = np.frombuffer(shapekey_bytes, dtype='f').reshape((num_vertices, NUM_FLOATS_PER_VERTEX))

                output_prefix = os.path.join(output_dir, f"{h}-Position")

                if use_delta:
                    data_to_write = shapekey_data[:, :3] - base_data[:, :3]
                    filename_suffix = "_pos_delta"
                    if use_packed: filename_suffix = "_packed_pos_delta"

                    pos_diff_mask = ~np.isclose(base_data[:, :3], shapekey_data[:, :3], atol=1e-6).all(axis=1)
                    num_active_vertices = np.sum(pos_diff_mask)

                    if num_active_vertices == 0:
                        print(f"    -> 无位置差异，生成空文件。")
                        if use_packed:
                            open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                            open(f"{output_prefix}_map.buf", 'wb').close()
                        else:
                             open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                        continue

                    if use_packed:
                        packed_data = data_to_write[pos_diff_mask]
                        data_path = f"{output_prefix}{filename_suffix}.buf"
                        with open(data_path, 'wb') as f: f.write(packed_data.tobytes())

                        index_map = np.full(num_vertices, -1, dtype=np.int32)
                        index_map[pos_diff_mask] = np.arange(num_active_vertices, dtype=np.int32)
                        map_path = f"{output_prefix}_map.buf"
                        with open(map_path, 'wb') as f: f.write(index_map.tobytes())
                        print(f"    -> 成功生成: {os.path.basename(data_path)} 和 {os.path.basename(map_path)}")
                    else:
                        data_path = f"{output_prefix}{filename_suffix}.buf"
                        with open(data_path, 'wb') as f: f.write(data_to_write.tobytes())
                        print(f"    -> 成功生成: {os.path.basename(data_path)}")

                elif use_packed:
                    filename_suffix = "_packed"
                    diff_mask = ~np.isclose(base_data, shapekey_data, atol=1e-6).all(axis=1)
                    num_active_vertices = np.sum(diff_mask)

                    if num_active_vertices == 0:
                        print(f"    -> 无差异，生成空文件。")
                        open(f"{output_prefix}{filename_suffix}.buf", 'wb').close()
                        open(f"{output_prefix}_map.buf", 'wb').close()
                        continue

                    packed_data = shapekey_data[diff_mask]
                    data_path = f"{output_prefix}{filename_suffix}.buf"
                    with open(data_path, 'wb') as f: f.write(packed_data.tobytes())

                    index_map = np.full(num_vertices, -1, dtype=np.int32)
                    index_map[diff_mask] = np.arange(num_active_vertices, dtype=np.int32)
                    map_path = f"{output_prefix}_map.buf"
                    with open(map_path, 'wb') as f: f.write(index_map.tobytes())
                    print(f"    -> 成功生成: {os.path.basename(data_path)} 和 {os.path.basename(map_path)}")
                else:
                    print(f"    -> 标准模式，使用原始形态键文件。")
                    pass
            except Exception as e:
                print(f"    -> 处理时出错: {e}")
                return False

        print("缓冲区处理完成。")
        return True

    def _read_ini_to_ordered_dict(self, ini_file_path):
        """读取INI文件到有序字典"""
        sections = OrderedDict()
        current_section = None
        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line.startswith('[') and stripped_line.endswith(']'):
                        current_section = stripped_line
                        if current_section not in sections:
                            sections[current_section] = []
                        continue
                    if current_section:
                        sections[current_section].append(line.rstrip('\n'))
        except Exception as e:
            print(f"读取INI文件失败: {e}")
        return sections

    def _write_ordered_dict_to_ini(self, sections, ini_file_path):
        """将有序字典写入INI文件"""
        try:
            with open(ini_file_path, 'w', encoding='utf-8') as f:
                for section_name, lines in sections.items():
                    if section_name.startswith(';;'):
                        f.write(section_name + '\n')
                    else:
                        f.write(section_name + '\n')
                    for line in lines:
                        f.write(line + '\n')
                    f.write('\n')
        except Exception as e:
            print(f"写入INI文件失败: {e}")

    def _get_vertex_count(self, sections, hash_value):
        """获取顶点数量"""
        for section_name, lines in sections.items():
            if f"override_vertex_count" in section_name:
                for line in lines:
                    if line.strip().startswith("override_vertex_count"):
                        try:
                            return int(line.split('=')[1].strip())
                        except (ValueError, IndexError):
                            pass
        return None

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

    def _get_shader_template_name(self):
        """获取着色器模板名称"""
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas
        
        if use_delta and use_packed:
            return "形态anim_packed_delta_v3.hlsl"
        elif use_delta:
            return "形态anim_standard_delta_v3.hlsl"
        elif use_packed:
            return "形态anim_packed.hlsl"
        else:
            return "形态anim_standard.hlsl"

    def _get_shader_source_path(self):
        """获取着色器模板文件路径"""
        try:
            addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            asset_source_dir = os.path.join(addon_dir, "超级工具集")
            shader_template_name = self._get_shader_template_name()
            shader_source_path = os.path.join(asset_source_dir, shader_template_name)
            return shader_source_path
        except Exception as e:
            print(f"获取着色器模板路径时出错: {e}")
            return None

    def _get_vertex_struct_definition(self):
        """获取顶点属性结构体定义"""
        vertex_attrs_node = self._get_vertex_attrs_node()
        if vertex_attrs_node:
            return vertex_attrs_node.get_vertex_struct_definition()
        
        return "struct VertexAttributes {\n    float3 position;\n    float3 normal;\n    float4 tangent;\n};"

    def _update_shader_file(self, shader_path, hash_slot_data, use_packed, use_delta, unique_names, unique_objects):
        """更新着色器文件"""
        try:
            with open(shader_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            vertex_struct = self._get_vertex_struct_definition()
            if vertex_struct:
                content = re.sub(r"struct VertexAttributes\s*\{[^}]*\};", vertex_struct, content, flags=re.DOTALL)
            
            name_to_freq_def = {name: f"FREQ{i+1}" for i, name in enumerate(unique_names)}
            obj_to_range_defs = {obj: (f"START{i+1}", f"END{i+1}") for i, obj in enumerate(unique_objects)}
            
            define_lines = [f"// --- Shared Animation Intensity (per Shape Key Name) ---\n// From index {self.INTENSITY_START_INDEX} onwards"]
            for i, name in enumerate(unique_names):
                define_lines.append(f"#define FREQ{i+1} IniParams[{self.INTENSITY_START_INDEX + i}].x // {name}")
            
            define_lines.extend([f"\n// --- Per-Object Vertex Ranges ---\n// From index {self.VERTEX_RANGE_START_INDEX} onwards"])
            for i, obj_name in enumerate(unique_objects):
                start_idx = self.VERTEX_RANGE_START_INDEX + i * 2
                define_lines.append(f"#define START{i+1} (uint)IniParams[{start_idx}].x // {obj_name}")
                define_lines.append(f"#define END{i+1}   (uint)IniParams[{start_idx + 1}].x")
            
            logic_lines = []
            
            for slot_num, names_data in sorted(hash_slot_data.items()):
                slot_index = slot_num - 1
                is_first_if = True
                
                logic_lines.extend([f"    // --- Slot {slot_index} (t{51+slot_index}) ---", f"    float anim_weight_slot{slot_index} = 0.0;"])
                for name, objects in names_data.items():
                    for obj in objects:
                        start_def, end_def = obj_to_range_defs[obj]
                        if_cmd = "if" if is_first_if else "else if"
                        logic_lines.append(f"    {if_cmd} (i >= {start_def} && i <= {end_def}) {{ anim_weight_slot{slot_index} = {name_to_freq_def[name]}; }} // Name: {name}")
                        is_first_if = False
                
                logic_lines.extend([f"    if (anim_weight_slot{slot_index} > 1e-5)", "    {"])
                
                indent = "        "
                read_idx = "i"
                if use_packed:
                    logic_lines.extend([f"        int packed_index = shapekey_maps[{slot_index}][i];", "        if (packed_index != -1)", "        {"])
                    read_idx = "packed_index"
                    indent = "            "
                
                if use_delta:
                    calc_line = f"total_diff_position += shapekey_pos_deltas[{slot_index}][{read_idx}] * anim_weight_slot{slot_index};"
                else: 
                    calc_line = f"total_diff_position += (shapekeys[{slot_index}][{read_idx}].position - base[i].position) * anim_weight_slot{slot_index};"

                logic_lines.append(indent + calc_line)

                if use_packed: logic_lines.extend(["        }", "    }\n"])
                else: logic_lines.extend(["    }\n"])

            content = re.sub(r"// --- \[PYTHON-MANAGED BLOCK START\] ---.*?// --- \[PYTHON-MANAGED BLOCK END\] ---",
                             f"// --- [PYTHON-MANAGED BLOCK START] ---\n{chr(10).join(define_lines)}\n// --- [PYTHON-MANAGED BLOCK END] ---",
                             content, flags=re.DOTALL)
            content = re.sub(r"// --- \[PYTHON-MANAGED LOGIC START\] ---.*?// --- \[PYTHON-MANAGED LOGIC END\] ---",
                             f"// --- [PYTHON-MANAGED LOGIC START] ---\n{chr(10).join(logic_lines)}    // --- [PYTHON-MANAGED LOGIC END] ---",
                             content, flags=re.DOTALL)
            
            with open(shader_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}"
            print(f"成功更新着色器 ({mode_str})，支持 {len(hash_slot_data)} 个槽位。")
            return True
        except Exception as e:
            print(f"更新着色器文件失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def execute_postprocess(self, mod_export_path):
        print(f"形态键配置后处理节点开始执行，Mod导出路径: {mod_export_path}")

        classification_text_obj = next((t for t in bpy.data.texts if "Shape_Key_Classification" in t.name), None)
        if not classification_text_obj:
            print("未找到 'Shape_Key_Classification' 文本")
            return

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("路径中未找到任何.ini文件")
            return

        target_ini_file = ini_files[0]
        use_packed = self.use_packed_buffers
        use_delta = self.store_deltas
        
        if (use_packed or use_delta) and not NUMPY_AVAILABLE:
            print("Numpy库未找到，无法使用优化功能")
            return

        shader_source_path = self._get_shader_source_path()
        if not shader_source_path or not os.path.exists(shader_source_path):
            print(f"着色器模板文件未找到: {shader_source_path}")
            return

        print(f"使用着色器模板: {self._get_shader_template_name()}")

        self._create_cumulative_backup(target_ini_file, mod_export_path)

        try:
            sections = self._read_ini_to_ordered_dict(target_ini_file)
            slot_to_name_to_objects, unique_hashes, hash_to_objects, all_objects = self._parse_classification_text_final(classification_text_obj.as_string())
            
            if not slot_to_name_to_objects:
                print("分类文本解析失败或为空")
                return

            hash_to_stride = {}
            if not self._process_shapekey_buffers(mod_export_path, slot_to_name_to_objects, hash_to_stride):
                print("缓冲区处理失败")
                return

            all_unique_names = list(OrderedDict.fromkeys(name for slot_data in slot_to_name_to_objects.values() for name in slot_data.keys()))
            all_unique_objects = list(OrderedDict.fromkeys(obj for slot_data in slot_to_name_to_objects.values() for name_data in slot_data.values() for obj in name_data))

            hash_to_base_resources = {}
            resource_pattern = re.compile(r'\[(Resource([a-f0-9]{8})Position(\d*))\]')
            for section_name in sections.keys():
                match = resource_pattern.match(section_name)
                if match:
                    full_name, hash_val, number = match.groups()
                    if hash_val not in hash_to_base_resources:
                        hash_to_base_resources[hash_val] = []
                    hash_to_base_resources[hash_val].append((int(number) if number else 1, full_name))
            for hash_val in hash_to_base_resources:
                hash_to_base_resources[hash_val].sort()
                hash_to_base_resources[hash_val] = [name for key, name in hash_to_base_resources[hash_val]]

            print("开始自动计算顶点索引范围...")
            draw_info_map = self._parse_ini_for_draw_info(sections, mod_export_path)
            calculated_ranges = {
                obj_name: self._calculate_vertex_range(draw_info_map[obj_name]['ib_path'], draw_info_map[obj_name]['draw_params'])
                for obj_name in all_objects if obj_name in draw_info_map
            }

            dest_res_dir = os.path.join(mod_export_path, "res")
            os.makedirs(dest_res_dir, exist_ok=True)

            hash_to_shader_paths = {}
            for hash_val in unique_hashes:
                shader_dest_path = os.path.join(dest_res_dir, f"形态anim_{hash_val}.hlsl")
                shutil.copy2(shader_source_path, shader_dest_path)
                hash_to_shader_paths[hash_val] = shader_dest_path
                print(f"已创建独立着色器文件: 形态anim_{hash_val}.hlsl")

            for hash_val in unique_hashes:
                hash_objects = hash_to_objects.get(hash_val, [])
                hash_slot_data = {}
                for slot, name_data in slot_to_name_to_objects.items():
                    for name, objects in name_data.items():
                        if any(obj in hash_objects for obj in objects):
                            if slot not in hash_slot_data:
                                hash_slot_data[slot] = {}
                            hash_slot_data[slot][name] = [obj for obj in objects if obj in hash_objects]

                if hash_slot_data:
                    hash_unique_names = list(OrderedDict.fromkeys(name for slot_data in hash_slot_data.values() for name in slot_data.keys()))
                    hash_unique_objects = list(OrderedDict.fromkeys(obj for slot_data in hash_slot_data.values() for name_data in slot_data.values() for obj in name_data))
                    
                    if not self._update_shader_file(hash_to_shader_paths[hash_val], hash_slot_data, use_packed, use_delta, hash_unique_names, hash_unique_objects):
                        print(f"更新哈希 {hash_val} 的着色器文件失败")

            vertex_counts = {
                m.group(1): int(l.split('=')[1].strip())
                for s, ls in sections.items()
                for m in [re.search(r'\[TextureOverride_([a-f0-9]{8})_[^_]*_VertexLimitRaise\]', s)]
                if m for l in ls if l.strip().startswith('override_vertex_count')
            }
            
            if '[Constants]' not in sections:
                sections['[Constants]'] = []
            constants_lines = sections['[Constants]']
            constants_content = "".join(constants_lines)
            vars_to_define = set()

            existing_param_names = set()
            shapekey_freq_params = {}
            for name in all_unique_names:
                shapekey_freq_params[name] = self._create_safe_var_name(name, prefix="$Freq_", existing_names=existing_param_names)

            constants_lines.append("\n; --- Auto-generated Shape Key Intensity Controls (Additive Blending) ---")
            for name, param in shapekey_freq_params.items():
                if param not in constants_content:
                    constants_lines.append(f"; 控制形态键 '{name}' 的强度")
                    constants_lines.append(f"global {param} = 0.0")

            constants_lines.append("\n; --- Auto-generated Vertex Ranges for Shape Keys ---")
            existing_vertex_range_names = set()
            vertex_range_vars = {}
            for obj_name, (start_v, end_v) in calculated_ranges.items():
                if start_v is None:
                    continue
                safe_name = self._create_safe_var_name(obj_name.replace("-", "_"), existing_names=existing_vertex_range_names)
                start_var, end_var = f"$SV_{safe_name}", f"$EV_{safe_name}"
                vertex_range_vars[obj_name] = (start_var, end_var)
                if start_var not in constants_content:
                    constants_lines.append(f"global {start_var} = {start_v}")
                if end_var not in constants_content:
                    constants_lines.append(f"global {end_var} = {end_v}")

            for h in unique_hashes:
                base_resources = hash_to_base_resources.get(h, [])
                res_to_post = base_resources if base_resources else [f"Resource{h}Position"]
                for res_name in res_to_post:
                    if f"post {res_name} = copy_desc" not in constants_content:
                        constants_lines.append(f"post {res_name} = copy_desc {res_name}_0")
                if len(base_resources) > 1:
                    vars_to_define.add("$swapkey100")
                if f"post run = CustomShader_{h}_Anim" not in constants_content:
                    constants_lines.append(f"post run = CustomShader_{h}_Anim")

            if vars_to_define:
                constants_lines.append("\n; --- Auto-generated Base Mesh Switch Key ---")
                for var in sorted(list(vars_to_define)):
                    if f"global persist {var}" not in constants_content and f"global {var}" not in constants_content:
                        constants_lines.append(f"global persist {var} = 1")

            if '[Present]' not in sections:
                sections['[Present]'] = []
            present_lines = sections['[Present]']
            present_content = "".join(present_lines)
            if 'if $active0 == 1' not in present_content:
                present_lines.extend(['if $active0 == 1', *[f"    run = CustomShader_{h}_Anim" for h in unique_hashes], 'endif'])

            hash_to_slots = {
                h: sorted([s for s, nd in slot_to_name_to_objects.items() if any(h in o for n in nd for o in nd[n])])
                for h in unique_hashes
            }

            compute_blocks_to_add = OrderedDict()
            for h in unique_hashes:
                block_name = f"[CustomShader_{h}_Anim]"
                if block_name in sections:
                    continue

                hash_objects = hash_to_objects.get(h, [])
                hash_slot_data = {}
                for slot, name_data in slot_to_name_to_objects.items():
                    for name, objects in name_data.items():
                        if any(obj in hash_objects for obj in objects):
                            if slot not in hash_slot_data:
                                hash_slot_data[slot] = {}
                            hash_slot_data[slot][name] = [obj for obj in objects if obj in hash_objects]

                if hash_slot_data:
                    hash_unique_names = list(OrderedDict.fromkeys(name for slot_data in hash_slot_data.values() for name in slot_data.keys()))
                    hash_unique_objects = list(OrderedDict.fromkeys(obj for slot_data in hash_slot_data.values() for name_data in slot_data.values() for obj in name_data))

                    block_lines = ["\n    ; --- Shared Intensity Controls (per Shape Key Name) ---"]
                    for i, name in enumerate(hash_unique_names):
                        if shapekey_freq_params.get(name):
                            block_lines.append(f"    x{self.INTENSITY_START_INDEX + i} = {shapekey_freq_params.get(name)} \n; {name}")
                    block_lines.append("\n    ; --- Per-Object Vertex Range Controls ---")
                    for i, obj_name in enumerate(hash_unique_objects):
                        if obj_name in calculated_ranges and calculated_ranges[obj_name][0] is not None:
                            start_var, end_var = vertex_range_vars.get(obj_name, (f"$SV_unknown", f"$EV_unknown"))
                            block_lines.append(f"    x{self.VERTEX_RANGE_START_INDEX + i*2} = {start_var} \n; {obj_name} Start")
                            block_lines.append(f"    x{self.VERTEX_RANGE_START_INDEX + i*2 + 1} = {end_var} \n; {obj_name} End")

                    t_registers_to_null = []
                    slots_for_hash = hash_to_slots.get(h, [])

                    if not use_delta:
                        block_lines.append(f"\n    cs-t50 = copy Resource{h}Position0000")
                        t_registers_to_null.append("cs-t50")

                    res_suffix = "_packed_pos_delta" if use_packed and use_delta else \
                                 "_pos_delta" if use_delta else \
                                 "_packed" if use_packed else ""

                    mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}"
                    block_lines.append(f"\n    ; --- Binding Shape Key Buffers (Mode: {mode_str}) ---")
                    for slot in slots_for_hash:
                        res_name = f"Resource{h}Position100{slot}{res_suffix}"
                        if not (use_packed or use_delta):
                            res_name = f"Resource{h}Position100{slot}"

                        t_reg = 51 + slot - 1
                        block_lines.append(f"    cs-t{t_reg} = copy {res_name}")
                        t_registers_to_null.append(f"cs-t{t_reg}")
                        if use_packed:
                            map_reg = 75 + slot - 1
                            block_lines.append(f"    cs-t{map_reg} = copy Resource{h}Position100{slot}_Map")
                            t_registers_to_null.append(f"cs-t{map_reg}")

                    block_lines.append(f"    cs = ./res/形态anim_{h}.hlsl")

                    base_resources = hash_to_base_resources.get(h, [])
                    res_to_bind = base_resources if base_resources else [f"Resource{h}Position"]
                    if len(res_to_bind) > 1:
                        block_lines.append(f"\n    ; --- Base Mesh Switching ---")
                        for i, res_name in enumerate(res_to_bind, 1):
                            block_lines.extend([f"    if $swapkey100 == {i}", f"        cs-u5 = copy {res_name}_0", f"        {res_name} = ref cs-u5", "    endif"])
                    else:
                        res_name = res_to_bind[0]
                        block_lines.extend([f"    cs-u5 = copy {res_name}_0", f"    {res_name} = ref cs-u5"])

                    dispatch_count = vertex_counts.get(h, 0)
                    block_lines.extend([f"    Dispatch = {dispatch_count}, 1, 1", "    cs-u5 = null", *[f"    {reg} = null" for reg in sorted(list(set(t_registers_to_null)))]])
                    compute_blocks_to_add[block_name] = block_lines

            new_resource_lines = []
            generated_section_names = set()

            for h in unique_hashes:
                section_name = f"[Resource{h}Position0000]"
                if section_name not in sections and section_name not in generated_section_names:
                    stride = hash_to_stride.get(h, 40)
                    new_resource_lines.extend([section_name, "type = Buffer", f"stride = {stride}", f"filename = Buffer0000/{h}-Position.buf", ""])
                    generated_section_names.add(section_name)

            for slot, names_data in slot_to_name_to_objects.items():
                for obj in [o for name, objs in names_data.items() for o in objs]:
                    hash_match = re.search(r'([a-f0-9]{8})', obj)
                    if hash_match:
                        h = hash_match.group(1)
                        base_stride = hash_to_stride.get(h, 40)
                        stride, filename, section_name = 0, "", ""
                        if use_delta:
                            res_suffix = "_packed_pos_delta" if use_packed else "_pos_delta"
                            stride = 12
                        elif use_packed:
                            res_suffix = "_packed"
                            stride = base_stride
                        else:
                            res_suffix = ""
                            stride = base_stride

                        if use_delta or use_packed:
                            section_name = f"[Resource{h}Position100{slot}{res_suffix}]"
                            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
                            filename = f"{folder_name}/{h}-Position{res_suffix}.buf"
                            if section_name not in sections and section_name not in generated_section_names:
                                new_resource_lines.extend([section_name, "type = Buffer", f"stride = {stride}", f"filename = {filename}", ""])
                                generated_section_names.add(section_name)

                        if use_packed:
                            map_section = f"[Resource{h}Position100{slot}_Map]"
                            folder_name = f"Buffer100{slot}" if slot < 10 else f"Buffer10{slot}"
                            if map_section not in sections and map_section not in generated_section_names:
                                new_resource_lines.extend([map_section, "type = Buffer", "stride = 4", f"filename = {folder_name}/{h}-Position_map.buf", ""])
                                generated_section_names.add(map_section)

            if new_resource_lines:
                sections[";; --- Generated Shape Key Buffers ---"] = new_resource_lines

            for h in unique_hashes:
                for res_name in hash_to_base_resources.get(h, [f"Resource{h}Position"]):
                    if f"[{res_name}]" in sections and not any(f"[{res_name}_0]" in line for line in sections[f"[{res_name}]"]):
                        sections[f"[{res_name}]"].insert(0, f"[{res_name}_0]")

            sections.update(compute_blocks_to_add)
            self._write_ordered_dict_to_ini(sections, target_ini_file)

            mode_str = f"紧凑:{'是' if use_packed else '否'}, 增量(仅位置):{'是' if use_delta else '否'}"
            print(f"形态键配置({mode_str})已生成到 {os.path.basename(target_ini_file)}")

        except Exception as e:
            print(f"生成形态键配置时发生未知错误: {e}")
            import traceback
            traceback.print_exc()

        print("形态键配置后处理节点执行完成")


classes = (
    SSMTNode_PostProcess_ShapeKey,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
