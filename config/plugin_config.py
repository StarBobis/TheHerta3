# 配置类，独立于主模块
class PluginConfig:
    _bl_info = None
    
    @classmethod
    def set_bl_info(cls, info):
        cls._bl_info = info
    
    @classmethod
    def get_bl_info(cls):
        return cls._bl_info
    
    @classmethod
    def get_version_string(cls) -> str:
        if cls._bl_info and "version" in cls._bl_info:
            version = cls._bl_info["version"]
            return f"{version[0]}.{version[1]}.{version[2]}"
        return "未知"
    

