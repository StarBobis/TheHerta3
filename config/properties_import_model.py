import bpy

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

