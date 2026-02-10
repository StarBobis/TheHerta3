import bpy
import os
import glob
import re

from .blueprint_node_postprocess_base import SSMTNode_PostProcess_Base


class SSMTNode_PostProcess_HealthDetection(SSMTNode_PostProcess_Base):
    '''血量检测后处理节点：在配置表最下方追加血量检测模块，支持自定义角色哈希和血量映射级数'''
    bl_idname = 'SSMTNode_PostProcess_HealthDetection'
    bl_label = '血量检测（仅限ZZZ）'
    bl_description = '在配置表最下方追加血量检测模块，支持自定义角色哈希和血量映射级数 (适配ZZZ)'

    health_character_hash: bpy.props.StringProperty(
        name="角色哈希",
        description="目标角色的Body Blend Hash",
        default="2d519056",
        maxlen=256,
        update=lambda self, context: self.update_node_width([self.health_character_hash, self.health_combat_ui_hash, self.health_bar_hash, self.health_param_name])
    )
    health_combat_ui_hash: bpy.props.StringProperty(
        name="战斗UI哈希",
        description="战斗UI的Hash值",
        default="0086a8159f4d9a00",
        maxlen=256,
        update=lambda self, context: self.update_node_width([self.health_character_hash, self.health_combat_ui_hash, self.health_bar_hash, self.health_param_name])
    )
    health_bar_hash: bpy.props.StringProperty(
        name="血条绘制哈希",
        description="血条绘制Shader的Hash值",
        default="dce9c76d7f184caf",
        maxlen=256,
        update=lambda self, context: self.update_node_width([self.health_character_hash, self.health_combat_ui_hash, self.health_bar_hash, self.health_param_name])
    )
    health_param_name: bpy.props.StringProperty(
        name="参数名称",
        description="血量映射的参数名称",
        default="$HealthLevel",
        maxlen=256,
        update=lambda self, context: self.update_node_width([self.health_character_hash, self.health_combat_ui_hash, self.health_bar_hash, self.health_param_name])
    )
    health_levels: bpy.props.IntProperty(
        name="级数",
        description="血量映射的级数",
        default=10,
        min=2,
        max=100
    )

    def draw_buttons(self, context, layout):
        layout.prop(self, "health_character_hash")
        layout.prop(self, "health_combat_ui_hash")
        layout.prop(self, "health_bar_hash")
        layout.prop(self, "health_param_name")
        layout.prop(self, "health_levels")

    def execute_postprocess(self, mod_export_path):
        print(f"血量检测后处理节点开始执行，Mod导出路径: {mod_export_path}")

        if not self.health_character_hash:
            print("错误: 未设置角色哈希值")
            return

        ini_files = glob.glob(os.path.join(mod_export_path, "*.ini"))
        if not ini_files:
            print("路径中未找到任何.ini文件")
            return

        target_ini_file = ini_files[0]

        try:
            with open(target_ini_file, 'r', encoding='utf-8') as f:
                if "; --- AUTO-APPENDED HEALTH DETECTION MODULE ---" in f.read():
                    print("血量检测模块配置已存在于文件中。请手动删除后再生成。")
                    return
        except Exception as e:
            print(f"读取目标INI文件以进行检查时出错: {e}")
            return

        self._create_cumulative_backup(target_ini_file, mod_export_path)

        try:
            module_content = self._get_module_template()
            
            module_content = module_content.replace("hash = 2d519056", f"hash = {self.health_character_hash}")
            module_content = module_content.replace("hash = 0086a8159f4d9a00", f"hash = {self.health_combat_ui_hash}")
            module_content = module_content.replace("hash = dce9c76d7f184caf", f"hash = {self.health_bar_hash}")
            
            health_mapping_section = self._generate_health_mapping()
            
            module_content = module_content.replace("; 每一帧重置状态，等待下一帧重新检测", 
                                                       f"; 每一帧重置状态，等待下一帧重新检测\n\n{health_mapping_section}")
            
            with open(target_ini_file, "a", encoding='utf-8') as f_out:
                f_out.write("\n\n")
                f_out.write("; ==============================================================================")
                f_out.write("\n; --- AUTO-APPENDED HEALTH DETECTION MODULE ---")
                f_out.write("\n; ==============================================================================\n\n")
                f_out.write(module_content)

            print(f"血量检测模块配置已追加到: {os.path.basename(target_ini_file)}")
            print(f"角色哈希: {self.health_character_hash}")
            print(f"血量级数: {self.health_levels}")
        except Exception as e:
            print(f"追加血量检测模块配置到文件时失败: {e}")
            import traceback
            traceback.print_exc()
            return

    def _get_module_template(self):
        return """\
[Constants]
; 血量更新频率 (秒)
global $HEALTH_UPDATE_INTERVAL = 0.05
; 下场后血量重置延迟 (秒)
global $HEALTH_RESET_DELAY = 30.0
global $Health = 1.0

; 内部逻辑变量
global $IsTargetOnScreen = 0
global $IsCombat = 0
global $NextUpdateTime = 0
global $TimeSinceLastOnField = 0
global $TempHealth = 1.0

; 临时存储Buffer
[ResourceHealthBuffer]

[TextureOverride_TargetCharacter_Check]
hash = 2d519056
match_priority = -999
$IsTargetOnScreen = 1

[ShaderOverride_CombatCheck]
hash = 0086a8159f4d9a00
allow_duplicate_hash = true
$IsCombat = 1

[TextureOverride_HealthBarTex_Filter]
hash = 783c26a0
match_index_count = 54
match_priority = 999
filter_index = 2

[TextureOverride_HealthBarTex_Fuzzy]
match_type = Texture2D
match_format = DXGI_FORMAT_BC3_UNORM_SRGB
match_width = 1024
match_height = 1024
match_mips = 1
match_index_count = 54
match_priority = 999
filter_index = 2

; 兼容 UI Recolor Mod
[TextureOverride_HealthBarTex_Fuzzy_Compat]
match_type = Texture2D
match_format = DXGI_FORMAT_BC3_UNORM_SRGB
match_width = 1024
match_height = 1024
match_mips = 11
match_index_count = 54
match_priority = 999
filter_index = 2

[ShaderOverride_ReadHealthBar]
hash = dce9c76d7f184caf
allow_duplicate_hash = true
if $IsCombat && time > $NextUpdateTime && ps-t0 == 2 && $IsTargetOnScreen
    ResourceHealthBuffer = copy ps-cb0
    $NextUpdateTime = time + $HEALTH_UPDATE_INTERVAL
endif

[Present]
if $IsTargetOnScreen && $IsCombat
    store = $TempHealth, ref ResourceHealthBuffer, 45
    
    $Health = $TempHealth
    
    $TimeSinceLastOnField = time + $HEALTH_RESET_DELAY
else
    if time > $TimeSinceLastOnField && $TimeSinceLastOnField > 0
        $Health = 1.0
        $TimeSinceLastOnField = 0
    endif
endif

post $IsTargetOnScreen = 0
post $IsCombat = 0
; 每一帧重置状态，等待下一帧重新检测
"""

    def _generate_health_mapping(self):
        param_name = self.health_param_name
        levels = self.health_levels
        
        lines = [
            "; ==============================================================================",
            "; 血量映射逻辑 (自动生成)",
            "; ==============================================================================",
            "",
            f"; 将血量 (0.0-1.0) 映射到 {param_name} (0-{levels-1})",
            f"; 每级代表血量变化 {1.0/levels:.4f}",
            "",
            "[Present]"
        ]
        
        for i in range(levels):
            lower_bound = i / levels
            upper_bound = (i + 1) / levels
            
            if i == 0:
                condition = f"if $Health >= {lower_bound:.4f} && $Health < {upper_bound:.4f}"
            elif i == levels - 1:
                condition = f"else if $Health >= {lower_bound:.4f}"
            else:
                condition = f"else if $Health >= {lower_bound:.4f} && $Health < {upper_bound:.4f}"
            
            lines.append(f"    {condition}")
            lines.append(f"        {param_name} = {i}")
        
        lines.append("    endif")
        
        return "\n".join(lines)


classes = (
    SSMTNode_PostProcess_HealthDetection,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
