"""
解密器基类和统一返回结构
所有解密器必须继承 BaseDecryptor 并实现 decrypt_file 方法
"""

import os
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


@dataclass
class DecryptResult:
    """解密结果统一数据结构"""
    audio_path: str                    # 解密后的音频文件路径
    cover_data: Optional[bytes] = None # 封面图片二进制数据
    cover_mime: str = "image/jpeg"     # 封面 MIME 类型
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    lyrics: Optional[str] = None       # 歌词内容 (LRC 格式)
    source_format: str = ""            # 源格式名称
    detected_type: Optional[str] = None  # 检测到的内部音频类型 (mp3/flac/ogg)

    @property
    def title(self) -> Optional[str]:
        return self.metadata.get('title')

    @property
    def artist(self) -> Optional[str]:
        return self.metadata.get('artist')

    @property
    def album(self) -> Optional[str]:
        return self.metadata.get('album')

    @property
    def has_cover(self) -> bool:
        return self.cover_data is not None and len(self.cover_data) > 0

    @property
    def has_lyrics(self) -> bool:
        return self.lyrics is not None and len(self.lyrics.strip()) > 0


class BaseDecryptor:
    """解密器基类"""

    # 子类必须设置: 格式名称
    FORMAT_NAME: str = "Unknown"
    # 子类必须设置: 支持的扩展名列表
    EXTENSIONS: List[str] = []
    # 文件头魔数签名 (用于自动识别)
    MAGIC_SIGNATURES: List[bytes] = []

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密文件

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径 (None 则自动生成)
            output_format: 输出格式 ('mp3', 'flac', 'ogg')

        Returns:
            DecryptResult 对象
        """
        raise NotImplementedError("子类必须实现 decrypt_file 方法")

    @classmethod
    def _detect_audio_type(cls, data: bytes) -> Optional[str]:
        """通过文件头魔数检测解密后的音频类型"""
        if len(data) < 4:
            return None
        if data[:3] == b'ID3' or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0):
            return 'mp3'
        if data[:4] == b'fLaC':
            return 'flac'
        if data[:4] == b'OggS':
            return 'ogg'
        if data[:4] == b'RIFF':
            return 'wav'
        if b'ftyp' in data[:32]:
            return 'm4a'
        if data[:4] == b'MAC ':
            return 'ape'
        if data[:3] == b'\xff\xf1' or data[:3] == b'\xff\xf9':
            return 'aac'
        return None

    @classmethod
    def _detect_cover_mime(cls, cover_data: bytes) -> str:
        """检测封面图片 MIME 类型"""
        if not cover_data or len(cover_data) < 4:
            return "image/jpeg"
        if cover_data[:3] == b'\xFF\xD8\xFF':
            return "image/jpeg"
        if cover_data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if cover_data[:4] == b'RIFF' and cover_data[8:12] == b'WEBP':
            return "image/webp"
        if cover_data[:4] == b'GIF8':
            return "image/gif"
        return "image/jpeg"

    @staticmethod
    def _auto_output_path(input_path: str, output_format: str) -> str:
        """自动生成输出路径"""
        base = os.path.splitext(input_path)[0]
        return f"{base}.{output_format}"

    @staticmethod
    def _is_valid_audio_header(data: bytes, fmt: str) -> bool:
        """检查数据头是否为有效的音频格式"""
        if len(data) < 4:
            return False
        if fmt == 'mp3':
            return data[:3] == b'ID3' or (data[0] == 0xFF and (data[1] & 0xE0) == 0xE0)
        elif fmt == 'flac':
            return data[:4] == b'fLaC'
        elif fmt == 'ogg':
            return data[:4] == b'OggS'
        elif fmt == 'wav':
            return data[:4] == b'RIFF'
        elif fmt == 'ape':
            return data[:4] == b'MAC '
        return True

    @classmethod
    def _is_valid_audio_data(cls, data: bytes) -> bool:
        """
        检查数据是否为任何已知的音频格式。
        用于解密后验证输出是否真的包含有效音频数据。
        """
        if len(data) < 4:
            return False
        for fmt in ('mp3', 'flac', 'ogg', 'wav', 'ape'):
            if cls._is_valid_audio_header(data, fmt):
                return True
        # 检查 AAC / M4A
        if b'ftyp' in data[:32]:
            return True
        if data[:3] == b'\xff\xf1' or data[:3] == b'\xff\xf9':
            return True
        return False

    @classmethod
    def _validate_decrypted_output(cls, data: bytes, output_path: str,
                                   source_format: str = "") -> DecryptResult:
        """
        验证解密后的数据是否为有效音频，无效则抛出异常。

        Args:
            data: 解密后的数据
            output_path: 输出文件路径
            source_format: 源格式描述

        Returns:
            DecryptResult 对象

        Raises:
            RuntimeError: 解密后的数据不是有效音频格式
        """
        if cls._is_valid_audio_data(data):
            with open(output_path, 'wb') as out:
                out.write(data)
            detected_type = cls._detect_audio_type(data[:32])
            logger.info(f"解密验证通过 ({detected_type}): {output_path}")
            return DecryptResult(
                audio_path=output_path,
                source_format=source_format,
                detected_type=detected_type,
            )
        else:
            raise RuntimeError(
                f"解密失败: 输出数据不是有效的音频格式。"
                f"可能是新版加密算法，当前解密器不支持。"
                f" (源格式: {source_format})"
            )
