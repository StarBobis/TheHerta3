import re
import numpy
import struct
import math
import numpy


# This used to catch any exception in run time and raise it to blender output console.
class Fatal(Exception):
    pass


class FormatUtils:
    f32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_FLOAT''')
    f16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_FLOAT''')
    u32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_UINT''')
    u16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_UINT''')
    u8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_UINT''')
    s32_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]32)+_SINT''')
    s16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_SINT''')
    s8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_SINT''')
    unorm16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_UNORM''')
    unorm8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_UNORM''')
    snorm16_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]16)+_SNORM''')
    snorm8_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD]8)+_SNORM''')

    misc_float_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD][0-9]+)+_(?:FLOAT|UNORM|SNORM)''')
    misc_int_pattern = re.compile(r'''(?:DXGI_FORMAT_)?(?:[RGBAD][0-9]+)+_[SU]INT''')

    components_pattern = re.compile(r'''(?<![0-9])[0-9]+(?![0-9])''')

    @classmethod
    def get_nptype_from_format(cls,fmt):
        '''
        解析DXGI Format字符串，返回numpy的数据类型
        '''
        if cls.f32_pattern.match(fmt):
            return numpy.float32
        elif cls.f16_pattern.match(fmt):
            return numpy.float16
        elif cls.u32_pattern.match(fmt):
            return numpy.uint32
        elif cls.u16_pattern.match(fmt):
            return numpy.uint16
        elif cls.u8_pattern.match(fmt):
            return numpy.uint8
        elif cls.s32_pattern.match(fmt):
            return numpy.int32
        elif cls.s16_pattern.match(fmt):
            return numpy.int16
        elif cls.s8_pattern.match(fmt):
            return numpy.int8

        elif cls.unorm16_pattern.match(fmt):
            return numpy.uint16
        elif cls.unorm8_pattern.match(fmt):
            return numpy.uint8
        elif cls.snorm16_pattern.match(fmt):
            return numpy.int16
        elif cls.snorm8_pattern.match(fmt):
            return numpy.int8

        raise Fatal('Mesh uses an unsupported DXGI Format: %s' % fmt)

    @classmethod
    def EncoderDecoder(cls,fmt):
        '''
        转换效率极低，不建议使用
        有条件还是调用numpy的astype方法

        奶奶滴，不经过这一层转换还不行呢，不转换数据是错的。
        '''
        if cls.f32_pattern.match(fmt):
            return (lambda data: b''.join(struct.pack('<f', x) for x in data),
                    lambda data: numpy.frombuffer(data, numpy.float32).tolist())
        if cls.f16_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.float16).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.float16).tolist())
        if cls.u32_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.uint32).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.uint32).tolist())
        if cls.u16_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.uint16).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.uint16).tolist())
        if cls.u8_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.uint8).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.uint8).tolist())
        if cls.s32_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.int32).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.int32).tolist())
        if cls.s16_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.int16).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.int16).tolist())
        if cls.s8_pattern.match(fmt):
            return (lambda data: numpy.fromiter(data, numpy.int8).tobytes(),
                    lambda data: numpy.frombuffer(data, numpy.int8).tolist())

        if cls.unorm16_pattern.match(fmt):
            return (
                lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 65535.0)).astype(numpy.uint16).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.uint16) / 65535.0).tolist())
        if cls.unorm8_pattern.match(fmt):
            return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 255.0)).astype(numpy.uint8).tobytes(),
                    lambda data: (numpy.frombuffer(data, numpy.uint8) / 255.0).tolist())
        if cls.snorm16_pattern.match(fmt):
            return (
                lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 32767.0)).astype(numpy.int16).tobytes(),
                lambda data: (numpy.frombuffer(data, numpy.int16) / 32767.0).tolist())
        if cls.snorm8_pattern.match(fmt):
            return (lambda data: numpy.around((numpy.fromiter(data, numpy.float32) * 127.0)).astype(numpy.int8).tobytes(),
                    lambda data: (numpy.frombuffer(data, numpy.int8) / 127.0).tolist())
        # print(fmt)
        raise Fatal('File uses an unsupported DXGI Format: %s' % fmt)
    
    @classmethod
    def apply_format_conversion(cls, data, fmt):
        '''
        从指定格式导入时必须经过转换，否则丢失精度。
        '''
        if cls.unorm16_pattern.match(fmt):
            decode_func = lambda x: (x / 65535.0).astype(numpy.float32)
        elif cls.unorm8_pattern.match(fmt):
            decode_func = lambda x: (x / 255.0).astype(numpy.float32)
        elif cls.snorm16_pattern.match(fmt):
            decode_func = lambda x: (x / 32767.0).astype(numpy.float32)
        elif cls.snorm8_pattern.match(fmt):
            decode_func = lambda x: (x / 127.0).astype(numpy.float32)
        else:
            return data  # 如果格式不在这四个里面的任意一个，则直接返回原始数据

        # 对输入数据应用转换
        decoded_data = decode_func(data)
        return decoded_data

    @classmethod
    def format_size(cls,fmt):
        '''
        输入FORMAT返回该FORMAT的字节数
        例如输入R32G32B32_FLOAT 返回字节数：12

        XXX 注意这里的结果并不可靠，应该在数据类型中定义正确的ByteWidth，而不是调用这里，这里仅用于兼容古董架构的fmt文件。
        这里的东西将在未来被移除，但可能会持续存在很长一段时间。
        '''
        matches = cls.components_pattern.findall(fmt)
        return sum(map(int, matches)) // 8


    '''
    用于各种二进制数据格式转换
    '''
    # 向量归一化
    @classmethod
    def vector_normalize(cls,v):
        """归一化向量"""
        length = math.sqrt(sum(x * x for x in v))
        if length == 0:
            return v  # 避免除以零
        return [x / length for x in v]
    
    @classmethod
    def add_and_normalize_vectors(cls,v1, v2):
        """将两个向量相加并规范化(normalize)"""
        # 相加
        result = [a + b for a, b in zip(v1, v2)]
        # 归一化
        normalized_result = cls.vector_normalize(result)
        return normalized_result
    
    # 辅助函数：计算两个向量的点积
    @classmethod
    def dot_product(cls,v1, v2):
        return sum(a * b for a, b in zip(v1, v2))


    @classmethod
    def convert_2x_float32_to_r16g16_unorm(cls, input_array):
        """
        把 shape=(…,2) 的 float32 [0,1] 区间量
        量化成 uint16 [0,65535] 并返回同样 shape 的 uint16 数组。
        如果 input 是一维的，也会按元素逐个量化。
        """
        # 先拷贝，避免原地修改
        arr = numpy.asarray(input_array, dtype=numpy.float32)
        # 钳位到 [0,1]
        numpy.clip(arr, 0.0, 1.0, out=arr)
        # 量化：65535 是 R16G16_UNORM 的最大值
        return numpy.round(arr * 65535).astype(numpy.uint16)

    '''
    这四个UNORM和SNORM比较特殊需要这样处理，其它float类型转换直接astype就行
    '''
    # @classmethod
    # def convert_4x_float32_to_r8g8b8a8_snorm(cls, input_array):
    #     return numpy.round(input_array * 127).astype(numpy.int8)

    @classmethod
    def convert_4x_float32_to_r8g8b8a8_snorm(cls, input_array):
        '''
        这里听了DeepSeek的建议改成这样了，也许可以避免某些问题
        '''
        arr = numpy.asarray(input_array, dtype=numpy.float32)
        # 1. 钳位到 [-1, 1]
        numpy.clip(arr, -1.0, 1.0, out=arr)
        # 2. 量化到 [-127, 127]
        arr = numpy.round(arr * 127).astype(numpy.int8)
        # 3. 确保不出现 -128（理论上 clip+round 后已不可能，但再保险一次）
        #    其实可省略，因为 -1.0*-127=127, 1.0*127=127，已覆盖不到 -128
        return arr

    @classmethod
    def convert_4x_float32_to_r8g8b8a8_unorm(cls,input_array):
        return numpy.round(input_array * 255).astype(numpy.uint8)
    
    @classmethod
    def convert_4x_float32_to_r16g16b16a16_snorm(cls,input_array):
        return numpy.round(input_array * 32767).astype(numpy.int16)
    
    @classmethod
    def convert_4x_float32_to_r16g16b16a16_unorm(cls, input_array):
        return numpy.round(input_array * 65535).astype(numpy.uint16)
    
    @classmethod
    def convert_4x_float32_to_r16g16b16a16_snorm(cls, input_array):
        return numpy.round(input_array * 32767).astype(numpy.int16)
    
    @classmethod    
    def convert_normals_to_endfield_octahedral_r32_uint(cls, input_normals):
        """
        Compress float3 normals to Endfield specific R32_UINT octahedral format.
        输入: (N, 3) float32 normals
        输出: (N,) uint32 packed data
        """
        # Ensure input is float32
        # n is reference, we copy to avoid modifying original info
        n = numpy.array(input_normals, dtype=numpy.float32)
        
        # 1. L1 Normalize
        # Avoid division by zero
        l1_norm = numpy.abs(n[:, 0]) + numpy.abs(n[:, 1]) + numpy.abs(n[:, 2])
        l1_norm = numpy.where(l1_norm == 0, 1.0, l1_norm) 
        
        n /= l1_norm[:, numpy.newaxis]
        
        x = n[:, 0]
        y = n[:, 1]
        z = n[:, 2]
        
        # 2. Octahedral wrap for z < 0
        neg_z = z < 0
        
        # sign(x) : 1 if x >= 0 else -1
        sign_x = numpy.where(x >= 0, 1.0, -1.0)
        sign_y = numpy.where(y >= 0, 1.0, -1.0)
        
        # tx = (1 - abs(y)) * sign(x)
        # ty = (1 - abs(x)) * sign(y)
        tx = (1.0 - numpy.abs(y)) * sign_x
        ty = (1.0 - numpy.abs(x)) * sign_y
        
        x = numpy.where(neg_z, tx, x)
        y = numpy.where(neg_z, ty, y)
        
        # 3. Quantize to [-511, 511] (Based on scale 0.00195694715 ~= 1/511)
        # However, 10-bit signed range [-512, 511]. 
        scale = 511.0
        
        xq = numpy.round(x * scale).astype(numpy.int32)
        yq = numpy.round(y * scale).astype(numpy.int32)
        
        # Clamp to 10-bit signed range [-512, 511]
        xq = numpy.clip(xq, -512, 511)
        yq = numpy.clip(yq, -512, 511)
        
        # 4. Bit packing
        # Convert to 10-bit uint representation (Two's complement logic is handled by & 0x3FF)
        xu = xq & 0x3FF
        yu = yq & 0x3FF
        
        # Shift Y by 10, X at lowest
        # HLSL: r0.y (X) = raw & 1023
        # HLSL: raw >> 10 (Y) & 1023
        packed = xu | (yu << 10)

        # Critical: Set Bit 30 (0x40000000) to 1 to enable decompression in shader
        # Shader logic: r0.xy = (int2)v2.xx & int2(0x40000000,1023);
        #               r0.x = cmp(0 < (uint)r0.x); -> Checks bit 30
        #               r0.xyz = r0.xxx ? r0.yzw (decompressed) : v2.xyz;
        packed |= 0x40000000
        
        # Result is uint32
        return packed.astype(numpy.uint32)

    @classmethod    
    def convert_4x_float32_to_r8g8b8a8_unorm_blendweights(cls, input_array):
        # 确保输入数组是浮点类型
        # input_array_float = input_array.astype(numpy.float32)
    
        # 创建结果数组
        result = numpy.zeros_like(input_array, dtype=numpy.uint8)
        
        # 处理NaN值
        nan_mask = numpy.isnan(input_array).any(axis=1)
        valid_mask = ~nan_mask
        
        # 只处理非NaN行
        valid_input = input_array[valid_mask]
        if valid_input.size == 0:
            return result
        
        # 计算每行总和
        row_sums = valid_input.sum(axis=1, keepdims=True)
        
        # 处理零和行
        zero_sum_mask = (row_sums[:, 0] == 0)
        non_zero_mask = ~zero_sum_mask
        
        # 归一化权重
        normalized = numpy.zeros_like(valid_input)
        normalized[non_zero_mask] = valid_input[non_zero_mask] / row_sums[non_zero_mask] * 255.0
        
        # 计算整数部分和小数部分
        int_part = numpy.floor(normalized).astype(numpy.int32)
        fractional = normalized - int_part
        
        # 设置小于1的权重为0
        small_weight_mask = (normalized < 1) & non_zero_mask[:, numpy.newaxis]
        int_part[small_weight_mask] = 0
        fractional[small_weight_mask] = 0
        
        # 计算精度误差
        precision_error = 255 - int_part.sum(axis=1)
        
        # 计算tickets
        tickets = numpy.zeros_like(normalized)
        with numpy.errstate(divide='ignore', invalid='ignore'):
            tickets[non_zero_mask] = numpy.where(
                (normalized[non_zero_mask] >= 1) & (fractional[non_zero_mask] > 0),
                255 * fractional[non_zero_mask] / normalized[non_zero_mask],
                0
            )
        
        # 分配精度误差
        output = int_part.copy()
        for i in range(precision_error.max()):
            # 找出需要分配的行
            need_allocation = (precision_error > 0)
            if not numpy.any(need_allocation):
                break
            
            # 找出当前行中ticket最大的位置
            max_ticket_mask = numpy.zeros_like(tickets, dtype=bool)
            rows = numpy.where(need_allocation)[0]
            
            # 对于有ticket的行
            has_ticket = (tickets[rows] > 0).any(axis=1)
            if numpy.any(has_ticket):
                ticket_rows = rows[has_ticket]
                row_indices = ticket_rows[:, numpy.newaxis]
                col_indices = tickets[ticket_rows].argmax(axis=1)
                max_ticket_mask[ticket_rows, col_indices] = True
                tickets[ticket_rows, col_indices] = 0
            
            # 对于没有ticket的行
            no_ticket = ~has_ticket & need_allocation[rows]
            if numpy.any(no_ticket):
                no_ticket_rows = rows[no_ticket]
                # 找出当前权重最大的位置
                max_weight_mask = numpy.zeros_like(tickets, dtype=bool)
                row_indices = no_ticket_rows[:, numpy.newaxis]
                col_indices = output[no_ticket_rows].argmax(axis=1)
                max_weight_mask[no_ticket_rows, col_indices] = True
                max_ticket_mask |= max_weight_mask
            
            # 应用分配
            output[max_ticket_mask] += 1
            precision_error[need_allocation] -= 1
        
        # 将结果存回
        result[valid_mask] = output.astype(numpy.uint8)
        return result
    
    @classmethod
    def convert_4x_float32_to_r8g8b8a8_unorm_blendweights_bk2(cls, input_array):

        result = numpy.zeros_like(input_array, dtype=numpy.uint8)

        for i in range(input_array.shape[0]):
            weights = input_array[i]

            # 如果权重含有NaN值，则将该行的所有值设置为0。
            # 因为权重只要是被刷过，就不会出现NaN值。
            find_nan = False
            for w in weights:
                if math.isnan(w):
                    row_normalized = [0, 0, 0, 0]
                    result[i] = numpy.array(row_normalized, dtype=numpy.uint8)
                    find_nan = True
                    break
                    # print(weights)
                    # raise Fatal("NaN found in weights")
            if find_nan:
                continue
            
            total = sum(weights)
            if total == 0:
                row_normalized = [0] * len(weights)
                result[i] = numpy.array(row_normalized, dtype=numpy.uint8)
                continue

            precision_error = 255

            tickets = [0] * len(weights)
            normalized_weights = [0] * len(weights)

            for index, weight in enumerate(weights):
                # Ignore zero weight
                if weight == 0:
                    continue

                weight = weight / total * 255
                # Ignore weight below minimal precision (1/255)
                if weight < 1:
                    normalized_weights[index] = 0
                    continue

                # Strip float part from the weight
                int_weight = 0

                int_weight = int(weight)

                normalized_weights[index] = int_weight
                # Reduce precision_error by the integer weight value
                precision_error -= int_weight
                # Calculate weight 'significance' index to prioritize lower weights with float loss
                tickets[index] = 255 / weight * (weight - int_weight)

            while precision_error > 0:
                ticket = max(tickets)
                if ticket > 0:
                    # Route `1` from precision_error to weights with non-zero ticket value first
                    idx = tickets.index(ticket)
                    tickets[idx] = 0
                else:
                    # Route remaining precision_error to highest weight to reduce its impact
                    idx = normalized_weights.index(max(normalized_weights))
                # Distribute `1` from precision_error
                normalized_weights[idx] += 1
                precision_error -= 1

            row_normalized = normalized_weights
            result[i] = numpy.array(row_normalized, dtype=numpy.uint8)
        return result


