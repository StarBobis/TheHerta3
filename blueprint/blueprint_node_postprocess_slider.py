import bpy
import os
import glob
import re
import shutil
from collections import OrderedDict

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_SliderPanel(SSMTNode_PostProcess_Base):
    '''滑块面板后处理节点：扫描INI文件中的形态键强度参数，并为其生成可交互的滑块UI'''
    bl_idname = 'SSMTNode_PostProcess_SliderPanel'
    bl_label = '滑块面板'
    bl_description = '扫描INI文件中的形态键强度参数，并为其生成可交互的滑块UI'

    create_cumulative_backup: bpy.props.BoolProperty(
        name="创建累积备份",
        description="是否在修改前创建备份文件",
        default=True
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "create_cumulative_backup")

    def execute_postprocess(self, mod_export_path):
        print(f"滑块面板后处理节点开始执行，Mod导出路径: {mod_export_path}")

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("路径中未找到任何.ini文件")
            return

        target_ini_file = ini_files[0]

        try:
            with open(target_ini_file, 'r', encoding='utf-8') as f:
                if "; --- AUTO-APPENDED SLIDER CONTROL PANEL ---" in f.read():
                    print("滑块面板配置已存在于文件中。请手动删除后再生成。")
                    return
        except Exception as e:
            print(f"读取目标INI文件以进行检查时出错: {e}")
            return

        try:
            with open(target_ini_file, 'r', encoding='utf-8') as f:
                original_content = f.read()

            if self.create_cumulative_backup:
                self._create_cumulative_backup(target_ini_file, mod_export_path)
        except Exception as e:
            print(f"创建备份时出错: {e}")
            return

        try:
            addon_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            asset_subdir_name = "超级工具集"
            source_asset_dir = os.path.join(addon_dir, asset_subdir_name)

            dest_res_dir = os.path.join(mod_export_path, "res")
            os.makedirs(dest_res_dir, exist_ok=True)

            shader_source_path = os.path.join(source_asset_dir, "draw_2d.hlsl")
            shader_dest_path = os.path.join(dest_res_dir, "draw_2d.hlsl")
            if os.path.exists(shader_source_path):
                if not os.path.exists(shader_dest_path):
                    shutil.copy2(shader_source_path, shader_dest_path)
                    print(f"已复制 draw_2d.hlsl 到 {dest_res_dir}")
            else:
                print(f"警告: 未找到 'draw_2d.hlsl' 模板, 滑块UI可能无法显示。路径: {shader_source_path}")

            images_to_copy = ['0.png', '1.png', '2.png', '3.png']
            print("正在检查并复制滑块UI图片...")
            for image_name in images_to_copy:
                source_image_path = os.path.join(source_asset_dir, image_name)
                dest_image_path = os.path.join(dest_res_dir, image_name)
                if os.path.exists(source_image_path):
                    if not os.path.exists(dest_image_path):
                        shutil.copy2(source_image_path, dest_image_path)
                        print(f"已复制 {image_name} 到 {dest_res_dir}")
                else:
                    print(f"警告: UI图片 '{image_name}' 在插件目录中未找到。路径: {source_image_path}")
        except Exception as e:
            print(f"准备和复制资源文件时出错: {e}")
            return

        sections = self._read_ini_to_ordered_dict(target_ini_file)
        if not sections:
            print(f"无法读取或解析INI文件: {target_ini_file}")
            return

        freq_params = set()
        param_pattern = re.compile(r'^\s*global\s+(\$Freq_[^\s=]+)')
        if '[Constants]' in sections:
            for line in sections['[Constants]']:
                match = param_pattern.match(line)
                if match:
                    freq_params.add(match.group(1))

        sorted_freq_params = sorted(list(freq_params))
        num_sliders = len(sorted_freq_params)

        if num_sliders == 0:
            print("在INI文件的[Constants]块中未找到任何形态键强度参数 (如 global $Freq_...)")
            return

        print(f"找到 {num_sliders} 个形态键强度参数，开始生成滑块面板...")

        child_height = 0.03
        top_bottom_padding = 0.03
        spacing = 0.02
        total_slider_height = num_sliders * child_height
        total_spacing_height = max(0, (num_sliders - 1) * spacing)
        parent_height = total_slider_height + total_spacing_height + (top_bottom_padding * 2)

        content = []
        constants_lines = []
        present_logic = []

        content.extend([
            "; Author: HammyCatte & Assistant",
            f"; Description: Dynamically generated 3Dmigoto overlay for {num_sliders} shape key sliders.",
            "; Version: 1.1 (Auto-generated & Appended, Refactored)",
            "\n; 配置区 ---------------------------------------------------------",
            "\n; ※※ 必须配置 ※※",
            "\n; 1. 配置图片资源 (插件已自动复制, 位于res文件夹)",
            "[ResourceImageToRender0]", "filename = ./res/0.png",
            "\n[ResourceSliderHandle]", "filename = ./res/1.png",
            "\n[ResourceLeftBar]", "filename = ./res/2.png",
            "\n[ResourceRightBar]", "filename = ./res/3.png",
            "\n; 2. 配置用以检测当前角色的hash值 (请根据需要修改)",
            "[TextureOverrideCheckHash]", "hash = ", "$active = 1",
        ])

        constants_lines.extend([
            "; --- UI 几何与位置配置 ---",
            "; 父级 (背景) 配置",
            "global $base_width0 = 0.3",
            f"global $base_height0 = {parent_height:.4f}",
            "global $set_x0 = 0.5", "global $set_y0 = 0.5",
        ])

        for i in range(1, num_sliders + 1):
            current_y_offset = top_bottom_padding + (i - 1) * (child_height + spacing) + (child_height / 2)
            relative_y = current_y_offset / parent_height
            constants_lines.extend([
                f"\n; 子级 {i} ({sorted_freq_params[i-1]}) 配置",
                f"global $base_width{i} = 0.02", f"global $base_height{i} = 0.03",
                f"global $set_rel_x{i} = 0.5", f"global $fixed_rel_y{i} = {relative_y:.4f}",
            ])

        constants_lines.extend([
            "\n; --- 状态与控制变量 ---",
            "global $active", "global $help", "global $max_zoom = 5.0", "global $min_zoom = 0.1",
            "global $mouse_clicked = 0", "global $click_outside = 0", "global $is_dragging = 0",
            "global $drag_x = 0", "global $drag_y = 0",
            "\n; --- 父级持久化状态变量 ---",
            "global persist $img0_x = 0", "global persist $img0_y = 0", "global persist $zoom0 = 1.0",
            "global $norm_width0", "global $norm_height0",
        ])

        for i in range(1, num_sliders + 1):
            constants_lines.extend([
                f"\n; --- 子级 {i} 状态与几何变量 ---",
                f"global persist $rel_x{i} = 0", f"global persist $zoom{i} = 1.0",
                f"global $norm_width{i}", f"global $norm_height{i}", f"global $img{i}_x", f"global $img{i}_y",
                f"global $rel_y{i}", f"global $param{i}",
                f"global $left_bar{i}_x", f"global $left_bar{i}_y", f"global $left_bar{i}_width", f"global $left_bar{i}_height",
                f"global $right_bar{i}_x", f"global $right_bar{i}_y", f"global $right_bar{i}_width", f"global $right_bar{i}_height",
                f"global $min_rel_x{i}", f"global $max_rel_x{i}", f"global $range_x{i}", f"global $slider{i}_center_x",
            ])

        reset_lines = ["$img0_x = 0", "$img0_y = 0", "$zoom0 = 1.0"]
        for i in range(1, num_sliders + 1):
            reset_lines.extend([f"$rel_x{i} = 0", f"$zoom{i} = 1.0"])

        zoom_in_lines = ["$zoom0 = $zoom0 + 0.05"] + [f"$zoom{i} = $zoom{i} + 0.05" for i in range(1, num_sliders + 1)]
        zoom_out_lines = ["$zoom0 = $zoom0 - 0.05"] + [f"$zoom{i} = $zoom{i} - 0.05" for i in range(1, num_sliders + 1)]

        content.extend([
            "\n; 功能区 ---------------------------------------------------------",
            "\n; --- 统一快捷键配置 ---",
            "[KeyHelp]", "condition = $active == 1", "key = home", "type = cycle", "$help = 0,1",
            "\n[KeyResetPosition]", "condition = $help == 1 && $active == 1", "key = ctrl home", "type = cycle", *reset_lines,
            "\n[KeyZoomIn]", "condition = $help == 1 && $active == 1", "key = up", "type = press", "run = CommandListZoomIn",
            "\n[KeyZoomOut]", "condition = $help == 1 && $active == 1", "key = down", "type = press", "run = CommandListZoomOut",
            "\n; 鼠标拖拽检测", "[KeyMouseDrag]", "condition = $help == 1 && $active == 1", "key = VK_LBUTTON", "type = hold", "$mouse_clicked = 1",
            "\n; --- 指令集 ---", "[CommandListZoomIn]", *zoom_in_lines, "\n[CommandListZoomOut]", *zoom_out_lines,
        ])

        present_logic.extend(["post $active = 0", "if $help == 1 && $active == 1"])
        present_logic.extend(["    ; --- 1. 尺寸计算 ---", "    $norm_width0 = $base_width0 * $zoom0", "    $norm_height0 = $base_height0 * $zoom0"])

        for i in range(1, num_sliders + 1):
            present_logic.extend([f"    $norm_width{i} = $base_width{i} * $zoom{i}", f"    $norm_height{i} = $base_height{i} * $zoom{i}"])

        present_logic.append("\n    ; --- 2. 计算子级的拖拽边界 ---")

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"    $min_rel_x{i} = $norm_width0 * 0.05",
                f"    $max_rel_x{i} = ($norm_width0 * 0.95) - $norm_width{i}",
                f"    $range_x{i} = $max_rel_x{i} - $min_rel_x{i}"
            ])

        present_logic.extend([
            "\n    ; --- 3. 位置初始化 ---",
            "    if $img0_x == 0 && $img0_y == 0",
            "        $img0_x = $set_x0 * (1 - $norm_width0)",
            "        $img0_y = $set_y0 * (1 - $norm_height0)",
            "    endif"
        ])

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"    if $rel_x{i} == 0",
                f"        $rel_x{i} = $min_rel_x{i} + ($set_rel_x{i} * $range_x{i})",
                "    endif"
            ])

        present_logic.extend([
            "\n    ; --- 4. 拖拽逻辑与位置更新 ---",
            "    if $mouse_clicked",
            "        if $is_dragging == 0"
        ])

        for i in range(num_sliders, 0, -1):
            prefix = "if" if i == num_sliders else "            else if"
            present_logic.extend([
                f"            {prefix} cursor_x > $img{i}_x && cursor_x < $img{i}_x + $norm_width{i} && cursor_y > $img{i}_y && cursor_y < $img{i}_y + $norm_height{i}",
                f"                $is_dragging = {i + 1}",
                f"                $drag_x = cursor_x - $img{i}_x"
            ])

        present_logic.extend([
            "            else if cursor_x > $img0_x && cursor_x < $img0_x + $norm_width0 && cursor_y > $img0_y && cursor_y < $img0_y + $norm_height0",
            "                $is_dragging = 1",
            "                $drag_x = cursor_x - $img0_x",
            "                $drag_y = cursor_y - $img0_y",
            "            else",
            "                $click_outside = 1",
            "            endif",
            "        endif",
            "    else",
            "        $is_dragging = 0",
            "    endif",
            "    if $click_outside == 1 && $mouse_clicked == 0",
            "        $help = 0",
            "        $click_outside = 0",
            "    endif",
            "    if $is_dragging == 1",
            "        $img0_x = cursor_x - $drag_x",
            "        $img0_y = cursor_y - $drag_y"
        ])

        for i in range(2, num_sliders + 2):
            present_logic.extend([
                f"    else if $is_dragging == {i}",
                f"        $rel_x{i-1} = (cursor_x - $drag_x) - $img0_x",
                f"        if $rel_x{i-1} < $min_rel_x{i-1}",
                f"            $rel_x{i-1} = $min_rel_x{i-1}",
                f"        endif",
                f"        if $rel_x{i-1} > $max_rel_x{i-1}",
                f"            $rel_x{i-1} = $max_rel_x{i-1}",
                f"        endif"
            ])

        present_logic.append("    endif")
        present_logic.append("\n    ; --- 5. 计算最终绝对位置 (滑块) ---")

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"    $rel_y{i} = ($fixed_rel_y{i} * $norm_height0) - ($norm_height{i} / 2)",
                f"    $img{i}_x = $img0_x + $rel_x{i}",
                f"    $img{i}_y = $img0_y + $rel_y{i}"
            ])

        present_logic.append("\n    ; --- 6. 计算进度条的几何信息 ---")

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"    $slider{i}_center_x = $img{i}_x + ($norm_width{i} * 0.5)",
                f"    $left_bar{i}_height = $norm_height{i} * 0.5",
                f"    $left_bar{i}_y = $img{i}_y + ($norm_height{i} * 0.25)",
                f"    $left_bar{i}_x = $img0_x + $min_rel_x{i}",
                f"    $left_bar{i}_width = $slider{i}_center_x - $left_bar{i}_x",
                f"    $right_bar{i}_height = $left_bar{i}_height",
                f"    $right_bar{i}_y = $left_bar{i}_y",
                f"    $right_bar{i}_x = $slider{i}_center_x",
                f"    $right_bar{i}_width = ($img0_x + $norm_width0 * 0.95) - $right_bar{i}_x"
            ])

        present_logic.append("\n    ; --- 7. 计算映射参数并链接到形态键强度 ---")

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"    $param{i} = ($rel_x{i} - $min_rel_x{i}) / $range_x{i}",
                f"    {sorted_freq_params[i-1]} = $param{i}"
            ])

        present_logic.extend([
            "\n    ; --- 8. 执行渲染 (按层级) ---",
            "    ; 渲染父级 (最底层)",
            "    ps-t100 = ResourceImageToRender0",
            "    x87 = $norm_width0",
            "    y87 = $norm_height0",
            "    z87 = $img0_x",
            "    w87 = $img0_y",
            "    run = CustomShaderDraw"
        ])

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"\n    ; 渲染进度条{i}",
                f"    ps-t100 = ResourceLeftBar",
                f"    x87 = $left_bar{i}_width",
                f"    y87 = $left_bar{i}_height",
                f"    z87 = $left_bar{i}_x",
                f"    w87 = $left_bar{i}_y",
                f"    run = CustomShaderDraw",
                f"    ps-t100 = ResourceRightBar",
                f"    x87 = $right_bar{i}_width",
                f"    y87 = $right_bar{i}_height",
                f"    z87 = $right_bar{i}_x",
                f"    w87 = $right_bar{i}_y",
                f"    run = CustomShaderDraw"
            ])

        for i in range(1, num_sliders + 1):
            present_logic.extend([
                f"\n    ; 渲染滑块{i} (最顶层)",
                f"    ps-t100 = ResourceSliderHandle",
                f"    x87 = $norm_width{i}",
                f"    y87 = $norm_height{i}",
                f"    z87 = $img{i}_x",
                f"    w87 = $img{i}_y",
                f"    run = CustomShaderDraw"
            ])

        present_logic.append("endif")

        shader_def = [
            "\n; 渲染着色器 ---------------------------------------------------------",
            "[CustomShaderDraw]",
            "hs = null",
            "ds = null",
            "gs = null",
            "cs = null",
            "vs = ./res/draw_2d.hlsl",
            "ps = ./res/draw_2d.hlsl",
            "blend = ADD SRC_ALPHA INV_SRC_ALPHA",
            "cull = none",
            "topology = triangle_strip",
            "o0 = set_viewport bb",
            "Draw = 4,0",
            "clear = ps-t100"
        ]

        content.append("\n\n[Constants]")
        content.extend(constants_lines)
        content.append("\n\n[Present]")
        content.extend(present_logic)
        content.extend(shader_def)

        try:
            with open(target_ini_file, "a", encoding='utf-8') as f_out:
                f_out.write("\n\n")
                f_out.write("; ==============================================================================\n")
                f_out.write("; --- AUTO-APPENDED SLIDER CONTROL PANEL ---\n")
                f_out.write("; ==============================================================================\n\n")
                f_out.write("\n".join(content))

            print(f"滑块控制面板配置已追加到: {os.path.basename(target_ini_file)}")
            print(f"共生成 {num_sliders} 个滑块")
        except Exception as e:
            print(f"追加滑块控制面板配置到文件时失败: {e}")
            return

    def _read_ini_to_ordered_dict(self, ini_file_path):
        """读取INI文件并返回有序字典"""
        sections = OrderedDict()
        current_section = None
        try:
            with open(ini_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    stripped_line = line.strip()
                    if stripped_line.startswith('[') and stripped_line.endswith(']') and len(stripped_line) > 2:
                        current_section = stripped_line
                        sections[current_section] = []
                    elif current_section is not None:
                        sections[current_section].append(line.rstrip())
        except FileNotFoundError:
            return None
        return sections


classes = (
    SSMTNode_PostProcess_SliderPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
