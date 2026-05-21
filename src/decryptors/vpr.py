"""
酷我VIP .vpr 格式解密器
VPR 是酷我音乐 VIP 专用的加密格式
"""

import os
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class VPRDecryptor(BaseDecryptor):
    """酷我VIP .vpr 格式解密器"""

    FORMAT_NAME = "酷我VIP"
    EXTENSIONS = ['.vpr']
    MAGIC_SIGNATURES = [b'\x05\x28\x50\x56']

    # VPR 解密密钥
    VPR_KEYS = [
        bytes([
            0x05, 0x28, 0x50, 0x56, 0x01, 0x06, 0x08, 0x00,
            0x50, 0x0E, 0x08, 0x40, 0x04, 0x00, 0x01, 0x24,
        ]),
        bytes([
            0x28, 0x05, 0x56, 0x50, 0x06, 0x01, 0x00, 0x08,
            0x0E, 0x50, 0x40, 0x08, 0x00, 0x04, 0x24, 0x01,
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
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 .vpr 文件

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

        # 尝试所有密钥和头部偏移组合
        for key in cls.VPR_KEYS:
            for header_size in [1024, 2048, 512, 256, 0]:
                result = cls._try_decrypt(data, key, header_size)
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

        # 回退：跳过头部直接输出
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
            f"VPR 解密失败: 所有密钥和偏移组合均无法解密此文件。"
            f"文件可能使用了新版加密算法。"
            f" (文件大小: {len(data)} bytes)"
        )
