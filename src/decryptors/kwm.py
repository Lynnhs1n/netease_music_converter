"""
酷我音乐 .kwm 格式解密器
酷我音乐的 KWM 格式使用 AES 加密 + 特定头部结构
"""

import os
import struct
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class KWMDecryptor(BaseDecryptor):
    """酷我音乐 .kwm 格式解密器"""

    FORMAT_NAME = "酷我音乐"
    EXTENSIONS = ['.kwm']
    MAGIC_SIGNATURES = [b'\x32\x34\x6B\x77', b'kwm']

    # KWM 解密密钥 (多种版本)
    KWM_KEYS = [
        # V1
        bytes([
            0x69, 0x39, 0x37, 0x6D, 0x37, 0x66, 0x65, 0x69,
            0x38, 0x35, 0x36, 0x64, 0x34, 0x33, 0x38, 0x37,
        ]),
        # V2
        bytes([
            0x38, 0x35, 0x36, 0x64, 0x34, 0x33, 0x38, 0x37,
            0x69, 0x39, 0x37, 0x6D, 0x37, 0x66, 0x65, 0x69,
        ]),
    ]

    @classmethod
    def _try_decrypt(cls, data: bytes, key: bytes, header_size: int) -> Optional[bytes]:
        """尝试用指定密钥解密"""
        if header_size >= len(data):
            return None

        audio_data = data[header_size:]
        key_len = len(key)
        decrypted = bytearray(len(audio_data))

        for i in range(len(audio_data)):
            decrypted[i] = audio_data[i] ^ key[i % key_len]

        if cls._is_valid_audio_header(decrypted[:16], 'mp3') or \
           cls._is_valid_audio_header(decrypted[:16], 'flac') or \
           cls._is_valid_audio_header(decrypted[:16], 'ogg'):
            return bytes(decrypted)

        return None

    @classmethod
    def _parse_kwm_header(cls, data: bytes) -> dict:
        """解析 KWM 文件头获取元数据和音频信息"""
        info = {
            'header_size': 0,
            'audio_format': 'mp3',
        }

        # KWM 头部结构:
        # 前4字节: 魔数
        # 接下来可能包含格式信息
        if len(data) < 16:
            return info

        # 检查是否包含 "kwm" 标识
        if data[:3] == b'kwm':
            # 标准 KWM 格式
            info['header_size'] = 1024
        elif data[:4] == b'\x32\x34\x6B\x77':
            # 变体格式 "24kw"
            info['header_size'] = 1024
        else:
            info['header_size'] = 1024

        # 尝试从头部中读取格式信息
        # 某些 KWM 文件在偏移 12-16 处存储音频格式标识
        try:
            fmt_indicator = struct.unpack('<I', data[12:16])[0]
            if fmt_indicator == 0x43414C46:  # 'FLAC'
                info['audio_format'] = 'flac'
            elif fmt_indicator == 0x5367674F:  # 'OggS'
                info['audio_format'] = 'ogg'
        except Exception:
            pass

        return info

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 .kwm 文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            output_format: 输出格式

        Returns:
            DecryptResult 对象
        """
        with open(input_path, 'rb') as f:
            data = f.read()

        kwm_info = cls._parse_kwm_header(data)
        header_size = kwm_info['header_size']
        internal_format = kwm_info['audio_format']

        if output_path is None:
            output_path = cls._auto_output_path(input_path, internal_format)

        # 尝试所有密钥组合
        for key in cls.KWM_KEYS:
            for skip in [header_size, 1024, 2048, 512, 0]:
                result = cls._try_decrypt(data, key, skip)
                if result is not None:
                    with open(output_path, 'wb') as out:
                        out.write(result)
                    detected_type = cls._detect_audio_type(result[:32])
                    logger.info(f"解密完成 (key=V{cls.KWM_KEYS.index(key)+1}, skip={skip}): {output_path}")
                    return DecryptResult(
                        audio_path=output_path,
                        source_format=cls.FORMAT_NAME,
                        detected_type=detected_type,
                    )

        # 最后尝试：跳过头部直接输出
        logger.warning(f"标准解密失败，尝试直接提取: {input_path}")
        for skip in [1024, 2048, 4096, 512, 0]:
            if skip < len(data):
                test_data = data[skip:]
                if cls._is_valid_audio_header(test_data[:16], 'mp3') or \
                   cls._is_valid_audio_header(test_data[:16], 'flac') or \
                   cls._is_valid_audio_header(test_data[:16], 'ogg'):
                    with open(output_path, 'wb') as out:
                        out.write(test_data)
                    detected_type = cls._detect_audio_type(test_data[:32])
                    logger.info(f"直接提取成功 (skip={skip}): {output_path}")
                    return DecryptResult(
                        audio_path=output_path,
                        source_format=f"{cls.FORMAT_NAME} (Direct)",
                        detected_type=detected_type,
                    )

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
            f"KWM 解密失败: 所有密钥和偏移组合均无法解密此文件。"
            f"文件可能使用了新版加密算法。"
            f" (文件大小: {len(data)} bytes)"
        )
