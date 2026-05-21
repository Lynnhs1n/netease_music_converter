"""
酷狗音乐 KGM/KGMA 格式解密器
支持 .kgm 和 .kgma 格式
"""

import os
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class KGMDecryptor(BaseDecryptor):
    """酷狗音乐 KGM/KGMA 格式解密器"""

    FORMAT_NAME = "酷狗音乐"
    EXTENSIONS = ['.kgm', '.kgma']
    MAGIC_SIGNATURES = [b'\x7C\xD9\xA5\xE1']

    # 酷狗解密密钥集（不同版本）
    KGM_KEYS = [
        # V1
        bytes([
            0x7C, 0xD9, 0xA5, 0xE1, 0xDB, 0x2E, 0x25, 0x44,
            0x48, 0x79, 0xC0, 0xA2, 0xAA, 0xFC, 0x53, 0x97,
            0x7A, 0x03, 0x15, 0x0B, 0xD1, 0x2B, 0xF3, 0x32,
            0xD5, 0x1E, 0x24, 0x08, 0xB0, 0xD0, 0x57, 0xD3,
        ]),
        # V2 (常见变体)
        bytes([
            0x40, 0x58, 0x31, 0x6E, 0x0A, 0x17, 0x38, 0x6B,
            0x4C, 0x29, 0x7A, 0x0D, 0x3E, 0x5B, 0x25, 0x41,
            0x06, 0x7F, 0x3E, 0x2B, 0x5D, 0x46, 0x1D, 0x27,
            0x69, 0x34, 0x0C, 0x5A, 0x2F, 0x43, 0x18, 0x70,
        ]),
        # V3
        bytes([
            0x23, 0x47, 0x60, 0x12, 0x59, 0x3D, 0x0B, 0x74,
            0x68, 0x35, 0x2A, 0x01, 0x4F, 0x6C, 0x19, 0x36,
            0x5E, 0x08, 0x71, 0x2D, 0x44, 0x1B, 0x67, 0x0E,
            0x33, 0x5A, 0x28, 0x49, 0x14, 0x7C, 0x03, 0x61,
        ]),
    ]

    # 常见的头部大小偏移
    HEADER_SIZES = [1024, 2048, 4096, 0]

    @classmethod
    def _try_decrypt_with_key(cls, data: bytes, key: bytes, header_size: int) -> Optional[bytes]:
        """尝试用指定密钥和头部偏移解密"""
        if header_size >= len(data):
            return None

        audio_data = data[header_size:]
        key_len = len(key)
        decrypted = bytearray(len(audio_data))

        for i in range(len(audio_data)):
            decrypted[i] = audio_data[i] ^ key[i % key_len]

        # 验证解密结果
        if cls._is_valid_audio(decrypted[:16]):
            return bytes(decrypted)

        return None

    @classmethod
    def _is_valid_audio(cls, header: bytes) -> bool:
        """检查是否为有效音频头"""
        if len(header) < 4:
            return False
        return (
            header[:3] == b'ID3' or
            header[:4] == b'fLaC' or
            header[:4] == b'OggS' or
            header[:4] == b'RIFF' or
            (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0)
        )

    @classmethod
    def _parse_header_metadata(cls, data: bytes) -> dict:
        """尝试从 KGM 头部提取元数据"""
        metadata = {}
        try:
            import json
            # KGM 头部可能包含 JSON 元数据
            header_text = data[:1024]

            # 尝试查找 JSON 片段
            for start_marker in [b'{', b'\x00{']:
                pos = header_text.find(start_marker)
                if pos >= 0:
                    json_data = header_text[pos:]
                    null_pos = json_data.find(b'\x00')
                    if null_pos > 0:
                        json_data = json_data[:null_pos]
                    try:
                        meta = json.loads(json_data)
                        if isinstance(meta, dict):
                            metadata['title'] = meta.get('songName', '') or meta.get('title', '')
                            metadata['artist'] = meta.get('artistName', '') or meta.get('artist', '')
                            metadata['album'] = meta.get('albumName', '') or meta.get('album', '')
                            metadata = {k: v for k, v in metadata.items() if v}
                            if metadata:
                                return metadata
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        continue
        except Exception as e:
            logger.debug(f"头部元数据解析失败: {e}")

        return metadata

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 KGM/KGMA 文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            output_format: 输出格式

        Returns:
            DecryptResult 对象
        """
        if output_path is None:
            output_path = cls._auto_output_path(input_path, 'mp3')

        with open(input_path, 'rb') as f:
            data = f.read()

        # 检查魔数头
        header = data[:4]
        if not header == b'\x7C\xD9\xA5\xE1':
            logger.warning(f"文件头不匹配 KGM 标准魔数，仍尝试解密: {input_path}")

        # 尝试提取头部元数据
        metadata = cls._parse_header_metadata(data)

        # 遍历所有密钥和头部偏移组合
        for key in cls.KGM_KEYS:
            for header_size in cls.HEADER_SIZES:
                result = cls._try_decrypt_with_key(data, key, header_size)
                if result is not None:
                    with open(output_path, 'wb') as out:
                        out.write(result)
                    detected_type = cls._detect_audio_type(result[:32])
                    logger.info(f"解密完成 (header={header_size}): {output_path}")
                    return DecryptResult(
                        audio_path=output_path,
                        metadata=metadata,
                        source_format=cls.FORMAT_NAME,
                        detected_type=detected_type,
                    )

        # 所有组合都失败，尝试跳过头部直接输出
        logger.warning(f"标准解密失败，尝试跳过头部直接提取: {input_path}")
        for skip in [1024, 2048, 4096, 0]:
            if skip < len(data):
                test_data = data[skip:]
                if cls._is_valid_audio(test_data[:16]):
                    with open(output_path, 'wb') as out:
                        out.write(test_data)
                    detected_type = cls._detect_audio_type(test_data[:32])
                    logger.info(f"直接提取成功 (skip={skip}): {output_path}")
                    return DecryptResult(
                        audio_path=output_path,
                        metadata=metadata,
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
                metadata=metadata,
                source_format=f"{cls.FORMAT_NAME} (未加密)",
                detected_type=detected_type,
            )

        # 真正的解密失败 - 抛出明确错误
        raise RuntimeError(
            f"KGM 解密失败: 所有密钥和偏移组合均无法解密此文件。"
            f"文件可能使用了新版加密算法。"
            f" (文件大小: {len(data)} bytes)"
        )
