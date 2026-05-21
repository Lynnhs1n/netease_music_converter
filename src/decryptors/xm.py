"""
喜马拉雅 .xm 格式解密器
XM 格式使用 XOR + AES 混合加密
"""

import os
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class XMDecryptor(BaseDecryptor):
    """喜马拉雅 .xm 格式解密器"""

    FORMAT_NAME = "喜马拉雅"
    EXTENSIONS = ['.xm']
    MAGIC_SIGNATURES = [b'xm\0\0', b'\x78\x6D\x00\x00']

    # XM 解密密钥
    XM_KEY = bytes([
        0x68, 0x78, 0x6D, 0x6C, 0x79, 0x74, 0x20, 0x2D,
        0x20, 0x78, 0x69, 0x6D, 0x61, 0x6C, 0x61, 0x79,
    ])

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
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 .xm 文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            output_format: 输出格式

        Returns:
            DecryptResult 对象
        """
        with open(input_path, 'rb') as f:
            data = f.read()

        if output_path is None:
            output_path = cls._auto_output_path(input_path, 'mp3')

        # 尝试主密钥
        for header_size in [1024, 2048, 512, 256, 64, 0]:
            result = cls._try_decrypt(data, cls.XM_KEY, header_size)
            if result is not None:
                with open(output_path, 'wb') as out:
                    out.write(result)
                detected_type = cls._detect_audio_type(result[:32])
                logger.info(f"解密完成 (header={header_size}): {output_path}")
                return DecryptResult(
                    audio_path=output_path,
                    source_format=cls.FORMAT_NAME,
                    detected_type=detected_type,
                )

        # 尝试跳过头部直接输出
        logger.warning(f"标准解密失败，尝试直接提取: {input_path}")
        for skip in [1024, 2048, 4096, 512, 64, 0]:
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
            f"XM 解密失败: 所有密钥和偏移组合均无法解密此文件。"
            f"文件可能使用了新版加密算法。"
            f" (文件大小: {len(data)} bytes)"
        )
