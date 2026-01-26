
'''
导入模型配置面板
'''
import os
import bpy

# 用于解决 AttributeError: 'IMPORT_MESH_OT_migoto_raw_buffers_mmt' object has no attribute 'filepath'
from bpy_extras.io_utils import ImportHelper

from ..utils.obj_utils import ObjUtils 

from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import CollectionColor, CollectionUtils
from ..utils.timer_utils import TimerUtils
from ..utils.translate_utils import TR

from ..config.main_config import GlobalConfig, LogicName

from ..importer.mesh_importer import MeshImporter,MigotoBinaryFile
from ..base.drawib_pair import DrawIBPair


class Import3DMigotoRaw(bpy.types.Operator, ImportHelper):
    """Import raw 3DMigoto vertex and index buffers"""
    bl_idname = "import_mesh.migoto_raw_buffers_mmt"
    bl_label = TR.translate("导入.fmt .ib .vb格式模型")
    bl_description = "导入3Dmigoto格式的 .ib .vb .fmt文件，只需选择.fmt文件即可"
    bl_options = {'REGISTER','UNDO'}
    
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
            MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=collection)

        # Select all objects under collection (因为用户习惯了导入后就是全部选中的状态). 
        CollectionUtils.select_collection_objects(collection)

        return {'FINISHED'}


def ImprotFromWorkSpaceSSMTV4(self, context):
    
    # 这里先创建以当前工作空间为名称的集合，并且链接到scene，确保它存在
    workspace_collection = CollectionUtils.create_new_collection(collection_name=GlobalConfig.workspacename,color_tag=CollectionColor.Red)
    bpy.context.scene.collection.children.link(workspace_collection)

    # 创建一个默认显示的集合DefaultShow，用来存放默认显示的东西
    # 在实际使用中几乎每次都需要我们手动创建，所以变为自动化了。
    default_show_collection = CollectionUtils.create_new_collection(collection_name="DefaultShow",color_tag=CollectionColor.White,link_to_parent_collection_name=workspace_collection.name)

    # 如果此时生成Mod的下拉列表没有任何集合，就让那个下拉列表选中这个集合
    if not context.scene.active_workspace_collection:
        context.scene.active_workspace_collection = workspace_collection

    # 获取当前工作空间文件夹路径
    current_workspace_folder = GlobalConfig.path_workspace_folder()

    # 获取当前的DrawIB列表，包括Alias别名
    draw_ib_pair_list:list[DrawIBPair] = ConfigUtils.get_extract_drawib_list_from_workspace_config_json()

    # 读取时保存每个DrawIB对应的GameType名称到工作空间文件夹下面的Import.json，在导出时使用
    draw_ib_gametypename_dict = {}
    
    # 逐个DrawIB进行导入
    for draw_ib_pair in draw_ib_pair_list:
        # 获取DrwaIB和别名
        draw_ib = draw_ib_pair.DrawIB
        alias_name = draw_ib_pair.AliasName

        # 如果别名不存在 就起名为Original 意思是原本的
        if alias_name == "":
            alias_name = "Original"

        print("尝试导入DrawIB:", draw_ib)
        import_drawib_folder_path = os.path.join(current_workspace_folder, draw_ib)
        print("当前导入的DrawIB路径:", import_drawib_folder_path)

        if not os.path.exists(import_drawib_folder_path):
            self.report({'ERROR'},"目标DrawIB "+draw_ib+" 的提取文件夹不存在,请检查你的工作空间中的DrawIB列表是否正确或者是否忘记点击提取模型: " + import_drawib_folder_path)

        # 导入时，要按照先GPU类型，再CPU类型进行排序，虽然我们已经在提取模型端排序过了
        # 但是这里双重检查机制，确保没问题
        gpu_import_folder_path_list = []
        cpu_import_folder_path_list = []

        dirs = os.listdir(import_drawib_folder_path)
        for dirname in dirs:
            if not dirname.startswith("TYPE_"):
                continue
            final_import_folder_path = os.path.join(import_drawib_folder_path,dirname)
            if dirname.startswith("TYPE_GPU"):
                gpu_import_folder_path_list.append(final_import_folder_path)
            elif dirname.startswith("TYPE_CPU"):
                cpu_import_folder_path_list.append(final_import_folder_path)

        final_import_folder_path_list = []
        for gpu_path in gpu_import_folder_path_list:
            final_import_folder_path_list.append(gpu_path)
        for cpu_path in cpu_import_folder_path_list:
            final_import_folder_path_list.append(cpu_path)
        

        # 接下来开始导入，尝试对当前DrawIB的每个类型进行导入
        # 如果出错的话直接提示错误并continue，直到顺位第一个导入成功
        for import_folder_path in final_import_folder_path_list:
            gametype_name = import_folder_path.split("TYPE_")[1]
            print("尝试导入数据类型: " + gametype_name)

            print("DrawIB " + draw_ib + "尝试导入路径: " + import_folder_path)

            import_prefix_list = ConfigUtils.get_prefix_list_from_tmp_json(import_folder_path)
            if len(import_prefix_list) == 0:
                self.report({'ERROR'},"当前数据类型暂不支持一键导入分支模型")
                continue

            # try:
            #     part_count = 1
            #     for prefix in import_prefix_list:
                    
            #         fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
            #         mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
            #         MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=default_show_collection)

            #         part_count = part_count + 1
            # except Exception as e:
            #     self.report({'WARNING'},"导入DrawIB " + draw_ib + "的数据类型: " + gametype_name + " 时出错，尝试下一个数据类型。错误信息: " + str(e))
            #     continue

            # 上面的给用户使用，下面的用于测试
            part_count = 1
            for prefix in import_prefix_list:
                
                fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
                mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
                MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=default_show_collection)

                part_count = part_count + 1

            # 如果能执行到这里，说明这个DrawIB成功导入了一个数据类型
            # 然后要把这个DrawIB对应的GameType名称保存下来
            tmp_json = ConfigUtils.read_tmp_json(import_folder_path)
            work_game_type = tmp_json.get("WorkGameType","")
            draw_ib_gametypename_dict[draw_ib] = work_game_type
            self.report({'INFO'}, "成功导入DrawIB " + draw_ib + " 的数据类型: " + gametype_name)
            break

    # 保存Import.json文件
    save_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(),"Import.json")
    JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict,filepath=save_import_json_path)
    
    # 因为用户习惯了导入后就是全部选中的状态，所以默认选中所有导入的obj
    CollectionUtils.select_collection_objects(workspace_collection)


def ImprotFromWorkSpaceSSMTBlueprint(self, context):
    
    # 这里先创建以当前工作空间为名称的集合，并且链接到scene，确保它存在
    workspace_collection = CollectionUtils.create_new_collection(collection_name=GlobalConfig.workspacename,color_tag=CollectionColor.Red)
    bpy.context.scene.collection.children.link(workspace_collection)

    # 创建一个默认显示的集合DefaultShow，用来存放默认显示的东西
    # 在实际使用中几乎每次都需要我们手动创建，所以变为自动化了。
    default_show_collection = CollectionUtils.create_new_collection(collection_name="DefaultShow",color_tag=CollectionColor.White,link_to_parent_collection_name=workspace_collection.name)

    # 如果此时生成Mod的下拉列表没有任何集合，就让那个下拉列表选中这个集合
    if not context.scene.active_workspace_collection:
        context.scene.active_workspace_collection = workspace_collection

    # 获取当前工作空间文件夹路径
    current_workspace_folder = GlobalConfig.path_workspace_folder()

    # 获取当前的DrawIB列表，包括Alias别名
    draw_ib_pair_list:list[DrawIBPair] = ConfigUtils.get_extract_drawib_list_from_workspace_config_json()

    # 读取时保存每个DrawIB对应的GameType名称到工作空间文件夹下面的Import.json，在导出时使用
    draw_ib_gametypename_dict = {}
    
    # 逐个DrawIB进行导入
    for draw_ib_pair in draw_ib_pair_list:
        # 获取DrwaIB和别名
        draw_ib = draw_ib_pair.DrawIB
        alias_name = draw_ib_pair.AliasName

        # 如果别名不存在 就起名为Original 意思是原本的
        if alias_name == "":
            alias_name = "Original"

        print("尝试导入DrawIB:", draw_ib)
        import_drawib_folder_path = os.path.join(current_workspace_folder, draw_ib)
        print("当前导入的DrawIB路径:", import_drawib_folder_path)

        if not os.path.exists(import_drawib_folder_path):
            self.report({'ERROR'},"目标DrawIB "+draw_ib+" 的提取文件夹不存在,请检查你的工作空间中的DrawIB列表是否正确或者是否忘记点击提取模型: " + import_drawib_folder_path)

        # 导入时，要按照先GPU类型，再CPU类型进行排序，虽然我们已经在提取模型端排序过了
        # 但是这里双重检查机制，确保没问题
        gpu_import_folder_path_list = []
        cpu_import_folder_path_list = []

        dirs = os.listdir(import_drawib_folder_path)
        for dirname in dirs:
            if not dirname.startswith("TYPE_"):
                continue
            final_import_folder_path = os.path.join(import_drawib_folder_path,dirname)
            if dirname.startswith("TYPE_GPU"):
                gpu_import_folder_path_list.append(final_import_folder_path)
            elif dirname.startswith("TYPE_CPU"):
                cpu_import_folder_path_list.append(final_import_folder_path)

        final_import_folder_path_list = []
        for gpu_path in gpu_import_folder_path_list:
            final_import_folder_path_list.append(gpu_path)
        for cpu_path in cpu_import_folder_path_list:
            final_import_folder_path_list.append(cpu_path)
        

        # 接下来开始导入，尝试对当前DrawIB的每个类型进行导入
        # 如果出错的话直接提示错误并continue，直到顺位第一个导入成功
        for import_folder_path in final_import_folder_path_list:
            gametype_name = import_folder_path.split("TYPE_")[1]
            print("尝试导入数据类型: " + gametype_name)

            print("DrawIB " + draw_ib + "尝试导入路径: " + import_folder_path)

            import_prefix_list = ConfigUtils.get_prefix_list_from_tmp_json(import_folder_path)
            if len(import_prefix_list) == 0:
                self.report({'ERROR'},"当前数据类型暂不支持一键导入分支模型")
                continue

            # try:
            #     part_count = 1
            #     for prefix in import_prefix_list:
                    
            #         fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
            #         mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
            #         MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=default_show_collection)

            #         part_count = part_count + 1
            # except Exception as e:
            #     self.report({'WARNING'},"导入DrawIB " + draw_ib + "的数据类型: " + gametype_name + " 时出错，尝试下一个数据类型。错误信息: " + str(e))
            #     continue

            # 上面的给用户使用，下面的用于测试
            part_count = 1
            for prefix in import_prefix_list:
                
                fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
                mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
                MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=default_show_collection)

                part_count = part_count + 1

            # 如果能执行到这里，说明这个DrawIB成功导入了一个数据类型
            # 然后要把这个DrawIB对应的GameType名称保存下来
            tmp_json = ConfigUtils.read_tmp_json(import_folder_path)
            work_game_type = tmp_json.get("WorkGameType","")
            draw_ib_gametypename_dict[draw_ib] = work_game_type
            self.report({'INFO'}, "成功导入DrawIB " + draw_ib + " 的数据类型: " + gametype_name)
            break

    # 保存Import.json文件
    save_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(),"Import.json")
    JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict,filepath=save_import_json_path)
    
    # 因为用户习惯了导入后就是全部选中的状态，所以默认选中所有导入的obj
    CollectionUtils.select_collection_objects(workspace_collection)

    # ==========================
    # 自动生成蓝图节点逻辑
    # ==========================
    try:
        # 1. 获取或创建蓝图树
        tree_name = f"Mod_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "SSMT_Mod_Logic"
        tree = bpy.data.node_groups.get(tree_name)
        if not tree:
            # 重要：先检查类型是否已注册
            if 'SSMTBlueprintTreeType' in bpy.types.NodeTree.bl_rna.properties['type'].enum_items:
                 pass # 如果能直接 new 最好
                 
            try:
                tree = bpy.data.node_groups.new(name=tree_name, type='SSMTBlueprintTreeType')
            except Exception as e:
                print(f"Failed to create new node tree: {e}. Check if SSMTBlueprintTreeType is registered.")
                # Fallback or return
                return

            tree.use_fake_user = True
        
        # 2. 清空现有节点并重新生成
        tree.nodes.clear()
        
        # 3. 遍历导入的对象并创建对应节点
        current_x = 200
        current_y = 0
        y_gap = 250 # 增加垂直间距
        
        count = 0
        
        # 此时 default_show_collection 应该在作用域内，因为它是上面的局部变量
        # 且导入的模型都放在这个集合里
        if 'default_show_collection' in locals() and default_show_collection:
             target_objects = default_show_collection.objects
        else:
             # Fallback: 尝试通过名称寻找，或者使用 workspace_collection
             target_objects = []
             if 'workspace_collection' in locals() and workspace_collection:
                 # 简易递归或直接查子集合
                 for child in workspace_collection.children:
                     if child.name == "DefaultShow":
                         target_objects = child.objects
                         break
        
        if not target_objects:
             print("Warning: Could not find DefaultShow collection to generate blueprint nodes.")

        for draw_ib_pair in draw_ib_pair_list:
            draw_ib = draw_ib_pair.DrawIB
            alias_name = draw_ib_pair.AliasName
            
            real_alias_name = alias_name if alias_name else "Original"
            
            # 在导入集合中寻找属于当前 DrawIB 的对象
            # 命名规则通常是: DrawIB-Part-Alias
            # 我们匹配 names starting with draw_ib
            
            found_objs = [obj for obj in target_objects if obj.name.startswith(draw_ib)]
            
            for obj in found_objs:
                 if obj.type == 'MESH':
                    # 创建节点
                    node = tree.nodes.new('SSMTNode_Object_Info')
                    node.location = (current_x, current_y)
                    
                    # 排列逻辑：每列排 5 个
                    count += 1
                    current_y -= y_gap
                    if count % 5 == 0:
                            current_y = 0
                            current_x += 300
                    
                    # 填充属性
                    node.object_name = obj.name
                    node.draw_ib = draw_ib
                    node.component = real_alias_name
                    node.label = obj.name # 设置节点标题方便识别
                        
        print(f"Blueprint {tree_name} updated with imported objects.")
                        
        print(f"Blueprint {tree_name} updated with imported objects.")
        
    except Exception as e:
        print(f"Error generating blueprint nodes: {e}")
        import traceback
        traceback.print_exc()


class SSMTImportAllFromCurrentWorkSpaceV3(bpy.types.Operator):
    bl_idname = "ssmt.import_all_from_workspace_v3"
    bl_label = TR.translate("一键导入当前工作空间内容")
    bl_description = "一键导入当前工作空间文件夹下所有的DrawIB对应的模型为SSMT集合架构"
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        # print("Current WorkSpace: " + GlobalConfig.workspacename)
        # print("Current Game: " + GlobalConfig.gamename)
        if GlobalConfig.workspacename == "":
            self.report({"ERROR"},"Please select your WorkSpace in SSMT before import.")
        elif not os.path.exists(GlobalConfig.path_workspace_folder()):
            self.report({"ERROR"},"WorkSpace Folder Didn't exists, Please create a WorkSpace in SSMT before import " + GlobalConfig.path_workspace_folder())
        else:
            TimerUtils.Start("ImportFromWorkSpace")
            ImprotFromWorkSpaceSSMTV4(self,context)
            TimerUtils.End("ImportFromWorkSpace")
        
        return {'FINISHED'}

class SSMTImportAllFromCurrentWorkSpaceBlueprint(bpy.types.Operator):
    bl_idname = "ssmt.import_all_from_workspace_blueprint"
    bl_label = TR.translate("一键导入当前工作空间内容(蓝图架构)")
    bl_description = "一键导入当前工作空间文件夹下所有的DrawIB对应的模型为SSMT蓝图架构"
    bl_options = {'REGISTER','UNDO'}

    def execute(self, context):
        # print("Current WorkSpace: " + GlobalConfig.workspacename)
        # print("Current Game: " + GlobalConfig.gamename)
        if GlobalConfig.workspacename == "":
            self.report({"ERROR"},"Please select your WorkSpace in SSMT before import.")
        elif not os.path.exists(GlobalConfig.path_workspace_folder()):
            self.report({"ERROR"},"WorkSpace Folder Didn't exists, Please create a WorkSpace in SSMT before import " + GlobalConfig.path_workspace_folder())
        else:
            TimerUtils.Start("ImportFromWorkSpace")
            ImprotFromWorkSpaceSSMTBlueprint(self,context)
            TimerUtils.End("ImportFromWorkSpace")
        
        return {'FINISHED'}

addon_keymaps = []

def register():
    bpy.utils.register_class(Import3DMigotoRaw)
    bpy.utils.register_class(SSMTImportAllFromCurrentWorkSpaceV3)
    bpy.utils.register_class(SSMTImportAllFromCurrentWorkSpaceBlueprint)

    # 添加快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(SSMTImportAllFromCurrentWorkSpaceV3.bl_idname, 
                                    type='I', value='PRESS', 
                                    ctrl=True, alt=True, shift=False)
        addon_keymaps.append((km, kmi))

def unregister():
    # 移除快捷键
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()

    bpy.utils.unregister_class(Import3DMigotoRaw)
    bpy.utils.unregister_class(SSMTImportAllFromCurrentWorkSpaceV3)
    bpy.utils.unregister_class(SSMTImportAllFromCurrentWorkSpaceBlueprint)
