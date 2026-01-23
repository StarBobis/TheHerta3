import os
import struct
import numpy

from ..config.main_config import GlobalConfig


class BufferExportHelper:
    '''
    工具类
    专门负责把ObjBufferModel中的数据写入到文件中

    这个类专门用在生成Mod时调用
    我们规定生成的Mod文件夹结构如下:

    文件夹: Mod_工作空间名称
    - 文件夹: Buffer                    存放所有二进制缓冲区文件,包括IB和VB文件
    - 文件夹: Texture                   存放所有贴图文件
    - 文件:   工作空间名称.ini           所有ini内容要全部写在一起,如果写在多个ini里面通过namespace关联,则可能会导致Mod开启或关闭时有一瞬间的上贴图延迟
    '''

    @staticmethod
    def write_category_buffer_files(category_buffer_dict:dict, draw_ib:str):
        # 直接遍历 OrderedCategoryNameList 进行写出，保持了顺序和筛选逻辑
        for category_name,category_buf in category_buffer_dict.items():
            buf_path = GlobalConfig.path_generatemod_buffer_folder() + draw_ib + "-" + category_name + ".buf"
            with open(buf_path, 'wb') as ibf:
                category_buf.tofile(ibf)

    @staticmethod
    def write_buf_ib_r32_uint(index_list:list[int],buf_file_name:str):
        ib_path = os.path.join(GlobalConfig.path_generatemod_buffer_folder(), buf_file_name)
        packed_data = struct.pack(f'<{len(index_list)}I', *index_list)
        with open(ib_path, 'wb') as ibf:
            ibf.write(packed_data) 

    @staticmethod
    def write_buf_shapekey_offsets(shapekey_offsets,filename:str):
        with open(GlobalConfig.path_generatemod_buffer_folder() + filename, 'wb') as file:
            for number in shapekey_offsets:
                # 假设数字是32位整数，使用'i'格式符
                # 根据实际需要调整数字格式和相应的格式符
                data = struct.pack('i', number)
                file.write(data)

    @staticmethod
    def write_buf_shapekey_vertex_ids(shapekey_vertex_ids,filename:str):
        with open(GlobalConfig.path_generatemod_buffer_folder() + filename, 'wb') as file:
            for number in shapekey_vertex_ids:
                # 假设数字是32位整数，使用'i'格式符
                # 根据实际需要调整数字格式和相应的格式符
                data = struct.pack('i', number)
                file.write(data)
                
    @staticmethod
    def write_buf_shapekey_vertex_offsets(shapekey_vertex_offsets,filename:str):
        # 将列表转换为numpy数组
        float_array = numpy.array(shapekey_vertex_offsets, dtype=numpy.float32)
        # 改变数据类型为float16
        float_array = float_array.astype(numpy.float16)
        with open(GlobalConfig.path_generatemod_buffer_folder() + filename, 'wb') as file:
            float_array.tofile(file)

    @staticmethod
    def write_buf_blendindices_uint16(blendindices, filename: str):
        """
        Write BLENDINDICES array to disk as uint16 values.

        `blendindices` may be a numpy array of shape (loops,) or (loops, N)
        or a Python sequence. This function will convert/cast it to
        uint16 and write the raw bytes to the buffer folder.
        """
        arr = numpy.asarray(blendindices)

        # If structured dtype, try to view first field
        if arr.dtype.names:
            # pick first named field
            arr = arr[arr.dtype.names[0]]

        # Ensure numeric integer shape: flatten rows if 2D
        if arr.ndim > 1:
            arr_to_write = arr.reshape(-1)
        else:
            arr_to_write = arr

        # Cast to uint16 (safe truncation assumed per format expectations)
        arr_uint16 = arr_to_write.astype(numpy.uint16)

        out_path = os.path.join(GlobalConfig.path_generatemod_buffer_folder(), filename)
        # Ensure directory exists
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        with open(out_path, 'wb') as f:
            arr_uint16.tofile(f)
