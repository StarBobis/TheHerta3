import bpy
import math
import os
import shutil

from ..config.main_config import GlobalConfig,LogicName
from ..common.draw_ib_model import DrawIBModel

from ..base.m_global_key_counter import M_GlobalKeyCounter
from ..blueprint.blueprint_model import BluePrintModel
from ..blueprint.blueprint_export_helper import BlueprintExportHelper

from ..common.m_ini_builder import M_IniBuilder,M_IniSection,M_SectionType
from ..config.properties_generate_mod import Properties_GenerateMod
from ..common.m_ini_helper import M_IniHelper,M_IniHelper
from ..common.m_ini_helper_gui import M_IniHelperGUI

class ModModelEFMI:
    def __init__(self, skip_buffer_export:bool = False):
        # (1) 统计全局分支模型
        self.branch_model = BluePrintModel()

        # (2) 抽象每个DrawIB为DrawIBModel
        self.drawib_drawibmodel_dict:dict[str,DrawIBModel] = {}
        self.parse_draw_ib_draw_ib_model_dict(skip_buffer_export)

        # (3) 这些属性用于ini生成
        self.vlr_filter_index_indent = ""
        self.texture_hash_filter_index_dict = {}
        
        # (4) 跨IB信息
        self.cross_ib_info_dict = self.branch_model.cross_ib_info_dict
        self.cross_ib_method_dict = self.branch_model.cross_ib_method_dict
        self.has_cross_ib = len(self.cross_ib_info_dict) > 0

    def parse_draw_ib_draw_ib_model_dict(self, skip_buffer_export:bool = False):
        '''
        根据obj的命名规则，推导出DrawIB并抽象为DrawIBModel
        如果用户用不到某个DrawIB的话，就可以隐藏掉对应的obj
        隐藏掉的obj就不会被统计生成DrawIBModel，做到只导入模型，不生成Mod的效果。
        '''
        for draw_ib in self.branch_model.draw_ib__component_count_list__dict.keys():
            draw_ib_model = DrawIBModel(draw_ib=draw_ib,branch_model=self.branch_model, skip_buffer_export=skip_buffer_export)
            self.drawib_drawibmodel_dict[draw_ib] = draw_ib_model

    def add_cross_ib_present_section(self, ini_builder:M_IniBuilder):
        '''
        添加跨IB特殊追加固定区域
        '''
        if not self.has_cross_ib:
            return
        
        present_section = M_IniSection(M_SectionType.CrossIBPresent)
        present_section.append(";特殊追加固定区域")
        present_section.append("[Present]")
        present_section.append("ResourcePrev_SRV = ResourceFakeT0_SRV")
        present_section.new_line()
        
        present_section.append("[ResourceDumpedCB1_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceDumpedCB1_SRV]")
        present_section.append("type = Buffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeCB1_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeCB1]")
        present_section.append("type = Buffer")
        present_section.append("stride = 16")
        present_section.append("format = R32G32B32A32_UINT")
        present_section.append("array = 4096")
        present_section.new_line()
        
        present_section.append("[ResourceFakeT0_UAV]")
        present_section.append("type = RWStructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[ResourceFakeT0_SRV]")
        present_section.append("type = StructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[ResourcePrev_SRV]")
        present_section.append("type = StructuredBuffer")
        present_section.append("stride = 16")
        present_section.append("array = 200000")
        present_section.new_line()
        
        present_section.append("[CustomShader_ExtractCB1]")
        present_section.append("vs = ./res/extract_cb1_vs.hlsl")
        present_section.append("ps = ./res/extract_cb1_ps.hlsl")
        present_section.append("ps-u7 = ResourceDumpedCB1_UAV")
        present_section.append("depth_enable = false")
        present_section.append("blend = ADD SRC_ALPHA INV_SRC_ALPHA")
        present_section.append("cull = none")
        present_section.append("topology = point_list")
        present_section.append("draw = 4096, 0")
        present_section.append("ps-u7 = null")
        present_section.append("ResourceDumpedCB1_SRV = copy ResourceDumpedCB1_UAV")
        present_section.new_line()
        
        present_section.append("[CustomShader_RecordBones]")
        present_section.append("cs = ./res/record_bones_cs.hlsl")
        present_section.append("cs-t0 = vs-t0")
        present_section.append("cs-t1 = ResourceDumpedCB1_SRV")
        present_section.append("cs-u1 = ResourceFakeT0_UAV")
        present_section.append("dispatch = 12, 1, 1")
        present_section.append("cs-u1 = null")
        present_section.append("cs-t0 = null")
        present_section.append("cs-t1 = null")
        present_section.append("ResourceFakeT0_SRV = copy ResourceFakeT0_UAV")
        present_section.new_line()
        
        present_section.append("[CustomShader_RedirectCB1]")
        present_section.append("cs = ./res/redirect_cb1_cs.hlsl")
        present_section.append("cs-t0 = ResourceDumpedCB1_SRV")
        present_section.append("ResourceFakeCB1_UAV = copy ResourceDumpedCB1_SRV")
        present_section.append("cs-u0 = ResourceFakeCB1_UAV")
        present_section.append("dispatch = 1, 1, 1")
        present_section.append("cs-u0 = null")
        present_section.append("cs-t0 = null")
        present_section.append("ResourceFakeCB1 = copy ResourceFakeCB1_UAV")
        present_section.new_line()
        
        shader_overrides = [
            ("ShaderOverridevs2", "847947b4a1ad40cf", "200"),
            ("ShaderOverridevs10", "ac358c21b925075b", "201"),
            ("ShaderOverridevs1", "b1ca4834786821dd", "202"),
            ("ShaderOverridevs33", "cdf11b288d812606", "203"),
            ("ShaderOverridevs88", "8e1c0782db9e85d1", "203"),
            ("ShaderOverridevs22", "6d85d78157be3f4c", "200"),
        ]
        
        for name, hash_val, filter_idx in shader_overrides:
            present_section.append(f"[{name}]")
            present_section.append(f"hash = {hash_val}")
            present_section.append(f"filter_index = {filter_idx}")
            present_section.new_line()
        
        ini_builder.append_section(present_section)

    def add_cross_ib_resource_id_sections(self, ini_builder:M_IniBuilder):
        '''
        添加跨IB身份块
        '''
        if not self.has_cross_ib:
            return
        
        resource_id_section = M_IniSection(M_SectionType.ResourceID)
        resource_id_section.append(";特殊追加身份证区域")
        
        all_ibs = set()
        for source_ib, target_ib_list in self.cross_ib_info_dict.items():
            all_ibs.add(source_ib)
            for target_ib in target_ib_list:
                all_ibs.add(target_ib)
        
        for draw_ib in self.drawib_drawibmodel_dict.keys():
            all_ibs.add(draw_ib)
        
        sorted_ibs = sorted(list(all_ibs))
        
        for idx, ib in enumerate(sorted_ibs):
            resource_id_section.append(f"[ResourceID_{ib}]")
            resource_id_section.append("type = Buffer")
            resource_id_section.append("format = R32_FLOAT")
            resource_id_section.append(f"data = {idx * 1000}.0")
            resource_id_section.new_line()
        
        ini_builder.append_section(resource_id_section)

    def get_cross_ib_objects_for_source(self, source_ib):
        '''
        获取指定源IB的所有跨IB物体
        '''
        cross_ib_objects = []
        
        for obj_model in self.branch_model.ordered_draw_obj_data_model_list:
            if obj_model.draw_ib == source_ib:
                cross_ib_objects.append(obj_model)
        
        return cross_ib_objects

    def _split_objects_by_cross_ib(self, obj_model_list):
        '''
        将物体列表分为跨IB物体和非跨IB物体
        返回: (cross_ib_objects, non_cross_ib_objects)
        '''
        cross_ib_objects = []
        non_cross_ib_objects = []
        
        cross_ib_object_names = self.branch_model.cross_ib_object_names
        
        for obj_model in obj_model_list:
            obj_name = obj_model.obj_name
            if obj_name in cross_ib_object_names:
                cross_ib_objects.append(obj_model)
            else:
                non_cross_ib_objects.append(obj_model)
        
        return cross_ib_objects, non_cross_ib_objects

    def generate_cross_ib_block_for_source(self, source_ib, component_model):
        '''
        生成源IB的跨IB块内容
        '''
        lines = []
        lines.append(";跨 iB 区域")
        lines.append("if vs == 200 || vs == 201")
        lines.append("    run = CustomShader_ExtractCB1")
        lines.append(f"    cs-t2 = ResourceID_{source_ib}")
        lines.append("    run = CustomShader_RecordBones")
        lines.append("    run = CustomShader_RedirectCB1")
        lines.append("    vs-t0 = ResourceFakeT0_SRV")
        lines.append("    vs-cb1 = ResourceFakeCB1")
        lines.append(";所有需要跨 Ib 的物体引用")
        
        cross_ib_objects, non_cross_ib_objects = self._split_objects_by_cross_ib(
            component_model.final_ordered_draw_obj_model_list
        )
        
        if cross_ib_objects:
            drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(cross_ib_objects)
            for drawindexed_str in drawindexed_str_list:
                if drawindexed_str.strip():
                    lines.append(drawindexed_str)
        
        lines.append("endif")
        lines.append(";不需要跨 Ib 的物体引用")
        
        if non_cross_ib_objects:
            drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(non_cross_ib_objects)
            for drawindexed_str in drawindexed_str_list:
                if drawindexed_str.strip():
                    lines.append(drawindexed_str)
        
        lines.append("")
        lines.append("post vs-cb1 = null")
        lines.append("post vs-t0 = null")
        lines.append("post cs-t2 = null")
        
        return lines

 

    def add_unity_vs_texture_override_ib_sections(self, config_ini_builder:M_IniBuilder, commandlist_ini_builder:M_IniBuilder, draw_ib_model:DrawIBModel, is_cross_ib_source=False, is_cross_ib_target=False, source_ib_list_for_target=None, part_name=None):
        if source_ib_list_for_target is None:
            source_ib_list_for_target = []
        
        texture_override_ib_section = M_IniSection(M_SectionType.TextureOverrideIB)
        draw_ib = draw_ib_model.draw_ib
        
        d3d11GameType = draw_ib_model.d3d11GameType

        match_first_index = draw_ib_model.import_config.match_first_index_list[draw_ib_model.import_config.part_name_list.index(part_name)]
        style_part_name = "Component" + part_name

        texture_override_name_suffix = "IB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + style_part_name

        ib_resource_name = ""
        ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(part_name,None)
            

        texture_override_ib_section.append("[TextureOverride_" + texture_override_name_suffix + "]")
        texture_override_ib_section.append("hash = " + draw_ib)
        texture_override_ib_section.append("match_first_index = " + match_first_index)

        if self.vlr_filter_index_indent != "":
            texture_override_ib_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

        texture_override_ib_section.append(self.vlr_filter_index_indent + "handling = skip")
        
        if is_cross_ib_target:
            texture_override_ib_section.append(self.vlr_filter_index_indent + "analyse_options = deferred_ctx_immediate dump_rt dump_cb dump_vb dump_ib buf txt dds dump_tex dds symlink")

        ib_buf = draw_ib_model.componentname_ibbuf_dict.get("Component " + part_name,None)
        if ib_buf is None or len(ib_buf) == 0:
            texture_override_ib_section.append("ib = null")
            texture_override_ib_section.new_line()
            config_ini_builder.append_section(texture_override_ib_section)
            return

        texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\EFMIv1\\OverrideTextures")

        if not Properties_GenerateMod.forbid_auto_texture_ini():
            texture_markup_info_list = draw_ib_model.import_config.partname_texturemarkinfolist_dict.get(part_name,None)
            if texture_markup_info_list is not None:
                if Properties_GenerateMod.use_rabbitfx_slot():
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            if texture_markup_info.mark_name == "DiffuseMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\Diffuse = ref " + texture_markup_info.get_resource_name())
                            elif texture_markup_info.mark_name == "LightMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\LightMap = ref " + texture_markup_info.get_resource_name())
                            elif texture_markup_info.mark_name == "NormalMap":
                                texture_override_ib_section.append(self.vlr_filter_index_indent + "Resource\\RabbitFx\\NormalMap = ref " + texture_markup_info.get_resource_name())
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CommandList\\RabbitFx\\SetTextures")
                    
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            if texture_markup_info.mark_name in ["DiffuseMap", "LightMap", "NormalMap"]:
                                pass
                            else:
                                texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())
                else:
                    for texture_markup_info in texture_markup_info_list:
                        if texture_markup_info.mark_type == "Slot":
                            texture_override_ib_section.append(self.vlr_filter_index_indent + texture_markup_info.mark_slot + " = " + texture_markup_info.get_resource_name())

        for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
            texture_override_ib_section.append(self.vlr_filter_index_indent + category_original_slot + " = Resource" + draw_ib + original_category_name)

        if Properties_GenerateMod.add_rain_effect():
            texture_override_ib_section.append(self.vlr_filter_index_indent + "vb3 = Resource" + draw_ib + "Position")

        texture_override_ib_section.append(self.vlr_filter_index_indent + "ib = " + ib_resource_name)

        if not d3d11GameType.GPU_PreSkinning:
            for category_name in d3d11GameType.OrderedCategoryNameList:
                category_hash = draw_ib_model.import_config.category_hash_dict[category_name]
                category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]

                for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                    if original_category_name == draw_category_name:
                        category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                        texture_override_ib_section.append(self.vlr_filter_index_indent + category_original_slot + " = Resource" + draw_ib + original_category_name)


        component_name = "Component " + part_name 
        component_model = draw_ib_model.component_name_component_model_dict[component_name]

        if is_cross_ib_source and self.has_cross_ib:
            cross_ib_lines = self.generate_cross_ib_block_for_source(draw_ib, component_model)
            for line in cross_ib_lines:
                texture_override_ib_section.append(self.vlr_filter_index_indent + line)
        
        elif is_cross_ib_target and self.has_cross_ib and source_ib_list_for_target:
            all_cross_ib_objects = []
            all_non_cross_ib_objects = []
            
            for source_ib in source_ib_list_for_target:
                source_hash, source_component_index = source_ib.split("_")
                source_component_index = int(source_component_index)
                source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                source_component_model = None
                if source_ib_model:
                    if source_component_index <= len(source_ib_model.import_config.part_name_list):
                        src_part_name = source_ib_model.import_config.part_name_list[source_component_index - 1]
                        src_component_name = "Component " + src_part_name
                        if src_component_name in source_ib_model.component_name_component_model_dict:
                            source_component_model = source_ib_model.component_name_component_model_dict[src_component_name]
                
                if source_component_model:
                    cross_objs, _ = self._split_objects_by_cross_ib(
                        source_component_model.final_ordered_draw_obj_model_list
                    )
                    all_cross_ib_objects.extend(cross_objs)
                
                cross_ib_objects_in_target, non_cross_ib_objects_in_target = self._split_objects_by_cross_ib(
                    component_model.final_ordered_draw_obj_model_list
                )
                
                texture_override_ib_section.append(self.vlr_filter_index_indent + ";跨 iB 区域(当前块身份绘制,所有需要跨 Ib 的物体引用)")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "if vs == 200 || vs == 201")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_ExtractCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{draw_ib}")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RecordBones")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-t0 = ResourceFakeT0_SRV")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "    vs-cb1 = ResourceFakeCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + ";所有需要跨 Ib 的物体引用")
                
                if all_cross_ib_objects:
                    drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(all_cross_ib_objects)
                    for drawindexed_str in drawindexed_str_list:
                        if drawindexed_str.strip():
                            texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                
                texture_override_ib_section.append(self.vlr_filter_index_indent + "endif")
                texture_override_ib_section.append(self.vlr_filter_index_indent + ";当前块身份,绘制当前块本身拥有的物体")
                texture_override_ib_section.append(self.vlr_filter_index_indent + f"cs-t2 = ResourceID_{draw_ib}")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "run = CustomShader_RedirectCB1")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vs-t0 = ResourceFakeT0_SRV")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "vs-cb1 = ResourceFakeCB1")
                
                all_target_objects = component_model.final_ordered_draw_obj_model_list
                if all_target_objects:
                    drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(all_target_objects)
                    for drawindexed_str in drawindexed_str_list:
                        if drawindexed_str.strip():
                            texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                
                for source_ib in source_ib_list_for_target:
                    source_hash, source_component_index = source_ib.split("_")
                    source_component_index = int(source_component_index)
                    source_ib_model = self.drawib_drawibmodel_dict.get(source_hash)
                    source_component_model = None
                    if source_ib_model:
                        if source_component_index <= len(source_ib_model.import_config.part_name_list):
                            src_part_name = source_ib_model.import_config.part_name_list[source_component_index - 1]
                            src_component_name = "Component " + src_part_name
                            if src_component_name in source_ib_model.component_name_component_model_dict:
                                source_component_model = source_ib_model.component_name_component_model_dict[src_component_name]
                    
                    cross_objs, _ = self._split_objects_by_cross_ib(
                        source_component_model.final_ordered_draw_obj_model_list if source_component_model else []
                    )
                    
                    if not cross_objs:
                        continue
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f";跨 IB 身份块,绘制 {source_hash} 需要跨 Ib 的物体引用")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "if vs == 202 || vs == 203")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    cs-t2 = ResourceID_{source_hash}")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "    run = CustomShader_RedirectCB1")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "    ;跨 IB 块数据区域")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb0 = Resource{source_hash}Position")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb1 = Resource{source_hash}Texcoord")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb2 = Resource{source_hash}Blend")
                    texture_override_ib_section.append(self.vlr_filter_index_indent + f"    vb3 = Resource{source_hash}Position")
                    
                    if source_ib_model:
                        if source_component_index <= len(source_ib_model.import_config.part_name_list):
                            src_part_name = source_ib_model.import_config.part_name_list[source_component_index - 1]
                            ib_resource_name = source_ib_model.PartName_IBResourceName_Dict.get(src_part_name)
                            if ib_resource_name:
                                texture_override_ib_section.append(self.vlr_filter_index_indent + f"    ib = {ib_resource_name}")
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + ";所有需要跨 Ib 的物体引用")
                    
                    drawindexed_str_list = M_IniHelper.get_drawindexed_instanced_str_list(cross_objs)
                    for drawindexed_str in drawindexed_str_list:
                        if drawindexed_str.strip():
                            texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
                    
                    texture_override_ib_section.append(self.vlr_filter_index_indent + "endif")
                
                texture_override_ib_section.append(self.vlr_filter_index_indent + "")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-cb1 = null")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "post vs-t0 = null")
                texture_override_ib_section.append(self.vlr_filter_index_indent + "post cs-t2 = null")
        
        else:
            drawindexed_str_list = M_IniHelper.get_drawindexed_str_list(component_model.final_ordered_draw_obj_model_list)
            for drawindexed_str in drawindexed_str_list:
                texture_override_ib_section.append(self.vlr_filter_index_indent + drawindexed_str)
        
        if self.vlr_filter_index_indent:
            texture_override_ib_section.append("endif")
            texture_override_ib_section.new_line()
        
        if len(self.branch_model.keyname_mkey_dict.keys()) != 0:
            texture_override_ib_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")
            
            if Properties_GenerateMod.generate_branch_mod_gui():
                texture_override_ib_section.append("$ActiveCharacter = 1")
            
        config_ini_builder.append_section(texture_override_ib_section)


    def add_unity_vs_resource_vb_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add Resource VB Section
        '''
        resource_vb_section = M_IniSection(M_SectionType.ResourceBuffer)
        for category_name in draw_ib_model.d3d11GameType.OrderedCategoryNameList:
            resource_vb_section.append("[Resource" + draw_ib_model.draw_ib + category_name + "]")
            resource_vb_section.append("type = Buffer")

            resource_vb_section.append("stride = " + str(draw_ib_model.d3d11GameType.CategoryStrideDict[category_name]))
            
            buffer_folder_name = GlobalConfig.get_buffer_folder_name()
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + draw_ib_model.draw_ib + "-" + category_name + ".buf")
            # resource_vb_section.append(";VertexCount: " + str(draw_ib_model.draw_number))
            resource_vb_section.new_line()
        
        '''
        Add Resource IB Section

        We default use R32_UINT because R16_UINT have a very small number limit.
        '''

        for partname, ib_filename in draw_ib_model.PartName_IBBufferFileName_Dict.items():
            ib_resource_name = draw_ib_model.PartName_IBResourceName_Dict.get(partname,None)
            resource_vb_section.append("[" + ib_resource_name + "]")
            resource_vb_section.append("type = Buffer")
            resource_vb_section.append("format = DXGI_FORMAT_R32_UINT")
            buffer_folder_name = GlobalConfig.get_buffer_folder_name()
            resource_vb_section.append("filename = " + buffer_folder_name + "/" + ib_filename)
            resource_vb_section.new_line()

        ini_builder.append_section(resource_vb_section)


    def add_resource_texture_sections(self,ini_builder,draw_ib_model:DrawIBModel):
        '''
        Add texture resource.
        只有槽位风格贴图会用到，因为Hash风格贴图有专门的方法去声明这个。
        '''
        if Properties_GenerateMod.forbid_auto_texture_ini():
            return 
        
        resource_texture_section = M_IniSection(M_SectionType.ResourceTexture)
        for partname, texture_markup_info_list in draw_ib_model.import_config.partname_texturemarkinfolist_dict.items():
            for texture_markup_info in texture_markup_info_list:
                if texture_markup_info.mark_type == "Slot":
                    resource_texture_section.append("[" + texture_markup_info.get_resource_name() + "]")
                    resource_texture_section.append("filename = Texture/" + texture_markup_info.mark_filename)
                    resource_texture_section.new_line()

        ini_builder.append_section(resource_texture_section)


    def add_unity_cs_texture_override_vb_sections(self,config_ini_builder:M_IniBuilder,commandlist_ini_builder:M_IniBuilder,draw_ib_model:DrawIBModel):
        # 声明TextureOverrideVB部分，只有使用GPU-PreSkinning时是直接替换hash对应槽位
        d3d11GameType = draw_ib_model.d3d11GameType
        draw_ib = draw_ib_model.draw_ib

        if d3d11GameType.GPU_PreSkinning:
            texture_override_vb_section = M_IniSection(M_SectionType.TextureOverrideVB)
            texture_override_vb_section.append("; " + draw_ib)
            for category_name in d3d11GameType.OrderedCategoryNameList:
                category_hash = draw_ib_model.category_hash_dict[category_name]
                category_slot = d3d11GameType.CategoryExtractSlotDict[category_name]
                texture_override_vb_namesuffix = "VB_" + draw_ib + "_" + draw_ib_model.draw_ib_alias + "_" + category_name

                if GlobalConfig.logic_name == LogicName.SRMI:
                    if category_name == "Position":
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "_VertexLimitRaise]")
                        texture_override_vb_section.append("override_byte_stride = " + str(d3d11GameType.CategoryStrideDict["Position"]))
                        texture_override_vb_section.append("override_vertex_count = " + str(draw_ib_model.draw_number))
                        texture_override_vb_section.append("uav_byte_stride = 4")
                    else:
                        texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                else:
                    texture_override_vb_section.append("[TextureOverride_" + texture_override_vb_namesuffix + "]")
                texture_override_vb_section.append("hash = " + category_hash)
                


                # 如果出现了VertexLimitRaise，Texcoord槽位需要检测filter_index才能替换
                filterindex_indent_prefix = ""
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("if vb0 == " + str(3000 + M_GlobalKeyCounter.generated_mod_number))

                # 遍历获取所有在当前分类hash下进行替换的分类，并添加对应的资源替换
                for original_category_name, draw_category_name in d3d11GameType.CategoryDrawCategoryDict.items():
                    if category_name == draw_category_name:
                        if original_category_name == "Position":
                            texture_override_vb_section.append("cs-cb0 = Resource_" + draw_ib + "_VertexLimit")

                            position_category_slot = d3d11GameType.CategoryExtractSlotDict["Position"]
                            blend_category_slot = d3d11GameType.CategoryExtractSlotDict["Blend"]
                            # print(position_category_slot)

                            texture_override_vb_section.append(position_category_slot + " = Resource" + draw_ib + "Position")
                            texture_override_vb_section.append(blend_category_slot + " = Resource" + draw_ib + "Blend")

                            texture_override_vb_section.append("handling = skip")

                            dispatch_number = int(math.ceil(draw_ib_model.draw_number / 64)) + 1
                            texture_override_vb_section.append("dispatch = " + str(dispatch_number) + ",1,1")
                        elif original_category_name != "Blend":
                            category_original_slot = d3d11GameType.CategoryExtractSlotDict[original_category_name]
                            texture_override_vb_section.append(filterindex_indent_prefix  + category_original_slot + " = Resource" + draw_ib + original_category_name)

                # 对应if vb0 == 3000的结束
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Texcoord"]:
                    if self.vlr_filter_index_indent != "":
                        texture_override_vb_section.append("endif")
                
                # 分支架构，如果是Position则需提供激活变量
                if category_name == d3d11GameType.CategoryDrawCategoryDict["Position"]:
                    if draw_ib_model.key_number != 0:
                        texture_override_vb_section.append("$active" + str(M_GlobalKeyCounter.generated_mod_number) + " = 1")

                texture_override_vb_section.new_line()
            config_ini_builder.append_section(texture_override_vb_section)
            


    def generate_unity_vs_config_ini(self):
        '''
        EFMI
        '''
        config_ini_builder = M_IniBuilder()
        
        if self.has_cross_ib:
            for node_name, cross_ib_method in self.cross_ib_method_dict.items():
                if cross_ib_method != 'END_FIELD':
                    print(f"[CrossIB] 警告: 节点 {node_name} 使用的跨 IB 方式 '{cross_ib_method}' 不适用于 EFMI 模式")
                    print(f"[CrossIB] EFMI 模式只支持 'END_FIELD' (终末地跨 IB) 方式")
                    self.has_cross_ib = False
                    break

        if self.has_cross_ib:
            self.add_cross_ib_present_section(config_ini_builder)
            self.add_cross_ib_resource_id_sections(config_ini_builder)

        M_IniHelper.generate_hash_style_texture_ini(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        print("Length: " + str(len(self.drawib_drawibmodel_dict.items())))

        for draw_ib, draw_ib_model in self.drawib_drawibmodel_dict.items():
            print("Generating Config INI for DrawIB: " + draw_ib)

            for count_i, part_name in enumerate(draw_ib_model.import_config.part_name_list):
                component_index = count_i + 1
                current_ib_key = f"{draw_ib}_{component_index}"
                
                is_source_ib = current_ib_key in self.cross_ib_info_dict
                
                source_ib_list_for_target = []
                for source_ib, target_ib_list in self.cross_ib_info_dict.items():
                    if current_ib_key in target_ib_list:
                        source_ib_list_for_target.append(source_ib)
                
                is_target_ib = len(source_ib_list_for_target) > 0

                self.add_unity_vs_texture_override_ib_sections(
                    config_ini_builder=config_ini_builder,
                    commandlist_ini_builder=config_ini_builder,
                    draw_ib_model=draw_ib_model,
                    is_cross_ib_source=is_source_ib,
                    is_cross_ib_target=is_target_ib,
                    source_ib_list_for_target=source_ib_list_for_target,
                    part_name=part_name
                )
            
            self.add_unity_vs_resource_vb_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)
            self.add_resource_texture_sections(ini_builder=config_ini_builder,draw_ib_model=draw_ib_model)

            M_IniHelper.move_slot_style_textures(draw_ib_model=draw_ib_model)

            M_GlobalKeyCounter.generated_mod_number = M_GlobalKeyCounter.generated_mod_number + 1

        
        M_IniHelper.add_branch_key_sections(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)
        M_IniHelper.add_shapekey_ini_sections(ini_builder=config_ini_builder,drawib_drawibmodel_dict=self.drawib_drawibmodel_dict)
        M_IniHelperGUI.add_branch_mod_gui_section(ini_builder=config_ini_builder,key_name_mkey_dict=self.branch_model.keyname_mkey_dict)

        config_ini_builder.save_to_file(GlobalConfig.path_generate_mod_folder() + GlobalConfig.workspacename + ".ini")

        if self.has_cross_ib:
            self.copy_cross_ib_hlsl_files()

    def copy_cross_ib_hlsl_files(self):
        '''
        复制跨IB所需的HLSL文件到模组res目录
        '''
        addon_dir = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        source_dir = os.path.join(addon_dir, "超级工具集")
        
        if not os.path.exists(source_dir):
            print(f"[CrossIB] 警告: 超级工具集目录不存在: {source_dir}")
            return
        
        hlsl_files = [
            'extract_cb1_ps.hlsl',
            'extract_cb1_vs.hlsl',
            'record_bones_cs.hlsl',
            'redirect_cb1_cs.hlsl'
        ]
        
        mod_export_path = GlobalConfig.path_generate_mod_folder()
        res_dir = os.path.join(mod_export_path, "res")
        os.makedirs(res_dir, exist_ok=True)
        
        copied_count = 0
        for hlsl_file in hlsl_files:
            source_file = os.path.join(source_dir, hlsl_file)
            target_file = os.path.join(res_dir, hlsl_file)
            
            if os.path.exists(source_file):
                if not os.path.exists(target_file):
                    shutil.copy2(source_file, target_file)
                    print(f"[CrossIB] 已复制: {hlsl_file}")
                    copied_count += 1
                else:
                    print(f"[CrossIB] 文件已存在，跳过: {hlsl_file}")
            else:
                print(f"[CrossIB] 警告: 源文件不存在: {source_file}")
        
        print(f"[CrossIB] 共复制 {copied_count} 个HLSL文件到 {res_dir}")






