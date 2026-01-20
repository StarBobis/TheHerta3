import bpy
import os
import shutil
from bpy.props import StringProperty, CollectionProperty, IntProperty, BoolProperty
from bpy.types import Operator, Panel, PropertyGroup, UIList
from bpy_extras.io_utils import ImportHelper
import bpy.utils.previews

from ..utils.obj_utils import ObjUtils

from ..importer.mesh_importer import MigotoBinaryFile, MeshImporter
from ..config.main_config import GlobalConfig

from ..utils.translate_utils import TR
from ..utils.json_utils import JsonUtils
from ..utils.collection_utils import CollectionUtils,CollectionColor

# 存储预览图集合
preview_collections = {}

# 定义图片列表项
class Sword_ImportTexture_ImageListItem(PropertyGroup):
    name: StringProperty(name="Image Name") # type: ignore
    filepath: StringProperty(name="File Path") # type: ignore

# 自定义UI列表显示图片和缩略图
class SWORD_UL_FastImportTextureList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        pcoll = preview_collections["main"]
        
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

# 选择文件夹操作符
class Sword_ImportTexture_WM_OT_SelectImageFolder(Operator, ImportHelper):
    bl_idname = "wm.select_image_folder"
    bl_label = TR.translate("选择预览贴图所在的文件夹位置")
    
    directory: StringProperty(subtype='DIR_PATH') # type: ignore
    filter_folder: BoolProperty(default=True, options={'HIDDEN'}) # type: ignore
    filter_image: BoolProperty(default=False, options={'HIDDEN'}) # type: ignore

    def execute(self, context):
        # 清空之前的列表
        context.scene.sword_image_list.clear()
        
        # 清空预览集合
        pcoll = preview_collections["main"]
        pcoll.clear()
        
        # 支持的图片格式
        image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr','.dds')
        
        # 遍历文件夹，收集图片文件
        image_count = 0
        for filename in os.listdir(self.directory):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(self.directory, filename)
                if os.path.isfile(full_path):
                    item = context.scene.sword_image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    # 加载预览图
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")
        
        self.report({'INFO'}, f"Scanned {image_count} images.")
        return {'FINISHED'}
    

def reload_textures_from_folder(picture_folder_path:str):
    # 清空之前的列表和预览
    bpy.context.scene.sword_image_list.clear()
    pcoll = preview_collections["main"]
    pcoll.clear()
    
    # 支持的图片格式
    image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr', '.dds')
    
    # 遍历文件夹，收集图片文件
    image_count = 0
    for filename in os.listdir(picture_folder_path):
        if filename.lower().endswith(image_extensions):
            full_path = os.path.join(picture_folder_path, filename)
            if os.path.isfile(full_path):
                item = bpy.context.scene.sword_image_list.add()
                item.name = filename
                item.filepath = full_path
                
                # 加载预览图
                try:
                    thumb = pcoll.load(filename, full_path, 'IMAGE')
                    image_count += 1
                except Exception as e:
                    print(f"Could not load preview for {filename}: {e}")


# 自动检测并设置DedupedTextures_jpg文件夹
class Sword_ImportTexture_WM_OT_AutoDetectTextureFolder(Operator):
    bl_idname = "wm.auto_detect_texture_folder"
    bl_label = TR.translate("自动检测提取的贴图文件夹")
    
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
        
        deduped_textures_jpg_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_jpg\\")
        deduped_textures_png_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_png\\")
        deduped_textures_tga_folder_path = os.path.join(selected_drawib_folder_path, "DedupedTextures_tga\\")

        deduped_textures_jpg_exists = os.path.exists(deduped_textures_jpg_folder_path)
        deduped_textures_png_exists = os.path.exists(deduped_textures_png_folder_path)
        deduped_textures_tga_exists = os.path.exists(deduped_textures_tga_folder_path)

        
        # 检查路径是否存在
        if not deduped_textures_jpg_exists and not deduped_textures_png_exists and not deduped_textures_tga_exists:
            self.report({'ERROR'}, TR.translate("未找到当前DrawIB: " + obj_name.split("-")[0] + "的DedupedTextures转换后的贴图文件夹，请确保此IB在当前工作空间中已经正常提取出来了"))
            return {'CANCELLED'}
        
        # 清空之前的列表和预览
        context.scene.sword_image_list.clear()
        pcoll = preview_collections["main"]
        pcoll.clear()
        
        # 支持的图片格式
        image_extensions = ('.jpg', '.jpeg', '.png', '.tiff', '.bmp', '.tga', '.exr', '.hdr','.dds')
        
        # 遍历文件夹，收集图片文件
        image_count = 0
        for filename in os.listdir(deduped_textures_jpg_folder_path):
            if filename.lower().endswith(image_extensions):
                full_path = os.path.join(deduped_textures_jpg_folder_path, filename)
                if os.path.isfile(full_path):
                    item = context.scene.sword_image_list.add()
                    item.name = filename
                    item.filepath = full_path
                    
                    # 加载预览图
                    try:
                        thumb = pcoll.load(filename, full_path, 'IMAGE')
                        image_count += 1
                    except Exception as e:
                        print(f"Could not load preview for {filename}: {e}")
        
        self.report({'INFO'}, f"Auto-detected and loaded {image_count} images from DedupedTextures_jpg folder.")
        return {'FINISHED'}



# 应用图片到材质操作符
class Sword_ImportTexture_WM_OT_ApplyImageToMaterial(Operator):
    bl_idname = "wm.apply_image_to_material"
    bl_label = "应用贴图到选中的物体"
    
    def execute(self, context):
        scene = context.scene
        selected_index = scene.sword_image_list_index
        
        if selected_index < 0 or selected_index >= len(scene.sword_image_list):
            self.report({'ERROR'}, "No image selected in the list.")
            return {'CANCELLED'}
        
        selected_image = scene.sword_image_list[selected_index]
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


class SwordImportAllReversed(bpy.types.Operator):
    bl_idname = "ssmt.import_all_reverse"
    bl_label = TR.translate("一键导入逆向出来的全部模型")
    bl_description = "把上一次一键逆向出来的所有模型全部导入到Blender，然后你可以手动筛选并删除错误的数据类型，流程上更加方便。"

    def execute(self, context):
        reverse_output_folder_path = GlobalConfig.path_reverse_output_folder()
        if not os.path.exists(reverse_output_folder_path):
            self.report({"ERROR"},"当前一键逆向结果中标注的文件夹位置不存在，请重新运行一键逆向")
            return {'FINISHED'}
        print("测试导入")

        total_folder_name = os.path.basename(reverse_output_folder_path)

        reverse_collection = CollectionUtils.create_new_collection(collection_name=total_folder_name,color_tag=CollectionColor.Red)
        bpy.context.scene.collection.children.link(reverse_collection)

        # 获取所有子文件夹
        subfolder_path_list = [f.path for f in os.scandir(reverse_output_folder_path) if f.is_dir()]

        for subfolder_path in subfolder_path_list:
            
            datatype_folder_name = os.path.basename(subfolder_path)

            datatype_collection = CollectionUtils.create_new_collection(collection_name=datatype_folder_name,color_tag=CollectionColor.White, link_to_parent_collection_name=reverse_collection.name)

            # 获取所有.fmt文件
            fmt_files = []
            for file in os.listdir(subfolder_path):
                if file.endswith('.fmt'):
                    fmt_files.append(os.path.join(subfolder_path, file))

            for fmt_filepath in fmt_files:
                # 获取带后缀的文件名
                filename_with_extension = os.path.basename(fmt_filepath)
                # 去掉后缀
                filename_without_extension = os.path.splitext(filename_with_extension)[0]
                # 调用导入功能
                mbf = MigotoBinaryFile(fmt_path=fmt_filepath,mesh_name=filename_without_extension)
                MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=datatype_collection)

                
                # Nico: 这里不再自动清除法线了，留给用户自己选择
                # 为什么呢？因为鸣潮部分模型导入的法线，本来就是没问题的
                # 只有一些特殊的法线处理方式会导致有问题
                # 所以这里还是决定让用户自己去清除

                # if mbf.fmt_file.clean_custom_normal:
                #     # 清除自定义法线
                #     print("准备清除自定义法线")
                  
                #     context.view_layer.objects.active = obj_result
                #     bpy.ops.object.mode_set(mode='OBJECT')
                #     bpy.ops.mesh.customdata_custom_splitnormals_clear() 


        # 随后把图片路径指定为当前路径
        reload_textures_from_folder(reverse_output_folder_path)

        return {'FINISHED'}


# 面板UI布局
class Sword_ImportTexture_VIEW3D_PT_ImageMaterialPanel(Panel):
    bl_label = "3Dmigoto-Sword面板"
    bl_idname = "VIEW3D_PT_image_material_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Sword'
    # bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # 一键导入逆向结果按钮
        layout.operator("ssmt.import_all_reverse")
        
        # 导入 ib vb fmt格式文件
        layout.operator("import_mesh.migoto_raw_buffers_mmt",icon='IMPORT')

        # 自动检测按钮
        row = layout.row()

        # 文件夹选择按钮
        row = layout.row()
        row.operator("wm.select_image_folder", icon='FILE_FOLDER')
        
        # 显示图片数量信息
        if scene.sword_image_list:
            layout.label(text=f"Found {len(scene.sword_image_list)} images")
        
        # 显示图片列表
        if scene.sword_image_list:
            row = layout.row()
            row.template_list(
                "SWORD_UL_FastImportTextureList",  # 修正为正确的类名
                "Image List", 
                scene, 
                "sword_image_list", 
                scene, 
                "sword_image_list_index",
                rows=6
            )
        else:
            layout.label(text="No images found. Select a folder first.")
        
        # 应用材质按钮
        row = layout.row()
        row.operator("wm.apply_image_to_material", icon='MATERIAL_DATA')
        
        # 显示当前选中图片的预览
        if scene.sword_image_list and scene.sword_image_list_index >= 0 and scene.sword_image_list_index < len(scene.sword_image_list):
            selected_item = scene.sword_image_list[scene.sword_image_list_index]
            pcoll = preview_collections["main"]
            
            if selected_item.name in pcoll:
                box = layout.box()
                box.label(text="Preview:")
                box.template_icon(icon_value=pcoll[selected_item.name].icon_id, scale=10.0)


class Sword_SplitModel_By_DrawIndexed_Panel(Panel):
    bl_label = "手动逆向后根据DrawIndexed值分割模型"
    bl_idname = "VIEW3D_PT_Sword_SplitModel_By_DrawIndexed_Panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Sword'
    # bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        layout.prop(scene, "submesh_start")
        layout.prop(scene, "submesh_count")
        
        op = layout.operator("mesh.extract_submesh")
        op.start_index = scene.submesh_start
        op.index_count = scene.submesh_count
                