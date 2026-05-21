"""
音乐文件解密模块 - 兼容层
重定向到新的 src/decryptors 包
保留旧接口以兼容现有代码
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)
logger.info("使用新版解密模块 (src.decryptors)")

# 从新模块导入
from src.decryptors import (
    DecryptorRegistry,
    decrypt_file as _decrypt_file,
    DecryptResult,
    NCMDecryptor,
    QMCDecryptor,
    KGMDecryptor,
)

# 保持旧接口兼容 - 直接使用 DecryptorRegistry 作为 MusicDecryptor
MusicDecryptor = DecryptorRegistry


class MusicDecryptorCompat:
    """兼容旧版 MusicDecryptor 接口"""

    DECRYPTORS = list(DecryptorRegistry._decryptors) if hasattr(DecryptorRegistry, '_decryptors') else []
    SUPPORTED_EXTENSIONS = DecryptorRegistry.get_all_extensions()

    @classmethod
    def is_supported(cls, file_path):
        return DecryptorRegistry.is_supported(file_path)

    @classmethod
    def get_format_name(cls, file_path):
        return DecryptorRegistry.get_format_name(file_path)

    @classmethod
    def decrypt(cls, input_path, output_path=None, output_format='mp3'):
        """
        解密文件（兼容旧接口）

        Returns:
            (输出文件路径, 封面数据) 元组 - 旧接口兼容
        """
        result = _decrypt_file(input_path, output_path, output_format)
        # 返回兼容格式
        return result.audio_path, result.cover_data


# 导出兼容接口
__all__ = ['MusicDecryptor', 'MusicDecryptorCompat', 'DecryptResult', 'decrypt_file']
