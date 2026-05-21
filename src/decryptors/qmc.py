"""
QQ音乐 QMC 格式解密器
支持 QMC0/QMC2/QMC3/QMCFLAC/QMCOGG/MFLAC/MFLAC0/MGG/MGG1/MGGL
支持尾部映射表 (QMC V2 Map/STag)
"""

import os
import struct
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class QMCDecryptor(BaseDecryptor):
    """QQ音乐 QMC 格式解密器"""

    FORMAT_NAME = "QQ音乐"
    EXTENSIONS = [
        '.qmc0', '.qmc2', '.qmc3', '.qmcflac', '.qmcogg',
        '.mflac', '.mflac0', '.mgg', '.mgg1', '.mggl',
        '.tkm',
    ]
    MAGIC_SIGNATURES = []  # QMC 没有明显的文件头魔数

    # QMC 映射表种子 (V1)
    MAP_SEED = [
        0x77, 0x48, 0x32, 0x73, 0xDE, 0xF2, 0xC0, 0xC8,
        0x95, 0xEC, 0x30, 0xB2, 0x51, 0xC3, 0xE1, 0xA0,
        0x9E, 0xE6, 0x9D, 0xCF, 0xFA, 0x7F, 0x14, 0xD1,
        0xCE, 0xB8, 0xDC, 0xC3, 0x4A, 0x67, 0x93, 0xD6,
        0x28, 0xC2, 0x91, 0x70, 0xCA, 0x8D, 0xA2, 0xA4,
        0xF0, 0x08, 0x61, 0x90, 0x7E, 0x6F, 0xA2, 0xE0,
        0xEB, 0xAE, 0x3E, 0xB6, 0x67, 0xC8, 0x6B, 0x3F,
        0x07, 0x04, 0x56, 0x3B, 0x06, 0x00, 0x3D, 0x8D,
    ]

    # 扩展格式到内部音频类型的映射
    FORMAT_MAP = {
        '.qmc0': 'mp3',
        '.qmc2': 'ogg',
        '.qmc3': 'ogg',
        '.qmcflac': 'flac',
        '.qmcogg': 'ogg',
        '.mflac': 'flac',
        '.mflac0': 'flac',
        '.mgg': 'ogg',
        '.mgg1': 'ogg',
        '.mggl': 'ogg',
        '.tkm': 'mp3',
    }

    @classmethod
    def _generate_key_map(cls, seed=None) -> bytearray:
        """生成 QMC V1 解密映射表"""
        if seed is None:
            seed = cls.MAP_SEED

        key = bytearray(256)
        for i in range(256):
            key[i] = i

        j = 0
        for i in range(256):
            j = (key[i] + j + seed[i % len(seed)]) & 0xFF
            key[i], key[j] = key[j], key[i]

        # 生成第二轮映射
        result = bytearray(256)
        for i in range(256):
            result[i] = (i + 1) & 0xFF

        j = 0
        for i in range(256):
            j = (result[i] + j + key[i]) & 0xFF
            result[i], result[j] = result[j], result[i]

        # 最终映射
        mapping = bytearray(256)
        for i in range(256):
            mapping[result[i]] = result[(i + 1) & 0xFF]

        return mapping

    @classmethod
    def _parse_v2_footer(cls, data: bytes) -> Optional[bytearray]:
        """
        解析 QMC V2 尾部映射表
        尾部结构: [映射表数据] [4字节大小] [1字节标记] "QTag" 或 "STag" 或 "StkE"
        """
        if len(data) < 8:
            return None

        # 检查尾部标记
        footer = data[-4:]
        tag_size_offset = -8  # 标记前4字节是大小

        if footer == b'QTag':
            # QTag 格式: 映射表 + 4字节大小 + "QTag"
            try:
                map_size = struct.unpack('<I', data[-8:-4])[0]
                if map_size <= 0 or map_size > len(data) - 8:
                    return None
                map_data = data[-(8 + map_size):-8]
                if len(map_data) != map_size:
                    return None
                return bytearray(map_data)
            except Exception:
                return None

        elif footer == b'STag':
            # STag 格式: 映射表 + 4字节大小 + "STag"
            try:
                map_size = struct.unpack('<I', data[-8:-4])[0]
                if map_size <= 0 or map_size > len(data) - 8:
                    return None
                map_data = data[-(8 + map_size):-8]
                if len(map_data) != map_size:
                    return None
                return bytearray(map_data)
            except Exception:
                return None

        elif footer == b'StkE':
            # StkE 格式: 映射表 + 4字节大小 + "StkE"
            try:
                map_size = struct.unpack('<I', data[-8:-4])[0]
                if map_size <= 0 or map_size > len(data) - 8:
                    return None
                map_data = data[-(8 + map_size):-8]
                if len(map_data) != map_size:
                    return None
                return bytearray(map_data)
            except Exception:
                return None

        return None

    @classmethod
    def _qmc_v1_decrypt(cls, data: bytes) -> bytes:
        """QMC V1 解密"""
        key = cls._generate_key_map()
        result = bytearray(len(data))

        chunk_size = 0x8000
        for offset in range(0, len(data), chunk_size):
            chunk = data[offset:offset + chunk_size]
            for i, b in enumerate(chunk):
                seed_index = ((offset + i) * 1) % len(cls.MAP_SEED)
                idx = (b + cls.MAP_SEED[seed_index]) & 0xFF
                result[offset + i] = b ^ key[idx % 256]

        return bytes(result)

    @classmethod
    def _qmc_v2_decrypt(cls, data: bytes, mapping: bytearray) -> bytes:
        """QMC V2 解密 (使用尾部映射表)"""
        map_size = len(mapping)
        if map_size == 0:
            return data

        result = bytearray(len(data))
        for i, b in enumerate(data):
            map_idx = (i * i + 27) % map_size
            result[i] = b ^ mapping[map_idx]

        return bytes(result)

    @classmethod
    def _qmc_static_decrypt(cls, data: bytes) -> bytes:
        """QMC 静态映射表解密 (用于无尾部标记的 V2 格式)"""
        key = cls._generate_key_map()
        result = bytearray(len(data))
        for i, b in enumerate(data):
            offset_key = key[(i & 0x7FF) % 256]
            result[i] = b ^ offset_key
        return bytes(result)

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 QMC 文件

        Args:
            input_path: 输入的 QMC 文件路径
            output_path: 输出文件路径
            output_format: 输出格式

        Returns:
            DecryptResult 对象
        """
        ext = os.path.splitext(input_path)[1].lower()
        internal_format = cls.FORMAT_MAP.get(ext, 'mp3')

        if output_path is None:
            output_path = cls._auto_output_path(input_path, internal_format)

        with open(input_path, 'rb') as f:
            data = f.read()

        original_size = len(data)

        # 尝试解析 V2 尾部映射表
        v2_mapping = cls._parse_v2_footer(data)

        if v2_mapping is not None:
            # V2 解密 (带尾部映射表)
            # 去除尾部: 映射表 + 4字节大小 + 4字节标记
            footer_total = len(v2_mapping) + 8
            audio_data_raw = data[:-footer_total]

            logger.info(f"检测到 V2 映射表 ({len(v2_mapping)} bytes)")
            decrypted = cls._qmc_v2_decrypt(audio_data_raw, v2_mapping)

            if cls._is_valid_audio_header(decrypted[:16], internal_format):
                with open(output_path, 'wb') as out:
                    out.write(decrypted)
                logger.info(f"解密完成 (V2-Map): {output_path}")
                detected_type = cls._detect_audio_type(decrypted[:32])
                return DecryptResult(
                    audio_path=output_path,
                    source_format=f"{cls.FORMAT_NAME} (V2)",
                    detected_type=detected_type,
                )

        # V1 解密
        try:
            decrypted = cls._qmc_v1_decrypt(data)
            if cls._is_valid_audio_header(decrypted[:16], internal_format):
                with open(output_path, 'wb') as out:
                    out.write(decrypted)
                logger.info(f"解密完成 (V1): {output_path}")
                detected_type = cls._detect_audio_type(decrypted[:32])
                return DecryptResult(
                    audio_path=output_path,
                    source_format=f"{cls.FORMAT_NAME} (V1)",
                    detected_type=detected_type,
                )
        except Exception as e:
            logger.debug(f"V1解密失败: {e}")

        # 静态映射表解密
        try:
            decrypted = cls._qmc_static_decrypt(data)
            if cls._is_valid_audio_header(decrypted[:16], internal_format):
                with open(output_path, 'wb') as out:
                    out.write(decrypted)
                logger.info(f"解密完成 (Static): {output_path}")
                detected_type = cls._detect_audio_type(decrypted[:32])
                return DecryptResult(
                    audio_path=output_path,
                    source_format=f"{cls.FORMAT_NAME} (Static)",
                    detected_type=detected_type,
                )
        except Exception as e:
            logger.debug(f"静态解密失败: {e}")

        # 所有解密方法都失败 - 检查原始数据是否本身就是有效音频（可能未加密）
        if cls._is_valid_audio_data(data):
            with open(output_path, 'wb') as out:
                out.write(data)
            detected_type = cls._detect_audio_type(data[:32])
            logger.info(f"文件已是未加密的音频，直接复制: {output_path}")
            return DecryptResult(
                audio_path=output_path,
                source_format=f"{cls.FORMAT_NAME} (未加密)",
                detected_type=detected_type,
            )

        # 真正的解密失败 - 抛出明确错误
        raise RuntimeError(
            f"QMC 解密失败: 所有解密方法（V2/V1/静态映射）均无法解密此文件。"
            f"文件可能使用了新版加密算法。"
            f" (扩展名: {ext}, 文件大小: {original_size} bytes)"
        )
