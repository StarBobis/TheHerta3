from ..base.d3d11_element import D3D11Element
from ..utils.format_utils import FormatUtils
import numpy

class FMTFile:
    def __init__(self, fmt_file_path:str):
        self.stride = 0
        self.topology = ""
        self.format = ""
        self.gametypename = ""
        self.prefix = ""
        self.scale = "1.0"
        self.rotate_angle:bool = False
        self.rotate_angle_x:float = 0
        self.rotate_angle_y:float = 0
        self.rotate_angle_z:float = 0
        self.flip_face_orientation:bool = False
        self.apply_rotation_transformation:bool = False

        self.elements:list[D3D11Element] = []

        with open(fmt_file_path, 'r') as file:
            lines = file.readlines()

        element_info = {}
        for line in lines:
            parts = line.strip().split(":")
            if len(parts) < 2:
                continue  # 跳过格式不正确的行

            key, value = parts[0].strip(), ":".join(parts[1:]).strip()
            if key == "stride":
                self.stride = int(value)
            elif key == "topology":
                self.topology = value
            elif key == "format":
                self.format = value
            elif key == "gametypename":
                self.gametypename = value
            elif key == "prefix":
                self.prefix = value
            elif key == "scale":
                self.scale = value
            elif key == "rotate_angle":
                self.rotate_angle = value.lower() == "true"
            elif key == "rotate_angle_x":
                self.rotate_angle_x = float(value)
            elif key == "rotate_angle_y":
                self.rotate_angle_y = float(value)
            elif key == "rotate_angle_z":
                self.rotate_angle_z = float(value)
            
            elif key == "flip_face_orientation":
                self.flip_face_orientation = value.lower() == "true"
            elif key == "apply_rotation_transformation":
                self.apply_rotation_transformation = value.lower() == "true"

            elif key.startswith("element"):
                # 处理element块
                if "SemanticName" in element_info:
                    append_d3delement = D3D11Element(
                        SemanticName=element_info["SemanticName"], SemanticIndex=int(element_info["SemanticIndex"]),
                        Format= element_info["Format"],AlignedByteOffset= int(element_info["AlignedByteOffset"]),
                        ByteWidth=0,
                        ExtractSlot="0",ExtractTechnique="",Category="")
                    
                    if "ByteWidth" in element_info:
                        # print("读取到ByteWidth存在: " + element_info["ByteWidth"])
                        append_d3delement.ByteWidth = int(element_info["ByteWidth"])
                    else:
                        append_d3delement.ByteWidth = FormatUtils.format_size(append_d3delement.Format)
                    
                    # 如果已经有一个element信息，则先添加到列表中
                    self.elements.append(append_d3delement)
                    element_info.clear()  # 清空当前element信息

                # 将新的element属性添加到element_info字典中
                element_info[key.split()[0]] = value
            elif key in ["SemanticName", "SemanticIndex", "Format","ByteWidth", "InputSlot", "AlignedByteOffset", "InputSlotClass", "InstanceDataStepRate"]:
                element_info[key] = value

        # 添加最后一个element
        if "SemanticName" in element_info:
            append_d3delement = D3D11Element(
                SemanticName=element_info["SemanticName"], SemanticIndex=int(element_info["SemanticIndex"]),
                Format= element_info["Format"],AlignedByteOffset= int(element_info["AlignedByteOffset"]),
                ByteWidth=0,
                ExtractSlot="0",ExtractTechnique="",Category=""
            )

            if "ByteWidth" in element_info:
                # print("读取到ByteWidth存在: " + element_info["ByteWidth"])
                append_d3delement.ByteWidth = int(element_info["ByteWidth"])
            else:
                append_d3delement.ByteWidth = FormatUtils.format_size(append_d3delement.Format)

            self.elements.append(append_d3delement)

    def __repr__(self):
        return (f"FMTFile(stride={self.stride}, topology='{self.topology}', format='{self.format}', "
                f"gametypename='{self.gametypename}', prefix='{self.prefix}', elements={self.elements})")
    
    def get_dtype(self):
        fields = []
        for elemnt in self.elements:
            # Numpy类型由Format决定，此时即使是WWMI的特殊R8_UINT也能得到正确的numpy.uint8
            numpy_type = FormatUtils.get_nptype_from_format(elemnt.Format)
            
            # 这里我们用ByteWidth / numpy_type.itemsize 得到总的维度数量，也就是列数
            # XXX 注意这里计算出正常Size的前提是numpy_type确定是对应真实的字节数，且ByteWidth正确，也就是数据类型必须完全正确。
            size = int( elemnt.ByteWidth / numpy.dtype(numpy_type).itemsize)

            # print("element: "+ elemnt.ElementName)
            # print(numpy_type)
            # print(size)
            fields.append((elemnt.ElementName,numpy_type , size))
        dtype = numpy.dtype(fields)
        return dtype