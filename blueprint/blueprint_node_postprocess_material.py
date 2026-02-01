import bpy
import os
import glob
import re
from collections import OrderedDict
import shutil

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_Material(SSMTNode_PostProcess_Base):
    '''材质转资源后处理节点：根据场景物体的材质和纹理创建资源引用'''
    bl_idname = 'SSMTNode_PostProcess_Material'
    bl_label = '材质转资源'
    bl_description = '根据场景物体的材质和纹理创建资源引用'

    material_to_resource_override: bpy.props.BoolProperty(
        name="覆盖现有资源",
        description="如果资源已存在，则覆盖它",
        default=False
    )
    material_switch_var: bpy.props.StringProperty(
        name="材质切换变量",
        description="用于材质切换的起始变量名(会自动递增)",
        default="$swapkey150"
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "material_to_resource_override")
        layout.prop(self, "material_switch_var")

    def extract_mesh_name(self, line):
        match = re.search(r'\[mesh:([^\]]+)\]', line)
        return match.group(1) if match else None

    def find_object_by_mesh_name(self, mesh_name):
        if mesh_name in bpy.data.objects:
            return bpy.data.objects[mesh_name]
        clean_name = re.sub(r'^[a-f0-9]+-[\d]+-', '', mesh_name)
        return bpy.data.objects.get(clean_name)

    def extract_transparency_info_from_mesh_name(self, mesh_name):
        match = re.search(r'(.+)_透明(\d+(\.\d+)?)', mesh_name)
        if match:
            base_name = match.group(1)
            transparency_value = match.group(2)
            shader_name = f"CustomShaderTransparencyCloth{base_name.replace('-', '_').replace('.', '_')}"
            return shader_name, transparency_value
        return None, None

    def extract_texture_type_from_resource(self, resource_name):
        match = re.search(r'_Slot_([^_]+)$', resource_name)
        if match:
            return match.group(1)

        match = re.search(r'Resource-[a-fA-F0-9]+-\d+-([^_]+)$', resource_name)
        if match:
            return match.group(1)

        return None

    def build_mapping_for_section(self, lines):
        mapping = OrderedDict()
        line_pattern = re.compile(r'^(ps-t\d+|Resource\\[^\s=]+)\s*=\s*(?:ref\s+)?(.*)$')
        for line in lines:
            resource_match = line_pattern.match(line.strip())
            if resource_match:
                param_name = resource_match.group(1).strip()
                resource_name = resource_match.group(2).strip()
                texture_type = self.extract_texture_type_from_resource(resource_name)
                if texture_type:
                    mapping[param_name] = texture_type
        return mapping

    def find_matching_materials(self, obj, texture_type):
        matching_materials = []
        texture_type_lower = texture_type.lower()
        for material_slot in obj.material_slots:
            material = material_slot.material
            if not material: continue
            material_first_word = material.name.split('_')[0].lower()
            if material_first_word == texture_type_lower:
                matching_materials.append(material)
        return matching_materials

    def get_texture_from_material(self, material):
        if not material or not material.use_nodes:
            return None
        try:
            output_node = next(n for n in material.node_tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output)
            surface_input = output_node.inputs.get('Surface')
            if surface_input and surface_input.is_linked:
                def find_texture_node_recursively(node):
                    if node.type == 'TEX_IMAGE' and node.image:
                        return node.image
                    for input_socket in node.inputs:
                        if input_socket.is_linked:
                            found_image = find_texture_node_recursively(input_socket.links[0].from_node)
                            if found_image: return found_image
                    return None
                linked_image = find_texture_node_recursively(surface_input.links[0].from_node)
                if linked_image: return linked_image
        except (StopIteration, AttributeError):
            pass
        for node in material.node_tree.nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                return node.image
        return None

    def copy_texture_file(self, texture_image, target_folder, material):
        if not texture_image or not texture_image.filepath:
            return None
        try:
            source_path = bpy.path.abspath(texture_image.filepath)
            if not os.path.exists(source_path): return None
            os.makedirs(target_folder, exist_ok=True)

            _, file_extension = os.path.splitext(os.path.basename(source_path))
            new_filename = f"{material.name}{file_extension}"

            target_path = os.path.join(target_folder, new_filename)
            if os.path.exists(target_path) and not self.material_to_resource_override:
                return new_filename
            shutil.copy2(source_path, target_path)
            return new_filename
        except Exception as e:
            print(f"复制纹理文件失败: {e}")
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

    def define_swapkeys_in_sections(self, sections, keys_to_define):
        if not keys_to_define: return
        if '[Constants]' not in sections:
            new_sections = OrderedDict([('[Constants]', [])])
            new_sections.update(sections)
            sections.clear()
            sections.update(new_sections)
        constants_lines = sections['[Constants]']
        existing_definitions = "".join(constants_lines)
        for key in sorted(list(keys_to_define)):
            if key not in existing_definitions:
                definition = f"global persist {key} = 0"
                constants_lines.append(definition)

    def generate_material_lines(self, matching_materials, param_name, texture_type, obj,
                                texture_folder, all_sections,
                                object_to_diffuse_swapkey, material_group_to_swapkey,
                                swap_key_prefix, next_swap_key_num, used_swap_keys):
        generated_lines = []
        brightness_param_name = r"$\RabbitFX\brightness"

        if len(matching_materials) == 1:
            material = matching_materials[0]
            if texture_type == 'Glowmap':
                match = re.search(r'^Glowmap_(\d+)_', material.name, re.IGNORECASE)
                if match:
                    generated_lines.append(f"{brightness_param_name} = {match.group(1)}")

            new_line = self.create_resource_entry(material, param_name, texture_folder, all_sections)
            if new_line:
                generated_lines.append(new_line)

        elif len(matching_materials) > 1:
            current_swap_variable = None
            if texture_type != 'DiffuseMap' and obj.name in object_to_diffuse_swapkey:
                current_swap_variable = object_to_diffuse_swapkey[obj.name]
            else:
                mat_names_tuple = tuple(sorted([mat.name for mat in matching_materials]))
                if mat_names_tuple not in material_group_to_swapkey:
                    new_swap_key = f"{swap_key_prefix}{next_swap_key_num}"
                    material_group_to_swapkey[mat_names_tuple] = new_swap_key
                    next_swap_key_num += 1
                current_swap_variable = material_group_to_swapkey[mat_names_tuple]

                if texture_type == 'DiffuseMap':
                    object_to_diffuse_swapkey[obj.name] = current_swap_variable

            used_swap_keys.add(current_swap_variable)

            generated_lines.append(f"; {texture_type} 材质切换 (组: {current_swap_variable})")
            for index, material in enumerate(matching_materials):
                new_line = self.create_resource_entry(material, param_name, texture_folder, all_sections)
                if new_line:
                    generated_lines.append(f"if {current_swap_variable} == {index}")
                    if texture_type == 'Glowmap':
                        match = re.search(r'^Glowmap_(\d+)_', material.name, re.IGNORECASE)
                        if match:
                            generated_lines.append(f"    {brightness_param_name} = {match.group(1)}")
                    generated_lines.append(f"    {new_line}")
                    generated_lines.append("endif")
            generated_lines.append("")

        return generated_lines, next_swap_key_num

    def create_resource_entry(self, material, param_name, texture_folder, all_sections):
        texture_image = self.get_texture_from_material(material)
        if not texture_image: return None
        copied_filename = self.copy_texture_file(texture_image, texture_folder, material)
        if not copied_filename: return None
        new_resource_name = f"Resource_{material.name}"
        resource_section_name = f"[{new_resource_name}]"
        if resource_section_name not in all_sections or self.material_to_resource_override:
            all_sections[resource_section_name] = [f"filename = Texture/{copied_filename}".replace("\\", "/")]
        return "{} = {}".format(param_name, new_resource_name) if not param_name.lower().startswith("resource\\") else "{} = ref {}".format(param_name, new_resource_name)

    def process_texture_override_section(self, section_name, all_sections,
                                          material_group_to_swapkey, swap_key_prefix, next_swap_key_num,
                                          used_swap_keys, transparency_sections_to_add):
        lines = all_sections[section_name]
        ini_mapping = self.build_mapping_for_section(lines)
        texture_folder = os.path.join(os.path.dirname(all_sections.get('_config_path', '')), "Texture")
        object_to_diffuse_swapkey = {}

        mesh_lines_info_phase1 = [(i, self.extract_mesh_name(line)) for i, line in enumerate(lines) if self.extract_mesh_name(line)]
        for insert_index, mesh_name in reversed(mesh_lines_info_phase1):
            obj = self.find_object_by_mesh_name(mesh_name)
            if not obj or not obj.material_slots: continue
            new_lines_for_this_mesh = []
            generated_zzmi_style, generated_rabbitfx_style, generated_glowmap, generated_fxmap = False, False, False, False
            is_pst_style = any(k.lower().startswith("ps-t") for k in ini_mapping.keys())
            is_zzmi_style = any(k.lower().startswith("resource\\zzmi\\") for k in ini_mapping.keys())
            if is_pst_style or is_zzmi_style:
                for param_name, texture_type in ini_mapping.items():
                    if not (param_name.lower().startswith("ps-t") or param_name.lower().startswith("resource\\zzmi\\")): continue
                    if param_name.lower().startswith("resource\\zzmi\\"): generated_zzmi_style = True
                    matching_materials = self.find_matching_materials(obj, texture_type)
                    if matching_materials:
                        generated_lines, next_swap_key_num = self.generate_material_lines(
                            matching_materials, param_name, texture_type, obj, texture_folder, all_sections,
                            object_to_diffuse_swapkey, material_group_to_swapkey,
                            swap_key_prefix, next_swap_key_num, used_swap_keys)
                        new_lines_for_this_mesh.extend(generated_lines)
            for texture_type in ['Glowmap', 'FXMap']:
                matching_materials = self.find_matching_materials(obj, texture_type)
                if matching_materials:
                    param_name = f"Resource\\RabbitFX\\{texture_type}"
                    generated_rabbitfx_style = True
                    if texture_type == 'Glowmap': generated_glowmap = True
                    if texture_type == 'FXMap': generated_fxmap = True
                    generated_lines, next_swap_key_num = self.generate_material_lines(
                        matching_materials, param_name, texture_type, obj, texture_folder, all_sections,
                        object_to_diffuse_swapkey, material_group_to_swapkey,
                        swap_key_prefix, next_swap_key_num, used_swap_keys)
                    new_lines_for_this_mesh.extend(generated_lines)
            if generated_zzmi_style: new_lines_for_this_mesh.append("run = CommandList\\ZZMI\\SetTextures")
            if generated_rabbitfx_style: new_lines_for_this_mesh.append("run = CommandList\\RabbitFX\\Run")
            lines[insert_index + 1:insert_index + 1] = new_lines_for_this_mesh
            reset_lines = []
            if generated_glowmap: reset_lines.extend(["Resource\\RabbitFX\\Glowmap = ref null", r"$\RabbitFX\brightness = 0"])
            if generated_fxmap: reset_lines.append("Resource\\RabbitFX\\FXMap = ref null")
            if reset_lines:
                reset_lines.append("run = CommandList\\RabbitFX\\Run")
                draw_idx = -1
                search_end_idx = len(lines)
                for i in range(insert_index + 1, len(lines)):
                    if '[mesh:' in lines[i]:
                        search_end_idx = i
                        break
                for i in range(insert_index + 1, search_end_idx):
                    if 'drawindexed' in lines[i]:
                        draw_idx = i
                        break
                if draw_idx != -1:
                    lines[draw_idx + 1:draw_idx + 1] = reset_lines
        mesh_lines_info_phase2 = [(i, self.extract_mesh_name(line)) for i, line in enumerate(lines) if self.extract_mesh_name(line)]
        for mesh_index, mesh_name in reversed(mesh_lines_info_phase2):
            transparency_shader_name, transparency_value = self.extract_transparency_info_from_mesh_name(mesh_name)
            if transparency_shader_name:
                if transparency_shader_name not in transparency_sections_to_add:
                    transparency_sections_to_add[transparency_shader_name] = [
                        "blend = ADD BLEND_FACTOR INV_BLEND_FACTOR",
                        f"blend_factor[0] = {transparency_value}", f"blend_factor[1] = {transparency_value}",
                        f"blend_factor[2] = {transparency_value}", "blend_factor[3] = 1",
                        "handling = skip",
                        "; --- Start of Overridden Mesh Content ---"
                    ]
                lines.insert(mesh_index + 1, f"run = {transparency_shader_name}")
                start_move_idx = mesh_index + 2
                end_move_idx = -1
                for i in range(start_move_idx, len(lines)):
                    if 'drawindexed' in lines[i]:
                        end_move_idx = i + 1
                        break
                    if '[mesh:' in lines[i] or (lines[i].strip().startswith('[') and not lines[i].strip().startswith('[mesh:')):
                        end_move_idx = i
                        break
                if end_move_idx == -1: end_move_idx = len(lines)
                if start_move_idx < end_move_idx:
                    block_to_move = lines[start_move_idx:end_move_idx]
                    filtered_block_to_move = [
                        line for line in block_to_move
                        if not any(keyword in line for keyword in ["Resource\\RabbitFX\\Glowmap = ref null", r"$\RabbitFX\brightness = 0", "Resource\\RabbitFX\\FXMap = ref null"])
                    ]
                    final_block = []
                    for line in filtered_block_to_move:
                        if "run = CommandList\\RabbitFX\\Run" in line:
                            has_resource_before = any("Resource\\RabbitFX" in prev_line for prev_line in final_block)
                            if has_resource_before:
                                final_block.append(line)
                        else:
                            final_block.append(line)
                    transparency_sections_to_add[transparency_shader_name].extend(final_block)
                    del lines[start_move_idx:end_move_idx]
        return next_swap_key_num

    def execute_postprocess(self, mod_export_path):
        print(f"材质转资源后处理节点开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("在路径中未找到任何.ini文件")
            return

        for ini_file in ini_files:
            self._create_cumulative_backup(ini_file, mod_export_path)

            with open(ini_file, 'r', encoding='utf-8') as f:
                content = f.read()

            sections = OrderedDict()
            current_section = None
            for line in content.splitlines():
                stripped = line.strip()
                if stripped.startswith('[') and stripped.endswith(']'):
                    current_section = stripped
                    sections[current_section] = []
                elif current_section:
                    sections[current_section].append(line)

            sections['_config_path'] = mod_export_path

            transparency_sections_to_add = OrderedDict()
            used_swap_keys = set()
            material_group_to_swapkey = {}
            base_swap_var = self.material_switch_var
            match = re.match(r'(\$\w+)(\d+)', base_swap_var)
            swap_key_prefix = match.group(1) if match else base_swap_var
            next_swap_key_num = int(match.group(2)) if match else 0

            for section_name, lines in list(sections.items()):
                if section_name.startswith('[TextureOverride_') and section_name != '_config_path':
                    next_swap_key_num = self.process_texture_override_section(
                        section_name, sections,
                        material_group_to_swapkey, swap_key_prefix, next_swap_key_num,
                        used_swap_keys, transparency_sections_to_add
                    )

            del sections['_config_path']

            self.define_swapkeys_in_sections(sections, used_swap_keys)

            new_content = []
            for section_name, lines in sections.items():
                new_content.append(section_name)
                new_content.extend(lines)
                new_content.append('')

            if transparency_sections_to_add:
                new_content.append('\n;MARK:CustomShaderTransparency----------------------------------------------------------')
                for shader_name, lines in transparency_sections_to_add.items():
                    new_content.append(f"[{shader_name}]")
                    new_content.extend(lines)
                    new_content.append('')

            with open(ini_file, 'w', encoding='utf-8') as f:
                f.write("\n".join(new_content))

        print("材质转资源引用完成！")


classes = (
    SSMTNode_PostProcess_Material,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
