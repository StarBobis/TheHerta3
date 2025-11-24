
import os
import shutil

from ..common.m_ini_builder import *
from ..config.main_config import GlobalConfig
from ..config.properties_generate_mod import Properties_GenerateMod
from ..common.migoto_format import M_Key
from ..base.obj_data_model import ObjDataModel

class M_IniHelperGUI:
    @classmethod
    def copy_files(cls,src_dir, dst_dir):
        """
        复制 src_dir 目录下的所有文件（不包括子目录）到 dst_dir 目录
        :param src_dir: 源目录路径
        :param dst_dir: 目标目录路径
        """
        # 确保目标目录存在
        os.makedirs(dst_dir, exist_ok=True)

        # 遍历源目录下的所有文件
        for filename in os.listdir(src_dir):
            src_file = os.path.join(src_dir, filename)
            dst_file = os.path.join(dst_dir, filename)

            # 只复制文件，忽略子目录
            if os.path.isfile(src_file):
                if not os.path.exists(dst_file):
                    shutil.copy2(src_file, dst_file)  # 使用 copy2 保留元数据
                print(f"复制文件: {src_file} -> {dst_file}")
                
    @classmethod
    def add_branch_mod_gui_section(cls,ini_builder:M_IniBuilder,key_name_mkey_dict:dict[str,M_Key]):
        '''
        声明模板化GUI面板

        此功能灵感来源于：https://www.caimogu.cc/post/2069456.html
        特别感谢：タ小言
        ; UI Block
        ; By: Comilarex
        ; Modifier: 夕小言

        特别感谢：SinsOfSeven
        '''

        if not Properties_GenerateMod.generate_branch_mod_gui():
            return
        else:
            # 在这里把所有的res下面的东西，复制到当前生成的Mod文件夹的res目录下
            res_path = os.path.join(GlobalConfig.path_generate_mod_folder(),"res\\")
            if not os.path.exists(res_path):
                os.makedirs(res_path)

            script_path = os.path.abspath(__file__)

            # 获取当前插件的工作目录
            plugin_directory = os.path.dirname(script_path)

            # 构建保存文件的路径
            res_source_path = os.path.join(plugin_directory, 'res\\')

            cls.copy_files(res_source_path,res_path)

        if len(key_name_mkey_dict.keys()) == 0:
            return
        
        
        constants_section = M_IniSection(M_SectionType.Constants)
        constants_section.SectionName = "Constants"

        constants_section.append("global $window_width = 1920")
        constants_section.append("global $window_height = 1080")
        constants_section.new_line()

        constants_section.append("global $menu = 0")
        constants_section.append("global $gap = 0.0025")
        constants_section.append("global $mouse_clicked = 0")
        constants_section.append("global $x_size = 0")
        constants_section.append("global $y_size = 0")
        constants_section.new_line()
        
        constants_section.append("global $x_size_Button = 0.03")
        constants_section.append("global $y_size_Button = 0.03")
        constants_section.append("global $y_offset_button = 0.029")
        constants_section.append("global $last_mx = 0")
        constants_section.append("global $last_my = 0")
        constants_section.append("global $mx = 0")
        constants_section.append("global $my = 0")
        constants_section.append("global $x_off_off = 0")
        constants_section.append("global $y_off_off = 0")
        constants_section.append("global $mouse_hold = 0")
        constants_section.append("global persist $final_x_off = -1")
        constants_section.append("global persist $final_y_off = 0.05845")
        constants_section.append("global $is_dragging = 0")
        constants_section.append("global $drag_start_x = 0")
        constants_section.append("global $drag_start_y = 0")
        constants_section.append("global $new_x_off = 0")
        constants_section.append("global $new_y_off = 0")
        constants_section.append("global $total_y_size = 0")
        constants_section.append("global $y_Title_size = 0.045")
        constants_section.append("global $x_Title_size = 0.12")
        constants_section.append("global $y_Credit_size = 0.03")
        constants_section.append("global $x_Credit_size = 0.12")
        constants_section.append("global $press_effect = 0.002")
        constants_section.append("global $ButtonLayerGeneration = 0")
        constants_section.append("global $UI_Thickness = 0.002")
        constants_section.append("global $x_random = -0.01701")
        constants_section.append("global $res_width = 0")
        constants_section.append("global $res_height = 0")
        constants_section.append("global $ActiveCharacter = 0")
        constants_section.new_line()

        constants_section.append(";设置按钮总数")
        constants_section.append("global $Button_amount = " + str(len(key_name_mkey_dict.values())))
        constants_section.append(";设置横向最大按钮数")
        constants_section.append("global $Button_horizontal_max = 10")
        constants_section.new_line()

        constants_section.append("global $Button_number = 0")
        constants_section.append("global $Button_now = 0")
        constants_section.append("global $Button_x = 0")
        constants_section.append("global $Button_y = 0")
        
        ini_builder.append_section(constants_section)


        key_section = M_IniSection(M_SectionType.Key)

        key_section.append("[KeyToggleUI]")
        key_section.append("condition = $ActiveCharacter")
        key_section.append("key = CTRL ALT")
        key_section.append("type = hold")
        key_section.append("$menu = 1")
        key_section.new_line()

        key_section.append("[KeyMouse]")
        key_section.append("condition = $menu")
        key_section.append("key = VK_LBUTTON")
        key_section.append("type = hold")
        key_section.append("$mouse_clicked = 1")
        key_section.append("$mouse_hold = 1")
        key_section.new_line()

        ini_builder.append_section(key_section)


        present_section = M_IniSection(M_SectionType.Present)
        present_section.SectionName = "Present"
        present_section.append("post $ActiveCharacter = 0")
        present_section.append("if $menu")
        present_section.append("    run = CommandListPassWindowInfo")
        present_section.new_line()

        present_section.append("    if $Button_amount > $Button_horizontal_max")
        present_section.append("        $x_size = (($x_size_Button + $gap) * $Button_horizontal_max) + $gap * 3")
        present_section.append("    else")
        present_section.append("        $x_size = (($x_size_Button + $gap) * $Button_amount) + $gap * 3")
        present_section.append("    endif")
        present_section.append("    $y_size = (($y_size_Button + $gap) * ((($Button_amount - 1) // $Button_horizontal_max) + 1) + $gap * 3 + ($y_size_Button * 0.66) * 2) * res_width / res_height")
        present_section.new_line()

        present_section.append("    if $x_Title_size > $x_size")
        present_section.append("        $x_size = $x_Title_size")
        present_section.append("    endif")
        present_section.append("    if $final_x_off == -1")
        present_section.append("        $final_x_off = 0.5 - $x_size/2 + -0.01701")
        present_section.append("    endif")
        present_section.new_line()

        present_section.append("    run = CommandListDrawUIElement")
        present_section.append("    run = CommandListDrawUITitle")
        present_section.append("    run = CommandListDrawUICredit")
        present_section.append("    run = CommandListDrawUIBorderXUpper")
        present_section.append("    run = CommandListDrawUIBorderXLower")
        present_section.append("    run = CommandListDrawUIBorderXMiddle")
        present_section.append("    run = CommandListDrawUIBorderXMiddle2")
        present_section.append("    run = CommandListDrawUIBorderYLeft")
        present_section.append("    run = CommandListDrawUIBorderYRight")
        present_section.new_line()

        present_section.append("    ;添加按钮")
        for mkey in key_name_mkey_dict.values():
            present_section.append("    run = CommandListAddButton")
        present_section.new_line()

        present_section.append("    $Button_number = 0")
        present_section.new_line()

        present_section.append("    run = CommandListCheckMouse")
        present_section.append("endif")

        ini_builder.append_section(present_section)

        commandlist_section = M_IniSection(M_SectionType.CommandList)
        commandlist_section.append(";MARK:ButtonSetting")
        commandlist_section.append("[CommandListSetButtonCondition]")
        commandlist_section.append(";设置按钮功能")

        button_number = 0
        for mkey in key_name_mkey_dict.values():
            if button_number == 0:
                commandlist_section.append("if $Button_number == " + str(button_number + 1))
            else:
                commandlist_section.append("else if $Button_number == " + str(button_number + 1))
            key_tmp_name = "$swapkey" + str(button_number)
            commandlist_section.append("    if " + key_tmp_name + " < " + str(len(mkey.value_list) - 1))
            commandlist_section.append("        " + key_tmp_name + " = " + key_tmp_name + " + 1" )
            commandlist_section.append("    else")
            commandlist_section.append("        " + key_tmp_name + " = 0")
            commandlist_section.append("    endif")

            button_number = button_number + 1
        commandlist_section.append("endif")
        commandlist_section.new_line()


        commandlist_section.append("[CommandListSetButtonIcon]")
        commandlist_section.append(";设置按钮图标")
        button_number = 0
        for mkey in key_name_mkey_dict.values():
            if button_number == 0:
                commandlist_section.append("if $Button_number == " + str(button_number + 1))
            else:
                commandlist_section.append("else if $Button_number == " + str(button_number + 1))
            commandlist_section.append("    ps-t100 = ResourceButton_item_default_" + str(button_number + 1))
            button_number = button_number + 1

        commandlist_section.append("else")
        commandlist_section.append("    ps-t100 = ResourceButton_item_default")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListPassWindowInfo]")
        commandlist_section.append("if window_width >= 640")
        commandlist_section.append("    $res_width = window_width")
        commandlist_section.append("    $res_height = window_height")
        commandlist_section.append("else if rt_width >= 640")
        commandlist_section.append("    $res_width = rt_width")
        commandlist_section.append("    $res_height = rt_height")
        commandlist_section.append("else if res_width >= 640")
        commandlist_section.append("    $res_width = res_width")
        commandlist_section.append("    $res_height = res_height")
        commandlist_section.append("else")
        commandlist_section.append("    $res_width = $window_width")
        commandlist_section.append("    $res_height = $window_height")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListAddButton]")
        commandlist_section.append("$Button_number = $Button_number + 1")
        commandlist_section.append("if $Button_number <= $Button_amount")
        commandlist_section.append("    run = CommandListButtonBlock")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListButtonBlock]")
        commandlist_section.append("$Button_x = $final_x_off + (($x_size_Button + $gap) * (($Button_number - 1) % $Button_horizontal_max ) + $gap * 2)")
        commandlist_section.append("$Button_y = $final_y_off + ((($y_size_Button + $gap)  * (($Button_number - 1) // $Button_horizontal_max) + $y_offset_button ) * res_width / res_height)")
        commandlist_section.append("run = CommandListDrawButton")
        commandlist_section.append("$ButtonLayerGeneration = !$ButtonLayerGeneration")
        commandlist_section.append("run = CommandListDrawButton")
        commandlist_section.append("; Calling this now to get Button effect over button")
        commandlist_section.append("if cursor_y > $Button_y && cursor_y < $Button_y + ($y_size_Button * res_width / res_height)")
        commandlist_section.append("    ; BUTTON")
        commandlist_section.append("    if $Button_amount >= $Button_number")
        commandlist_section.append("        if cursor_x > $Button_x && cursor_x < $Button_x + $x_size_Button")
        commandlist_section.append("            if $mouse_clicked")
        commandlist_section.append("                $Button_now = $Button_number")
        commandlist_section.append("                run = CommandListSetButtonCondition")
        commandlist_section.append("            endif")
        commandlist_section.append("            run = CommandListDrawButtonEffect")
        commandlist_section.append("        endif")
        commandlist_section.append("    endif")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListCheckMouse]")
        commandlist_section.append("$mouse_clicked = 0")
        commandlist_section.append("if $is_dragging == 1")
        commandlist_section.append("    if $mouse_hold")
        commandlist_section.append("        run = CommandListMoveUIElement")
        commandlist_section.append("    else")
        commandlist_section.append("        $is_dragging = 0")
        commandlist_section.append("    endif")
        commandlist_section.append("else if cursor_x > $final_x_off && cursor_x < $final_x_off + $x_size")
        commandlist_section.append("    if cursor_y > $final_y_off && cursor_y < $final_y_off + $y_size")
        commandlist_section.append("        if $mouse_hold")
        commandlist_section.append("            run = CommandListStartDrag")
        commandlist_section.append("            run = CommandListMoveUIElement")
        commandlist_section.append("        else")
        commandlist_section.append("            $is_dragging = 0")
        commandlist_section.append("        endif")
        commandlist_section.append("    endif")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawButtonEffect]")
        commandlist_section.append("x87 = $x_size_Button")
        commandlist_section.append("y87 = $y_size_Button * res_width / res_height")
        commandlist_section.append("z87 = $Button_x")
        commandlist_section.append("w87 = $Button_y")
        commandlist_section.append("if $is_dragging && $Button_now == $Button_number")
        commandlist_section.append("    w87 = $Button_y + $press_effect")
        commandlist_section.append("endif")
        commandlist_section.append("if $is_dragging == 0")
        commandlist_section.append("    ps-t100 = ResourceUIButtonSelect")
        commandlist_section.append("else")
        commandlist_section.append("    ps-t100 = ResourceButtonPush")
        commandlist_section.append("endif")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawButton]")
        commandlist_section.append("x87 = $x_size_Button")
        commandlist_section.append("y87 = $y_size_Button * res_width / res_height")
        commandlist_section.append("z87 = $Button_x")
        commandlist_section.append("w87 = $Button_y")
        commandlist_section.append("if $is_dragging && $Button_now == $Button_number")
        commandlist_section.append("    w87 = $Button_y + $press_effect")
        commandlist_section.append("endif")
        commandlist_section.append("if $ButtonLayerGeneration")
        commandlist_section.append("    ps-t100 = ResourceOutlineButton")
        commandlist_section.append("else")
        commandlist_section.append("    run = CommandListSetButtonIcon")
        commandlist_section.append("endif")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIElement]")
        commandlist_section.append("x87 = $x_size")
        commandlist_section.append("y87 = $y_size")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off")
        commandlist_section.append("ps-t100 = ResourceUIBackground")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUITitle]")
        commandlist_section.append("x87 = $x_Title_size")
        commandlist_section.append("y87 = $y_Title_size")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off")
        commandlist_section.append("ps-t100 = ResourceUITitle")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUICredit]")
        commandlist_section.append("x87 = $x_Credit_size")
        commandlist_section.append("y87 = $y_Credit_size")
        commandlist_section.append("z87 = $final_x_off + $x_size - $x_Credit_size")
        commandlist_section.append("w87 = $final_y_off + ($y_size - $y_Credit_size)")
        commandlist_section.append("ps-t100 = ResourceUICredit")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderXUpper]")
        commandlist_section.append("x87 = $x_size")
        commandlist_section.append("y87 = $UI_Thickness * res_width / res_height")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderXLower]")
        commandlist_section.append("x87 = $x_size")
        commandlist_section.append("y87 = $UI_Thickness * res_width / res_height")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off + $y_size - $UI_Thickness")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderXMiddle]")
        commandlist_section.append("x87 = $x_size")
        commandlist_section.append("y87 = $UI_Thickness * res_width / res_height")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off + $y_Title_size - $UI_Thickness")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderXMiddle2]")
        commandlist_section.append("x87 = $x_size")
        commandlist_section.append("y87 = $UI_Thickness * res_width / res_height")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off + $y_size - $y_Credit_size - $UI_Thickness")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderYLeft]")
        commandlist_section.append("x87 = $UI_Thickness")
        commandlist_section.append("y87 = $y_size")
        commandlist_section.append("z87 = $final_x_off")
        commandlist_section.append("w87 = $final_y_off")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListDrawUIBorderYRight]")
        commandlist_section.append("x87 = $UI_Thickness")
        commandlist_section.append("y87 = $y_size")
        commandlist_section.append("z87 = $final_x_off + $x_size - $UI_Thickness")
        commandlist_section.append("w87 = $final_y_off")
        commandlist_section.append("ps-t100 = ResourceUIColorBorder")
        commandlist_section.append("run = CustomShaderElement")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListStartDrag]")
        commandlist_section.append("if $is_dragging == 0")
        commandlist_section.append("    $drag_start_x = cursor_x - $final_x_off")
        commandlist_section.append("    $drag_start_y = cursor_y - $final_y_off")
        commandlist_section.append("    $is_dragging = 1")
        commandlist_section.append("endif")
        commandlist_section.new_line()

        commandlist_section.append("[CommandListMoveUIElement]")
        commandlist_section.append("if $is_dragging == 1")
        commandlist_section.append("    if $mouse_hold")
        commandlist_section.append("        $new_x_off = cursor_x - $drag_start_x")
        commandlist_section.append("        $new_y_off = cursor_y - $drag_start_y")
        commandlist_section.append("        if $new_x_off < 0")
        commandlist_section.append("            $final_x_off = 0")
        commandlist_section.append("        else if $new_x_off + $x_size > 1")
        commandlist_section.append("            $final_x_off = 1 - $x_size")
        commandlist_section.append("        else")
        commandlist_section.append("            $final_x_off = $new_x_off")
        commandlist_section.append("        endif")
        commandlist_section.append("        if $new_y_off < 0")
        commandlist_section.append("            $final_y_off = 0")
        commandlist_section.append("        else if $new_y_off + $y_size > 1")
        commandlist_section.append("            $final_y_off = 1 - $y_size")
        commandlist_section.append("        else")
        commandlist_section.append("            $final_y_off = $new_y_off")
        commandlist_section.append("        endif")
        commandlist_section.append("    else")
        commandlist_section.append("        $is_dragging = 0")
        commandlist_section.append("    endif")
        commandlist_section.append("endif")
        commandlist_section.new_line()


        commandlist_section.append("[CustomShaderElement]")
        commandlist_section.append("hs = null")
        commandlist_section.append("ds = null")
        commandlist_section.append("gs = null")
        commandlist_section.append("cs = null")
        commandlist_section.append("run = BuiltInCommandListUnbindAllRenderTargets")
        commandlist_section.append("vs = .\\res\\draw_2d.hlsl")
        commandlist_section.append("ps = .\\res\\draw_2d.hlsl")
        commandlist_section.append("blend = ADD SRC_ALPHA INV_SRC_ALPHA")
        commandlist_section.append("cull = none")
        commandlist_section.append("topology = triangle_strip")
        commandlist_section.append("o0 = set_viewport bb")
        commandlist_section.append("Draw = 4,0")
        commandlist_section.new_line()

        ini_builder.append_section(commandlist_section)

        resource_section = M_IniSection(M_SectionType.ResourceTexture)

        resource_section.append("[ResourceUIColorBorder]")
        resource_section.append("filename = .\\res\\Border.png")
        resource_section.new_line()
        
        resource_section.append("[ResourceUIBackground]")
        resource_section.append("filename = .\\res\\Background.png")
        resource_section.new_line()

        resource_section.append("[ResourceUIButtonSelect]")
        resource_section.append("filename = .\\res\\Selected.png")
        resource_section.new_line()
        
        resource_section.append("[ResourceOutlineButton]")
        resource_section.append("filename = .\\res\\Button.png")
        resource_section.new_line()

        resource_section.append("[ResourceButtonPush]")
        resource_section.append("filename = .\\res\\Push.png")
        resource_section.new_line()

        resource_section.append("[ResourceUITitle]")
        resource_section.append("filename = .\\res\\Title.png")
        resource_section.new_line()

        resource_section.append("[ResourceUICredit]")
        resource_section.append("filename = .\\res\\Credits.png")
        resource_section.new_line()

        resource_section.append("[ResourceButton_item_default]")
        resource_section.append("filename = .\\res\\item_shirt.png")
        resource_section.new_line()

        # 测试的自定义资源
        button_number = 0
        for mkey in key_name_mkey_dict.values():
            resource_section.append("[ResourceButton_item_default_"+ str(button_number + 1)+ "]")
            resource_section.append("filename = .\\res\\item_shirt.png")
            resource_section.new_line()
            button_number = button_number + 1

        ini_builder.append_section(resource_section)

        # for mkey in key_name_mkey_dict.values():
        #     key_str = "global persist " + mkey.key_name + " = " + str(mkey.initialize_value)
        #     constants_section.append(key_str) 
