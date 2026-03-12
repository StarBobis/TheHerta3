import numpy
from typing import Tuple, Optional


class TBNCodec:
    """
    10-10-10-2 TBN (Tangent-Bitangent-Normal) 编解码器
    用于 EFMI/AEMI 格式的八面体法线压缩
    
    数据格式 (R10G10B10A2_UINT):
    - X (10-bit): 八面体编码的法线 X 分量
    - Y (10-bit): 八面体编码的法线 Y 分量  
    - Z (10-bit): 编码的切线角度
    - W (2-bit): 标志位 - bit30 为打包标志, bit31 为副切线符号
    """

    @staticmethod
    def oct_decode_vector(data: numpy.ndarray) -> numpy.ndarray:
        """
        八面体解码: 将 2D 编码向量 (x,y) 解码为 3D 法线 (x,y,z)
        
        Args:
            data: shape (N, 2) 的 float32 数组, 范围约 [-1, 1]
            
        Returns:
            shape (N, 3) 的 float32 单位法线向量
        """
        assert data.ndim == 2 and data.shape[1] == 2, 'Array must be 2D with shape (N, 2)'
        x, y = data.T

        z = 1.0 - numpy.abs(x) - numpy.abs(y)
        mask = z < 0.0

        old_xf = x.copy()
        x[mask] = (1.0 - numpy.abs(y[mask])) * numpy.sign(old_xf[mask])
        y[mask] = (1.0 - numpy.abs(old_xf[mask])) * numpy.sign(y[mask])

        data = numpy.stack([x, y, z], axis=1)
        data /= numpy.linalg.norm(data, axis=1, keepdims=True).clip(1e-8)

        return data

    @staticmethod
    def oct_encode_vector(normals: numpy.ndarray) -> numpy.ndarray:
        """
        八面体编码: 将 3D 法线 (x,y,z) 编码为 2D 向量 (x,y)
        
        Args:
            normals: shape (N, 3) 的 float32 法线向量
            
        Returns:
            shape (N, 2) 的 float32 编码向量
        """
        n = normals / numpy.linalg.norm(normals, axis=1, keepdims=True).clip(1e-8)

        inv_l1 = 1.0 / numpy.sum(numpy.abs(n), axis=1, keepdims=True)
        n *= inv_l1

        mask = n[:, 2] < 0
        n_fold = n.copy()
        n_fold[mask, 0] = (1.0 - numpy.abs(n[mask, 1])) * numpy.sign(n[mask, 0])
        n_fold[mask, 1] = (1.0 - numpy.abs(n[mask, 0])) * numpy.sign(n[mask, 1])

        return n_fold[:, :2]

    @staticmethod
    def decode_10_10_10_2(data: numpy.ndarray) -> numpy.ndarray:
        """
        解包 10-10-10-2 编码的 uint32 数据
        
        Args:
            data: shape (N,) 的 uint32 数组
            
        Returns:
            shape (N, 5) 的 float32 数组: [x, y, z, packed_flag, sign_flag]
        """
        assert data.ndim == 1, 'Array for 10-10-10-2 decoding must be 1D'
        assert data.dtype == numpy.uint32, 'Array for 10-10-10-2 decoding must have dtype uint32'

        x = data & 0x3FF
        y = (data >> 10) & 0x3FF
        z = (data >> 20) & 0x3FF

        def sign_extend_10bit(v):
            v = v.astype(numpy.int32)
            return numpy.where(v >= 512, v - 1024, v)

        x_s, y_s, z_s = sign_extend_10bit(x), sign_extend_10bit(y), sign_extend_10bit(z)

        scale = 1.0 / 511.0

        bit_30 = numpy.where((data >> 30) & 1, 1, 0)
        bit_31 = numpy.where((data >> 31) & 1, 1, 0)

        decoded = numpy.stack([x_s * scale, y_s * scale, z_s * scale, bit_30, bit_31], axis=1)

        return decoded

    @staticmethod
    def encode_10_10_10_2(data: numpy.ndarray) -> numpy.ndarray:
        """
        打包 3 个浮点数和 2 个布尔值为 10-10-10-2 编码的 uint32
        
        Args:
            data: shape (N, 5) 的 float32 数组: [x, y, z, packed_flag, sign_flag]
            
        Returns:
            shape (N,) 的 uint32 数组
        """
        assert data.ndim == 2, 'Array for 10-10-10-2 encoding must be 2D'
        assert data.shape[1] == 5, 'Array for 10-10-10-2 encoding must be with shape (N, 5)'
        assert numpy.issubdtype(data.dtype, numpy.floating), 'Array must have floating dtype'

        flags = data[:, 3:].astype(numpy.int32)
        data_vals = data[:, 0:3]

        data_vals = numpy.rint(data_vals * 511).astype(numpy.int32)
        data_vals = numpy.clip(data_vals, -511, 511)
        data_vals &= 0x3FF

        packed = (data_vals[:, 0] | 
                  (data_vals[:, 1] << 10) | 
                  (data_vals[:, 2] << 20) | 
                  (flags[:, 0] << 30) | 
                  (flags[:, 1] << 31))

        return packed.astype(numpy.uint32)

    @staticmethod
    def encode_tangents(tangents: numpy.ndarray, normals: numpy.ndarray) -> numpy.ndarray:
        """
        将切线编码为角度值
        
        Args:
            tangents: shape (N, 3) 的切线向量
            normals: shape (N, 3) 的法线向量
            
        Returns:
            shape (N,) 的 float32 角度编码值, 范围约 [-1, 1]
        """
        R = numpy.stack([
            normals[:, 1] - normals[:, 2],
            normals[:, 2] - normals[:, 0],
            normals[:, 0] - normals[:, 1]
        ], axis=1)

        R_norm = numpy.linalg.norm(R, axis=1, keepdims=True)
        small_mask = R_norm[:, 0] < 1e-6

        if numpy.any(small_mask):
            helper = numpy.where(
                numpy.abs(normals[:, 0:1]) < 0.9, 
                numpy.array([1.0, 0.0, 0.0]), 
                numpy.array([0.0, 1.0, 0.0])
            )
            v_perp = numpy.cross(normals, helper)
            v_perp /= numpy.linalg.norm(v_perp, axis=1, keepdims=True)
            R = numpy.where(small_mask[:, None], v_perp, R / R_norm)

        B = numpy.cross(R, normals)

        cos_theta = numpy.sum(tangents * R, axis=1)
        sin_theta = numpy.sum(tangents * B, axis=1)

        cos_theta = numpy.clip(cos_theta, -1.0, 1.0)
        sin_theta = numpy.clip(sin_theta, -1.0, 1.0)

        denom = numpy.abs(cos_theta) + numpy.abs(sin_theta)
        u_t = cos_theta / denom
        t = 1 - (1 - u_t) / 2.0

        s = numpy.where(sin_theta == 0.0, 1.0, numpy.sign(sin_theta))
        t = numpy.copysign(t, s)

        return t

    @staticmethod
    def decode_tbn_data(
        data: numpy.ndarray, 
        debug: bool = False
    ) -> numpy.ndarray:
        """
        解码 10-10-10-2 TBN 数据为法线
        
        Args:
            data: shape (N,) 的 uint32 编码数据
            debug: 是否返回调试信息 (法线, 编码切线, 副切线符号)
            
        Returns:
            默认返回 shape (N, 3) 的法线
            debug=True 时返回 (normals, encoded_tangents, bitangent_signs)
        """
        assert data.ndim == 1, 'Array for 10-10-10-2 decoding must be 1D'
        assert data.dtype == numpy.uint32, 'Array must have dtype uint32'

        decoded = TBNCodec.decode_10_10_10_2(data)

        packed_flags = decoded[:, 3]
        if not numpy.all(packed_flags == 1):
            print("[TBNCodec] WARNING: Not all packed flags are set to 1, data may not be 10-10-10-2 encoded")

        normals = TBNCodec.oct_decode_vector(decoded[:, :2])

        if debug:
            encoded_tangents = decoded[:, 2]
            bitangent_signs = numpy.where(decoded[:, 4] == 1, 1, -1)
            return normals, encoded_tangents, bitangent_signs
        else:
            return normals

    @staticmethod
    def encode_tbn_data(
        normals: numpy.ndarray, 
        tangents: numpy.ndarray, 
        bitangent_signs: numpy.ndarray
    ) -> numpy.ndarray:
        """
        编码法线、切线和副切线符号为 10-10-10-2 格式
        
        Args:
            normals: shape (N, 3) 的法线向量
            tangents: shape (N, 3) 的切线向量
            bitangent_signs: shape (N,) 的副切线符号 (-1 或 1)
            
        Returns:
            shape (N,) 的 uint32 编码数据
        """
        assert normals.ndim == 2 and normals.shape[1] == 3, 'Normals must be shape (N, 3)'
        assert tangents.ndim == 2 and tangents.shape[1] == 3, 'Tangents must be shape (N, 3)'
        assert bitangent_signs.ndim == 1, 'Bitangent signs must be 1D'
        assert numpy.issubdtype(normals.dtype, numpy.floating), 'Normals must have floating dtype'
        assert numpy.issubdtype(tangents.dtype, numpy.floating), 'Tangents must have floating dtype'
        assert numpy.issubdtype(bitangent_signs.dtype, numpy.floating), 'Bitangent signs must have floating dtype'

        encoded_normals = TBNCodec.oct_encode_vector(normals)
        encoded_tangents = TBNCodec.encode_tangents(tangents, normals)

        packed_flags = numpy.ones(len(bitangent_signs))
        sign_flags = (bitangent_signs + 1) * 0.5

        data = numpy.stack([
            encoded_normals[:, 0], 
            encoded_normals[:, 1], 
            encoded_tangents, 
            packed_flags, 
            sign_flags
        ], axis=1)
        
        encoded = TBNCodec.encode_10_10_10_2(data)

        return encoded

    @staticmethod
    def convert_normals_to_octahedral_r32_uint(input_normals: numpy.ndarray) -> numpy.ndarray:
        """
        将法线转换为终末地风格的八面体 R32_UINT 格式
        (简化版,仅编码法线,不包含切线)
        
        Args:
            input_normals: shape (N, 3) 的法线向量
            
        Returns:
            shape (N,) 的 uint32 编码数据
        """
        n = numpy.array(input_normals, dtype=numpy.float32)
        
        l1_norm = numpy.abs(n[:, 0]) + numpy.abs(n[:, 1]) + numpy.abs(n[:, 2])
        l1_norm = numpy.where(l1_norm == 0, 1.0, l1_norm)
        n /= l1_norm[:, numpy.newaxis]
        
        x, y, z = n[:, 0], n[:, 1], n[:, 2]
        
        neg_z = z < 0
        sign_x = numpy.where(x >= 0, 1.0, -1.0)
        sign_y = numpy.where(y >= 0, 1.0, -1.0)
        
        tx = (1.0 - numpy.abs(y)) * sign_x
        ty = (1.0 - numpy.abs(x)) * sign_y
        
        x = numpy.where(neg_z, tx, x)
        y = numpy.where(neg_z, ty, y)
        
        scale = 511.0
        xq = numpy.round(x * scale).astype(numpy.int32)
        yq = numpy.round(y * scale).astype(numpy.int32)
        
        xq = numpy.clip(xq, -512, 511)
        yq = numpy.clip(yq, -512, 511)
        
        xu = xq & 0x3FF
        yu = yq & 0x3FF
        
        packed = xu | (yu << 10)
        packed |= 0x40000000
        
        return packed.astype(numpy.uint32)

    @staticmethod
    def decode_octahedral_r32_uint(data: numpy.ndarray) -> numpy.ndarray:
        """
        解码终末地风格的八面体 R32_UINT 格式为法线
        (简化版,仅解码法线)
        
        Args:
            data: shape (N,) 的 uint32 编码数据
            
        Returns:
            shape (N, 3) 的法线向量
        """
        raw = data.astype(numpy.uint32)
        
        mask_10bit = 0x3FF
        x_raw = raw & mask_10bit
        y_raw = (raw >> 10) & mask_10bit
        
        x_int = x_raw.astype(numpy.int32)
        y_int = y_raw.astype(numpy.int32)
        
        x_int = numpy.where(x_int >= 512, x_int - 1024, x_int)
        y_int = numpy.where(y_int >= 512, y_int - 1024, y_int)

        scale = 1.0 / 511.0
        x = x_int * scale
        y = y_int * scale

        z = 1.0 - numpy.abs(x) - numpy.abs(y)
        
        t = z < 0
        sign_x = numpy.where(x_int >= 0, 1.0, -1.0)
        sign_y = numpy.where(y_int >= 0, 1.0, -1.0)
        
        wrapped_x = (1.0 - numpy.abs(y)) * sign_x
        wrapped_y = (1.0 - numpy.abs(x)) * sign_y
        
        nx = numpy.where(t, wrapped_x, x)
        ny = numpy.where(t, wrapped_y, y)
        nz = z

        norm = numpy.sqrt(nx * nx + ny * ny + nz * nz)
        norm = numpy.where(norm == 0, 1.0, norm)

        nx /= norm
        ny /= norm
        nz /= norm

        return numpy.column_stack((nx, ny, nz)).astype(numpy.float32)
