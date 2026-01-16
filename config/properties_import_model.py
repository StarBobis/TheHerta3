import bpy

class Properties_ImportModel(bpy.types.PropertyGroup):

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

