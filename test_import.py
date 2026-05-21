#!/usr/bin/env python3
"""验证所有模块可以正确导入"""
import sys
sys.path.insert(0, '.')

print("=== 模块导入测试 ===")

try:
    from src.decryptors import DecryptorRegistry, DecryptResult
    print(f"✅ decryptors 模块导入成功")
    print(f"   支持的加密格式: {sorted(DecryptorRegistry.get_all_extensions())}")
    print(f"   格式数量: {len(DecryptorRegistry.get_all_extensions())}")
except Exception as e:
    print(f"❌ decryptors 模块导入失败: {e}")

try:
    from src.format_detector import FormatDetector
    print(f"✅ format_detector 模块导入成功")
except Exception as e:
    print(f"❌ format_detector 模块导入失败: {e}")

try:
    from src.metadata import MetadataManager
    print(f"✅ metadata 模块导入成功")
except Exception as e:
    print(f"❌ metadata 模块导入失败: {e}")

try:
    from src.config import config
    print(f"✅ config 模块导入成功")
    print(f"   配置版本: {config.get('version')}")
    print(f"   默认比特率: {config.get('output.bitrate')}")
except Exception as e:
    print(f"❌ config 模块导入失败: {e}")

try:
    from src.converter import AudioConverter, FFMPEG_PATH
    print(f"✅ converter 模块导入成功")
    print(f"   FFmpeg: {'已找到' if FFMPEG_PATH else '未找到'}")
except Exception as e:
    print(f"❌ converter 模块导入失败: {e}")

try:
    from src.task_manager import TaskManager, TaskStatus
    print(f"✅ task_manager 模块导入成功")
except Exception as e:
    print(f"❌ task_manager 模块导入失败: {e}")

try:
    from src.decryptor import MusicDecryptor
    print(f"✅ decryptor 兼容层导入成功")
except Exception as e:
    print(f"❌ decryptor 兼容层导入失败: {e}")

try:
    from src import __version__, ENCRYPTED_EXTENSIONS, AUDIO_EXTENSIONS, ALL_SUPPORTED_EXTENSIONS
    print(f"✅ src 包导入成功")
    print(f"   版本: {__version__}")
    print(f"   总支持格式数: {len(ALL_SUPPORTED_EXTENSIONS)}")
except Exception as e:
    print(f"❌ src 包导入失败: {e}")

print("\n=== 测试完成 ===")