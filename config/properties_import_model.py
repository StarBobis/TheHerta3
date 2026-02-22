import bpy
import os

class Properties_ImportModel(bpy.types.PropertyGroup):

    '''
    TODO 关于非镜像工作流，我突然有了新的灵感
    那就是在导入时，通过把Scale的X分量设为-1并应用，来让模型不镜像
    在导出时，把Scale的X分量再设为-1并应用，让模型镜像回来
    这样就避免了底层数据结构的操作，非常优雅，且后续基本上就应该这么做

    所以暂时删掉所有旧的非镜像工作流代码，等待后续测试

    '''
    use_mirror_workflow: bpy.props.BoolProperty(
        name="使用非镜像工作流",
        description="默认为False, 启用后导入和导出模型将不再是镜像的，目前3Dmigoto的模型导入后是镜像存粹是由于历史遗留问题是错误的，但是当错误积累成粑粑山，人的习惯和旧的工程很难被改变，所以只有勾选后才能使用非镜像工作流",
        default=False,
    ) # type: ignore

    @classmethod
    def use_mirror_workflow(cls):
        '''
        bpy.context.scene.properties_import_model.use_mirror_workflow
        '''
        return bpy.context.scene.properties_import_model.use_mirror_workflow

    use_parallel_export: bpy.props.BoolProperty(
        name="启用并行导出",
        description="启用多进程并行导出，可显著提升大量物体时的导出速度。需要保存项目文件后才能使用。",
        default=False,
    ) # type: ignore

    parallel_worker_count: bpy.props.IntProperty(
        name="并行进程数",
        description="并行导出时使用的工作进程数量，默认为 CPU 核心数 - 1",
        default=0,
        min=1,
        max=32,
    ) # type: ignore

    blender_executable_path: bpy.props.StringProperty(
        name="Blender路径",
        description="Blender可执行文件路径，用于并行预处理。留空则自动检测",
        default="",
        subtype='FILE_PATH',
    ) # type: ignore

    @classmethod
    def use_parallel_export(cls):
        '''
        bpy.context.scene.properties_import_model.use_parallel_export
        '''
        return bpy.context.scene.properties_import_model.use_parallel_export

    @classmethod
    def get_parallel_worker_count(cls):
        '''
        获取并行工作进程数量
        最大限制为 CPU 核心数的一半，防止系统卡顿
        '''
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        max_allowed = max(1, cpu_count // 2)
        
        count = bpy.context.scene.properties_import_model.parallel_worker_count
        if count <= 0:
            count = max_allowed
        else:
            count = min(count, max_allowed)
        
        return count
    
    @classmethod
    def get_max_parallel_worker_count(cls):
        '''
        获取允许的最大并行工作进程数量（CPU核心数的一半）
        '''
        import multiprocessing
        cpu_count = multiprocessing.cpu_count()
        return max(1, cpu_count // 2)

    @classmethod
    def get_blender_executable_path(cls):
        '''
        获取 Blender 可执行文件路径
        '''
        path = bpy.context.scene.properties_import_model.blender_executable_path
        if path and os.path.exists(path):
            return path
        return None

    use_normal_map: bpy.props.BoolProperty(
        name="自动上贴图时使用法线贴图",
        description="启用后在导入模型时自动附加法线贴图节点, 在材质预览模式下得到略微更好的视觉效果",
        default=False,
    )  # type: ignore

    @classmethod
    def use_normal_map(cls):
        '''
        bpy.context.scene.properties_import_model.use_normal_map
        '''
        return bpy.context.scene.properties_import_model.use_normal_map

def register():
    bpy.utils.register_class(Properties_ImportModel)
    bpy.types.Scene.properties_import_model = bpy.props.PointerProperty(type=Properties_ImportModel)

def unregister():
    del bpy.types.Scene.properties_import_model
    bpy.utils.unregister_class(Properties_ImportModel)

