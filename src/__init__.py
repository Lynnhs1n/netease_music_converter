"""
音乐格式转换工具 v2.0
支持网易云、QQ音乐、酷狗、酷我、喜马拉雅等平台加密音乐的解密与转换
"""
__version__ = "2.0.0"

# 导出核心模块
from src.decryptors import DecryptorRegistry, decrypt_file, DecryptResult
from src.converter import AudioConverter
from src.format_detector import FormatDetector
from src.metadata import MetadataManager
from src.config import ConfigManager

# 支持的加密格式扩展名
ENCRYPTED_EXTENSIONS = DecryptorRegistry.get_all_extensions()

# 支持的普通音频格式
AUDIO_EXTENSIONS = AudioConverter.AUDIO_EXTENSIONS

# 所有支持的格式
ALL_SUPPORTED_EXTENSIONS = ENCRYPTED_EXTENSIONS | AUDIO_EXTENSIONS