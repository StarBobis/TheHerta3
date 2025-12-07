
'''
导入模型配置面板
'''
import os
import bpy

# 用于解决 AttributeError: 'IMPORT_MESH_OT_migoto_raw_buffers_mmt' object has no attribute 'filepath'
from bpy_extras.io_utils import ImportHelper 

from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import CollectionColor, CollectionUtils
from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR

from ..config.main_config import GlobalConfig, LogicName

from ..importer.mesh_importer import MeshImporter,MigotoBinaryFile


class PanelModelImportConfig(bpy.types.Panel):
    '''
    导入模型文件面板
    '''
    bl_label = "导入模型文件"
    bl_idname = "VIEW3D_PT_CATTER_WorkSpace_IO_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TheHerta3'
    # bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.properties_import_model,"model_scale",text="模型导入大小比例")
        
        if GlobalConfig.logic_name == LogicName.WWMI:
            layout.prop(context.scene.properties_wwmi,"import_merged_vgmap",text="使用融合统一顶点组")

        
        # 导入 ib vb fmt格式文件
        layout.operator("import_mesh.migoto_raw_buffers_mmt",icon='IMPORT')

        # 一键导入当前工作空间
        layout.operator("ssmt.import_all_from_workspace_v3",icon='IMPORT')

        # 决定导入时是否调用法线贴图
        layout.prop(context.scene.properties_import_model, "isUsingNormalMapWhileImporting", text="导入时使用法线贴图")



class Import3DMigotoRaw(bpy.types.Operator, ImportHelper):
    """Import raw 3DMigoto vertex and index buffers"""
    bl_idname = "import_mesh.migoto_raw_buffers_mmt"
    bl_label = TR.translate("导入.fmt .ib .vb格式模型")
    bl_description = "导入3Dmigoto格式的 .ib .vb .fmt文件，只需选择.fmt文件即可"

    # 我们只需要选择fmt文件即可，因为其它文件都是根据fmt文件的前缀来确定的。
    # 所以可以实现一个.ib 和 .vb文件存在多个数据类型描述的.fmt文件的导入。
    filename_ext = '.fmt'

    filter_glob: bpy.props.StringProperty(
        default='*.fmt',
        options={'HIDDEN'},
    ) # type: ignore

    files: bpy.props.CollectionProperty(
        name="File Path",
        type=bpy.types.OperatorFileListElement,
    ) # type: ignore

    def execute(self, context):
        # 我们需要添加到一个新建的集合里，方便后续操作
        # 这里集合的名称需要为当前文件夹的名称
        dirname = os.path.dirname(self.filepath)

        collection_name = os.path.basename(dirname)
        collection = bpy.data.collections.new(collection_name)
        bpy.context.scene.collection.children.link(collection)

        # 如果用户不选择任何fmt文件，则默认返回读取所有的fmt文件。
        import_filename_list = []
        if len(self.files) == 1:
            if str(self.filepath).endswith(".fmt"):
                import_filename_list.append(self.filepath)
            else:
                for filename in os.listdir(self.filepath):
                    if filename.endswith(".fmt"):
                        import_filename_list.append(filename)
        else:
            for fmt_file in self.files:
                import_filename_list.append(fmt_file.name)

        # 逐个fmt文件导入
        for fmt_file_name in import_filename_list:
            fmt_file_path = os.path.join(dirname, fmt_file_name)
            mbf = MigotoBinaryFile(fmt_path=fmt_file_path)
            obj_result = MeshImporter.create_mesh_obj_from_mbf(mbf=mbf)
            collection.objects.link(obj_result)



            # 刷新视图以得到流畅的导入逐渐增多的视觉效果
            bpy.context.view_layer.update()

            # 强制Blender刷新界面
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

        
        # Select all objects under collection (因为用户习惯了导入后就是全部选中的状态). 
        CollectionUtils.select_collection_objects(collection)

        return {'FINISHED'}


def ImprotFromWorkSpaceSSMTV3(self, context):
    import_drawib_aliasname_folder_path_dict = ConfigUtils.get_import_drawib_aliasname_folder_path_dict_with_first_match_type()
    print(import_drawib_aliasname_folder_path_dict)

    workspace_collection = CollectionUtils.create_new_collection(collection_name=GlobalConfig.workspacename,color_tag=CollectionColor.Red)
    # 这里先链接SourceCollection，确保它在上面
    bpy.context.scene.collection.children.link(workspace_collection)

    # 读取时保存每个DrawIB对应的GameType名称到工作空间文件夹下面的Import.json，在导出时使用
    draw_ib_gametypename_dict = {}
    for draw_ib_aliasname,import_folder_path in import_drawib_aliasname_folder_path_dict.items():
        tmp_json = ConfigUtils.read_tmp_json(import_folder_path)
        work_game_type = tmp_json.get("WorkGameType","")
        draw_ib = draw_ib_aliasname.split("_")[0]
        draw_ib_gametypename_dict[draw_ib] = work_game_type

    save_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(),"Import.json")

    JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict,filepath=save_import_json_path)
    
    # 创建一个默认显示的集合，用来存放默认显示的东西，在实际使用中几乎每次都需要我们手动创建，所以变为自动化了。
    default_show_collection = CollectionUtils.create_new_collection(collection_name="DefaultShow",color_tag=CollectionColor.White,link_to_parent_collection_name=workspace_collection.name)

    # 开始读取模型数据
    for draw_ib_aliasname,import_folder_path in import_drawib_aliasname_folder_path_dict.items():
        print("Importing DrawIB:", draw_ib_aliasname)

        draw_ib = draw_ib_aliasname.split("_")[0]
        alias_name = draw_ib_aliasname.split("_")[1]
        if alias_name == "":
            alias_name = "Original"

        import_prefix_list = ConfigUtils.get_prefix_list_from_tmp_json(import_folder_path)
        if len(import_prefix_list) == 0:
            self.report({'ERROR'},"当前output文件夹"+draw_ib_aliasname+"中的内容暂不支持一键导入分支模型")
            continue


        part_count = 1
        for prefix in import_prefix_list:
            fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
            mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
            obj_result = MeshImporter.create_mesh_obj_from_mbf(mbf=mbf)

            # 刷新视图以得到流畅的导入逐渐增多的视觉效果
            bpy.context.view_layer.update()

            # 强制Blender刷新界面
            bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
            
            default_show_collection.objects.link(obj_result)
            part_count = part_count + 1

    

    # Select all objects under collection (因为用户习惯了导入后就是全部选中的状态). 
    CollectionUtils.select_collection_objects(workspace_collection)


class SSMTImportAllFromCurrentWorkSpaceV3(bpy.types.Operator):
    bl_idname = "ssmt.import_all_from_workspace_v3"
    bl_label = TR.translate("一键导入当前工作空间内容")
    bl_description = "一键导入当前工作空间文件夹下所有的DrawIB对应的模型为SSMT集合架构"
    bl_options = {'REGISTER'}

    def execute(self, context):
        # print("Current WorkSpace: " + GlobalConfig.workspacename)
        # print("Current Game: " + GlobalConfig.gamename)
        if GlobalConfig.workspacename == "":
            self.report({"ERROR"},"Please select your WorkSpace in SSMT before import.")
        elif not os.path.exists(GlobalConfig.path_workspace_folder()):
            self.report({"ERROR"},"WorkSpace Folder Didn't exists, Please create a WorkSpace in SSMT before import " + GlobalConfig.path_workspace_folder())
        else:
            TimerUtils.Start("ImportFromWorkSpace")
            ImprotFromWorkSpaceSSMTV3(self,context)
            TimerUtils.End("ImportFromWorkSpace")
        return {'FINISHED'}
