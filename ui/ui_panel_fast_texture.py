'''
快速上贴图技术
直接从DedupedTextures文件夹里显示预览贴图
然后直接快速上贴图
此时不参与自动贴图ini流程
仅用于预览显示
'''

import bpy
import os
import shutil
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ImportHelper
import bpy.utils.previews

from ..config.main_config import GlobalConfig

from ..utils.translate_utils import TR
from ..utils.json_utils import JsonUtils
from ..utils.collection_utils import CollectionUtils,CollectionColor

# 存储预览图集合
fast_preview_collections = {}

# 定义图片列表项
class SSMT_ImportTexture_ImageListItem(PropertyGroup):
    name: StringProperty(name="Image Name") # type: ignore
    filepath: StringProperty(name="File Path") # type: ignore

# 自定义UI列表显示图片和缩略图
class SSMT_UL_FastImportTextureList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        pcoll = fast_preview_collections["main"]
        
        if self.layout_type in {'DEFAULT', 'Expand'}:
            # 尝试获取预览图标
            if item.name in pcoll:
                layout.template_icon(icon_value=pcoll[item.name].icon_id, scale=1.0)
            else:
                layout.label(text="", icon='IMAGE_DATA')
            
            layout.label(text=item.name)
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            if item.name in pcoll:
                layout.template_icon(icon_value=pcoll[item.name].icon_id, scale=6.0)
            else:
                layout.label(text="", icon='IMAGE_DATA')


# 自动检测并设置DedupedTextures文件夹
class SSMT_ImportTexture_WM_OT_AutoDetectTextureFolder(Operator):
    bl_idname = "ssmt.auto_detect_texture_folder"
    bl_label = TR.translate("读取DedupedTextures")
    
    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}
        
        # 获取第一个选中的对象
        obj = selected_objects[0]
        obj_name = obj.name 
        
        # 构建路径
        selected_drawib_folder_path = os.path.join(GlobalConfig.path_workspace_folder(),  obj_name.split("-")[0] + "\\"  )
        
        deduped_textures_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures\\")

        deduped_textures_exists = os.path.exists(deduped_textures_folder_path)

        # 检查路径是否存在
        if not deduped_textures_exists:
            self.report({'ERROR'}, TR.translate("未找到当前DrawIB: " + obj_name.split("-")[0] + "的DedupedTextures转换后的贴图文件夹，请确保此IB在当前工作空间中已经正常提取出来了"))
            return {'CANCELLED'}
        
        # 清空之前的列表和预览
        bpy.context.scene.image_list.clear()
        pcoll = fast_preview_collections["main"]
        pcoll.clear()
        
        # 支持的图片格式
        image_extensions = ('.dds')
        
        # 遍历文件夹，收集图片文件
        image_count = 0
        for filename in os.listdir(deduped_textures_folder_path):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(deduped_textures_folder_path, filename)
                if os.path.isfile(full_path):
                    item = bpy.context.scene.image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    # 加载预览图
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")

        return {'FINISHED'}



class SSMT_FastTexture_ComponentOnly(Operator):
    bl_idname = "ssmt.fast_texture_component_only"
    bl_label = TR.translate("读取当前Component专属贴图")
    
    def execute(self, context):
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}
        
        # 获取第一个选中的对象
        obj = selected_objects[0]
        obj_name = obj.name

        obj_name_splits = obj_name.split("-")
        if len(obj_name_splits) < 3:
            self.report({'ERROR'}, "您当前选中的物体命名不符合SSMT模型制作规范: DrawIB-Component数-自定义名称，无法自动识别可用的贴图列表")
            return {'CANCELLED'}

        draw_ib = obj_name_splits[0]
        component_index = obj_name_splits[1]

        # 构建路径
        selected_drawib_folder_path = os.path.join(GlobalConfig.path_workspace_folder(),  draw_ib + "\\"  )
        deduped_textures_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures\\")

        deduped_textures_exists = os.path.exists(deduped_textures_folder_path)
        # 检查路径是否存在
        if not deduped_textures_exists:
            self.report({'ERROR'}, TR.translate("未找到当前DrawIB: " + obj_name.split("-")[0] + "的DedupedTextures转换后的贴图文件夹，请确保此IB在当前工作空间中已经正常提取出来了"))
            return {'CANCELLED'}
        
        # 现在，读取ComponentName_DrawCallIndexList.json以及TrianglelistDedupedFileName.json
        # 来共同确定当前Component可以选择的DedupedTextures贴图有哪些，这样就缩小了范围
        # 如果不缩小范围的话，以WWMI为例，每一个Component用到的贴图是不同的，如果只是在DedupedTextures中进行寻找
        # 就会有很多其它的贴图干扰项，大海捞针了。
        component_name__drawcall_indexlist_json_path = os.path.join(selected_drawib_folder_path,"ComponentName_DrawCallIndexList.json")
        trianglelist_deduped_filename_json_path = os.path.join(selected_drawib_folder_path,"TrianglelistDedupedFileName.json")

        component_name__drawcall_indexlist_json_dict = JsonUtils.LoadFromFile(component_name__drawcall_indexlist_json_path)
        trianglelist_deduped_filename_json_dict = JsonUtils.LoadFromFile(trianglelist_deduped_filename_json_path)

        drawcall_list = component_name__drawcall_indexlist_json_dict["Component " + component_index]
        print(drawcall_list)
        
        trianglelist_texture_filename_list:list[str] = trianglelist_deduped_filename_json_dict.keys()

        available_deduped_texture_filename_set = set()
        for trianglelist_texture_filename in trianglelist_texture_filename_list:
            for drawcall in drawcall_list:
                if trianglelist_texture_filename.startswith(drawcall):
                    deduped_texture_filename = trianglelist_deduped_filename_json_dict[trianglelist_texture_filename]["FALogDedupedFileName"]
                    available_deduped_texture_filename_set.add(deduped_texture_filename)

        for available_deduped_texture_filename in available_deduped_texture_filename_set:
            print(available_deduped_texture_filename)

        
        # 清空之前的列表和预览
        bpy.context.scene.image_list.clear()
        pcoll = fast_preview_collections["main"]
        pcoll.clear()
        
        # 支持的图片格式
        image_extensions = ('.dds')
        
        # 遍历文件夹，收集图片文件
        image_count = 0
        for filename in os.listdir(deduped_textures_folder_path):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(deduped_textures_folder_path, filename)
                if os.path.isfile(full_path) and filename in available_deduped_texture_filename_set:
                    item = bpy.context.scene.image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    # 加载预览图
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")

        return {'FINISHED'}
    

# 应用图片到材质操作符
class SSMT_ImportTexture_WM_OT_ApplyImageToMaterial(Operator):
    bl_idname = "ssmt.apply_image_to_material"
    bl_label = "应用贴图到选中的物体"
    
    def execute(self, context):
        scene = context.scene
        selected_index = scene.image_list_index
        
        if selected_index < 0 or selected_index >= len(scene.image_list):
            self.report({'ERROR'}, "No image selected in the list.")
            return {'CANCELLED'}
        
        selected_image = scene.image_list[selected_index]
        image_path = selected_image.filepath
        
        # 获取或创建图像数据块
        image_data = bpy.data.images.load(image_path, check_existing=True)
        
        selected_objects = context.selected_objects
        if not selected_objects:
            self.report({'ERROR'}, "No objects selected.")
            return {'CANCELLED'}
        
        applied_count = 0
        for obj in selected_objects:
            if obj.type != 'MESH':
                continue  # 跳过非网格对象
            
            # 确保对象有材质数据块
            if not obj.data.materials:
                mat = bpy.data.materials.new(name=f"Mat_{selected_image.name}")
                obj.data.materials.append(mat)
            else:
                # 使用第一个材质槽
                mat = obj.data.materials[0]
            
            # 确保材质使用节点
            mat.use_nodes = True
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            
            # 查找或创建Principled BSDF节点
            bsdf_node = nodes.get("Principled BSDF")
            if not bsdf_node:
                # 这里是根据名称获取，所以中英文都要添加支持
                print("疑似英文Principled BSDF无法获取，尝试获取中文的原理化 BSDF")
                bsdf_node = nodes.get("原理化 BSDF")
            
            # 3.6的原理化没有空格，他娘滴，每个版本还不一样
            if not bsdf_node:
                # 这里是根据名称获取，所以中英文都要添加支持
                print("疑似英文Principled BSDF无法获取，尝试获取中文的原理化 BSDF")
                bsdf_node = nodes.get("原理化BSDF")

            if not bsdf_node:
                print("BSDF not exists ,ready to create one.")
                bsdf_node = nodes.new(type='ShaderNodeBsdfPrincipled')
                bsdf_node.location = (0, 0)
                
                # 获取材质输出节点
                output_node = nodes.get("Material Output")
                if not output_node:
                    output_node = nodes.new(type='ShaderNodeOutputMaterial')
                    output_node.location = (400, 0)
                
                # 连接到输出
                links.new(bsdf_node.outputs['BSDF'], output_node.inputs['Surface'])
            
            # 创建图像纹理节点
            tex_image = nodes.new('ShaderNodeTexImage')
            tex_image.image = image_data
            tex_image.location = (-300, 0)
            
            # 将图像纹理节点的Color输出连接到BSDF的Base Color输入
            links.new(tex_image.outputs['Color'], bsdf_node.inputs['Base Color'])
            links.new(tex_image.outputs['Alpha'], bsdf_node.inputs['Alpha'])

            applied_count += 1
        
        self.report({'INFO'}, f"Applied {selected_image.name} to {applied_count} object(s).")
        return {'FINISHED'}


# 面板UI布局
class SSMT_ImportTexture_VIEW3D_PT_ImageMaterialPanel(Panel):
    bl_label = "快速上预览贴图"
    bl_idname = "VIEW3D_PT_fast_preview_texture"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 自动检测按钮
        row = layout.row()

        row.operator("ssmt.auto_detect_texture_folder")
        layout.operator("ssmt.fast_texture_component_only")
        
        # 显示图片数量信息
        if scene.image_list:
            layout.label(text=f"Found {len(scene.image_list)} images")
        
        # 显示图片列表
        if scene.image_list:
            row = layout.row()
            row.template_list(
                "SSMT_UL_FastImportTextureList",  # 修正为正确的类名
                "Image List", 
                scene, 
                "image_list", 
                scene, 
                "image_list_index",
                rows=6
            )
        else:
            layout.label(text="No images found. Select a folder first.")
        
        # 应用材质按钮
        row = layout.row()
        row.operator("ssmt.apply_image_to_material", icon='MATERIAL_DATA')
        
        # 显示当前选中图片的预览
        if scene.image_list and scene.image_list_index >= 0 and scene.image_list_index < len(scene.image_list):
            selected_item = scene.image_list[scene.image_list_index]
            pcoll = fast_preview_collections["main"]
            
            if selected_item.name in pcoll:
                box = layout.box()
                box.label(text="Preview:")
                box.template_icon(icon_value=pcoll[selected_item.name].icon_id, scale=10.0)