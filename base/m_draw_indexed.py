from dataclasses import dataclass, field


class M_DrawIndexed:
    def __init__(self) -> None:
        self.DrawNumber = ""

        # 绘制起始位置
        self.DrawOffsetIndex = "" 

        self.DrawStartIndex = "0"

        # 代表一个obj具体的draw_indexed
        self.AliasName = "" 

        # 代表这个obj的顶点数
        self.UniqueVertexCount = 0 
    
    def get_draw_str(self) ->str:
        return "drawindexed = " + self.DrawNumber + "," + self.DrawOffsetIndex +  "," + self.DrawStartIndex
  
@dataclass
class M_DrawIndexedInstanced:
    '''
    https://learn.microsoft.com/en-us/windows/win32/api/d3d11/nf-d3d11-id3d11devicecontext-drawindexedinstanced
    '''

    # Number of indices read from the index buffer for each instance.
    # 每个Instance绘制的索引数
    IndexCountPerInstance:int = field(init=False,repr=False,default=0)

    # Number of instances to draw.
    # 绘制几个Instance，一般用3Dmigoto默认的INSTANCE_COUNT即可，除非你需要绘制特定数量的Instance
    InstanceCount:int = field(init=False,repr=False,default=0)

    # The location of the first index read by the GPU from the index buffer.
    # 绘制起始索引偏移
    StartIndexLocation:int = field(init=False,repr=False,default=0)

    # A value added to each index before reading a vertex from the vertex buffer.
    # 一般情况下都为0
    BaseVertexLocation:int = field(init=False,repr=False,default=0)

    # 一般无需关注，用3Dmigoto默认的FIRST_INSTANCE即可，除非你需要从特定Instance开始绘制
    # A value added to each index before reading per-instance data from a vertex buffer.
    StartInstanceLocation:int = field(init=False,repr=False,default=0)

    def get_draw_str(self) ->str:

        draw_str = "drawindexedinstanced = "
        draw_str += str(self.IndexCountPerInstance) + ","

        # 一般使用默认值INSTANCE_COUNT
        if self.InstanceCount == 0:
            draw_str += "INSTANCE_COUNT,"
        else:
            draw_str += str(self.InstanceCount) + ","

        draw_str += str(self.StartIndexLocation) + ","      

        draw_str += str(self.BaseVertexLocation) + ","

        # 一般使用默认值FIRST_INSTANCE
        if self.StartInstanceLocation == 0:
            draw_str += "FIRST_INSTANCE"
        else:
            draw_str += str(self.StartInstanceLocation)
        return draw_str
