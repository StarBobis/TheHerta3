import os
import bpy

from ..utils.json_utils import JsonUtils
from ..utils.config_utils import ConfigUtils
from ..utils.collection_utils import CollectionColor, CollectionUtils
from ..utils.translate_utils import TR
from ..utils.timer_utils import TimerUtils

from ..config.main_config import GlobalConfig, LogicName
from ..config.properties_import_model import Properties_ImportModel

from ..importer.mesh_importer import MeshImporter,MigotoBinaryFile
from ..base.drawib_pair import DrawIBPair
from .blueprint_drag_drop import set_importing_state, refresh_workspace_cache


def ImportFromWorkSpaceSSMT4(self, context):
    '''
    第四代工作空间导入逻辑
    文件夹命名格式：DrawIB-IndexCount-FirstIndex
    返回: 成功导入的对象数量
    '''
    
    set_importing_state(True)
    
    workspace_collection = CollectionUtils.create_new_collection(collection_name=GlobalConfig.workspacename,color_tag=CollectionColor.Red)
    bpy.context.scene.collection.children.link(workspace_collection)

    current_workspace_folder = GlobalConfig.path_workspace_folder()

    workspace_subfolders = [f.path for f in os.scandir(current_workspace_folder) if f.is_dir() and '-' in f.name]

    foldername_gametypename_dict = {}
    imported_count = 0

    for import_folder_path in workspace_subfolders:
        import_folder_name = os.path.basename(import_folder_path)
        print("Import FolderName: " + import_folder_name)

        namesplits = import_folder_name.split('-')
        if len(namesplits) < 3:
            print(f"Warning: Skipping folder with unexpected name format (expected at least one '-'): {import_folder_name}")
            continue

        draw_ib = namesplits[0]
        index_count = namesplits[1]
        first_index = namesplits[2]

        print("尝试导入DrawIB:", draw_ib)
        
        gpu_import_folder_path_list = []
        cpu_import_folder_path_list = []

        dirs = os.listdir(import_folder_path)
        for dirname in dirs:
            if not dirname.startswith("TYPE_"):
                continue
            final_import_folder_path = os.path.join(import_folder_path,dirname)
            if dirname.startswith("TYPE_GPU"):
                gpu_import_folder_path_list.append(final_import_folder_path)
            elif dirname.startswith("TYPE_CPU"):
                cpu_import_folder_path_list.append(final_import_folder_path)

        final_import_folder_path_list = []
        for gpu_path in gpu_import_folder_path_list:
            final_import_folder_path_list.append(gpu_path)
        for cpu_path in cpu_import_folder_path_list:
            final_import_folder_path_list.append(cpu_path)
        

        for import_folder_path in final_import_folder_path_list:
            gametype_name = import_folder_path.split("TYPE_")[1]
            print("尝试导入数据类型: " + gametype_name)

            print("DrawIB " + draw_ib + "尝试导入路径: " + import_folder_path)

            fmt_file_path = os.path.join(import_folder_path, import_folder_name + ".fmt")
            if not os.path.exists(fmt_file_path):
                print(f"找不到 fmt 文件: {fmt_file_path}")
                continue
                
            mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name= import_folder_name + ".自定义名称")
            MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=workspace_collection)


            import_json_path = os.path.join(import_folder_path, "import.json")
            if os.path.exists(import_json_path):
                import_json = JsonUtils.LoadFromFile(import_json_path)
                work_game_type = import_json.get("WorkGameType","")
            else:
                tmp_json_path = os.path.join(import_folder_path, "tmp.json")
                if os.path.exists(tmp_json_path):
                    tmp_json = JsonUtils.LoadFromFile(tmp_json_path)
                    work_game_type = tmp_json.get("WorkGameType","")
                else:
                    work_game_type = ""
                    
            foldername_gametypename_dict[import_folder_name] = work_game_type
            imported_count += 1
            self.report({'INFO'}, "成功导入" + import_folder_name + " 的数据类型: " + gametype_name)
            break

    save_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(),"Import.json")
    JsonUtils.SaveToFile(json_dict=foldername_gametypename_dict,filepath=save_import_json_path)
    
    CollectionUtils.select_collection_objects(workspace_collection)

    try:
        tree_name = GlobalConfig.workspacename
        
        try:
            tree = bpy.data.node_groups.new(name=tree_name, type='SSMTBlueprintTreeType')
        except Exception as e:
            print(f"Failed to create new node tree: {e}. Check if SSMTBlueprintTreeType is registered.")
            return
        tree.use_fake_user = True
        
        group_node = tree.nodes.new('SSMTNode_Object_Group')
        group_node.label = "Default Group"
        
        current_x = 0
        current_y = 0
        y_gap = 200
        
        count = 0
        
        if 'workspace_collection' in locals() and workspace_collection:
             target_objects = workspace_collection.objects
        else:
             target_objects = []

        if not target_objects:
             print("Warning: Could not find Workspace collection to generate blueprint nodes.")

        min_y = 0
        for import_folder_path in workspace_subfolders:
            import_folder_name = os.path.basename(import_folder_path)

            namesplits = import_folder_name.split('-')
            if len(namesplits) < 3:
                continue
                
            found_objs = [obj for obj in target_objects if obj.name.startswith(import_folder_name)]
            
            for obj in found_objs:
                 if obj.type == 'MESH':
                    node = tree.nodes.new('SSMTNode_Object_Info')
                    node.location = (current_x, current_y)
                    
                    node.object_name = obj.name
                    
                    node.label = obj.name

                    if group_node.inputs[-1].is_linked:
                        group_node.inputs.new('SSMTSocketObject', f"Input {len(group_node.inputs) + 1}")
                    
                    tree.links.new(node.outputs[0], group_node.inputs[-1])
                    
                    count += 1
                    current_y -= y_gap
                    min_y = min(min_y, current_y)

        
        final_center_y = min_y / 2 if count <= 5 else -200
        
        group_node.location = (current_x + 400, final_center_y)

        output_node = tree.nodes.new('SSMTNode_Result_Output')
        output_node.location = (current_x + 800, final_center_y)
        output_node.label = "Generate Mod"
        
        if len(output_node.inputs) > 0 and len(group_node.outputs) > 0:
            tree.links.new(group_node.outputs[0], output_node.inputs[0])

        if hasattr(group_node, "update"):
             group_node.update()

        print(f"Blueprint {tree_name} updated with imported objects.")
        
    except Exception as e:
        print(f"Error generating blueprint nodes: {e}")
        import traceback
        traceback.print_exc()
    
    refresh_workspace_cache()
    
    return imported_count


def ImprotFromWorkSpaceSSMT3(self, context):
    '''
    第三代工作空间导入逻辑
    文件夹命名格式：DrawIB（只有 Hash）
    返回: 成功导入的对象数量
    '''
    
    set_importing_state(True)
    
    workspace_collection = CollectionUtils.create_new_collection(collection_name=GlobalConfig.workspacename,color_tag=CollectionColor.Red)
    bpy.context.scene.collection.children.link(workspace_collection)

    current_workspace_folder = GlobalConfig.path_workspace_folder()

    draw_ib_pair_list:list[DrawIBPair] = ConfigUtils.get_extract_drawib_list_from_workspace_config_json()

    draw_ib_gametypename_dict = {}
    imported_count = 0
    
    for draw_ib_pair in draw_ib_pair_list:
        draw_ib = draw_ib_pair.DrawIB
        alias_name = draw_ib_pair.AliasName

        if alias_name == "":
            alias_name = "Original"

        print("尝试导入DrawIB:", draw_ib)
        import_drawib_folder_path = os.path.join(current_workspace_folder, draw_ib)
        print("当前导入的DrawIB路径:", import_drawib_folder_path)

        if not os.path.exists(import_drawib_folder_path):
            self.report({'ERROR'},"目标DrawIB "+draw_ib+" 的提取文件夹不存在,请检查你的工作空间中的DrawIB列表是否正确或者是否忘记点击提取模型: " + import_drawib_folder_path)
            continue
        
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
        

        for import_folder_path in final_import_folder_path_list:
            gametype_name = import_folder_path.split("TYPE_")[1]
            print("尝试导入数据类型: " + gametype_name)

            print("DrawIB " + draw_ib + "尝试导入路径: " + import_folder_path)

            import_prefix_list = ConfigUtils.get_prefix_list_from_tmp_json(import_folder_path)
            if len(import_prefix_list) == 0:
                self.report({'ERROR'},"当前数据类型暂不支持一键导入分支模型")
                continue

            part_count = 1
            for prefix in import_prefix_list:
                
                fmt_file_path = os.path.join(import_folder_path, prefix + ".fmt")
                mbf = MigotoBinaryFile(fmt_path=fmt_file_path,mesh_name=draw_ib + "-" + str(part_count) + "-" + alias_name)
                MeshImporter.create_mesh_obj_from_mbf(mbf=mbf,import_collection=workspace_collection)

                part_count = part_count + 1

            tmp_json = ConfigUtils.read_tmp_json(import_folder_path)
            work_game_type = tmp_json.get("WorkGameType","")
            draw_ib_gametypename_dict[draw_ib] = work_game_type
            imported_count += 1
            self.report({'INFO'}, "成功导入DrawIB " + draw_ib + " 的数据类型: " + gametype_name)
            break

    save_import_json_path = os.path.join(GlobalConfig.path_workspace_folder(),"Import.json")
    JsonUtils.SaveToFile(json_dict=draw_ib_gametypename_dict,filepath=save_import_json_path)
    
    CollectionUtils.select_collection_objects(workspace_collection)

    try:
        tree_name = f"Mod_{GlobalConfig.workspacename}" if GlobalConfig.workspacename else "SSMT_Mod_Logic"
        
        try:
            tree = bpy.data.node_groups.new(name=tree_name, type='SSMTBlueprintTreeType')
        except Exception as e:
            print(f"Failed to create new node tree: {e}. Check if SSMTBlueprintTreeType is registered.")
            return

        tree.use_fake_user = True
        
        group_node = tree.nodes.new('SSMTNode_Object_Group')
        group_node.label = "Default Group"
        
        current_x = 0
        current_y = 0
        y_gap = 200
        
        count = 0
        
        if 'workspace_collection' in locals() and workspace_collection:
             target_objects = workspace_collection.objects
        else:
             target_objects = []

        if not target_objects:
             print("Warning: Could not find Workspace collection to generate blueprint nodes.")

        min_y = 0

        for draw_ib_pair in draw_ib_pair_list:
            draw_ib = draw_ib_pair.DrawIB
            alias_name = draw_ib_pair.AliasName
            
            found_objs = [obj for obj in target_objects if obj.name.startswith(draw_ib)]
            
            for obj in found_objs:
                 if obj.type == 'MESH':
                    node = tree.nodes.new('SSMTNode_Object_Info')
                    node.location = (current_x, current_y)
                    
                    node.object_name = obj.name
                    node.draw_ib = draw_ib
                    
                    name_parts = obj.name.split('-')
                    if len(name_parts) >= 2:
                        node.component = name_parts[1]
                    else:
                        node.component = "1"

                    node.alias_name = alias_name
                        
                    node.label = obj.name

                    if group_node.inputs[-1].is_linked:
                        group_node.inputs.new('SSMTSocketObject', f"Input {len(group_node.inputs) + 1}")
                    
                    tree.links.new(node.outputs[0], group_node.inputs[-1])
                    
                    count += 1
                    current_y -= y_gap
                    min_y = min(min_y, current_y)

        
        final_center_y = min_y / 2 if count <= 5 else -200
        
        group_node.location = (current_x + 400, final_center_y)

        output_node = tree.nodes.new('SSMTNode_Result_Output')
        output_node.location = (current_x + 800, final_center_y)
        output_node.label = "Generate Mod"
        
        if len(output_node.inputs) > 0 and len(group_node.outputs) > 0:
            tree.links.new(group_node.outputs[0], output_node.inputs[0])

        if hasattr(group_node, "update"):
             group_node.update()

        print(f"Blueprint {tree_name} updated with imported objects.")
        
    except Exception as e:
        print(f"Error generating blueprint nodes: {e}")
        import traceback
        traceback.print_exc()
    
    refresh_workspace_cache()
    
    return imported_count


def ImprotFromWorkSpaceSSMTBlueprint(self, context):
    '''
    根据 SSMT4 开关选择不同的导入逻辑
    当开启SSMT4时，首先尝试第四代导入，如果失败则回退到第三代
    '''
    if Properties_ImportModel.use_ssmt4():
        print("SSMT4模式: 尝试使用第四代导入逻辑...")
        imported_count = ImportFromWorkSpaceSSMT4(self, context)
        
        if imported_count == 0:
            print("SSMT4模式: 第四代导入未成功导入任何模型，尝试回退到第三代导入逻辑...")
            self.report({'WARNING'}, "第四代导入未成功，尝试回退到第三代导入逻辑...")
            imported_count = ImprotFromWorkSpaceSSMT3(self, context)
            
            if imported_count > 0:
                self.report({'INFO'}, f"成功使用第三代导入逻辑导入了 {imported_count} 个模型")
            else:
                self.report({'ERROR'}, "第四代和第三代导入均未成功导入任何模型")
        else:
            self.report({'INFO'}, f"成功使用第四代导入逻辑导入了 {imported_count} 个模型")
    else:
        ImprotFromWorkSpaceSSMT3(self, context)


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
            TimerUtils.Start("ImportFromWorkSpaceBlueprint")
            ImprotFromWorkSpaceSSMTBlueprint(self,context)
            TimerUtils.End("ImportFromWorkSpaceBlueprint")
        
        return {'FINISHED'}
    

def register():
    bpy.utils.register_class(SSMTImportAllFromCurrentWorkSpaceBlueprint)


def unregister():
    bpy.utils.unregister_class(SSMTImportAllFromCurrentWorkSpaceBlueprint)



