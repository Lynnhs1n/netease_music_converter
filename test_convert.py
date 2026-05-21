#!/usr/bin/env python3
"""测试转换流程，找出具体失败原因"""
import sys
import os
import logging

# 设置日志到控制台
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

print("=" * 50)
print("音乐转换工具 - 诊断测试")
print("=" * 50)

# 1. 检查 Python 版本
print(f"\n[1] Python 版本: {sys.version}")

# 2. 检查依赖
print("\n[2] 检查依赖包...")
try:
    from pydub import AudioSegment
    print("  ✅ pydub: OK")
except Exception as e:
    print(f"  ❌ pydub: {e}")

try:
    import mutagen
    print(f"  ✅ mutagen: {mutagen.version_string}")
except Exception as e:
    print(f"  ❌ mutagen: {e}")

try:
    from Crypto.Cipher import AES
    print("  ✅ pycryptodome: OK")
except Exception as e:
    print(f"  ❌ pycryptodome: {e}")

# 3. 检查 FFmpeg
print("\n[3] 检查 FFmpeg...")
from src.converter import FFMPEG_PATH
if FFMPEG_PATH:
    print(f"  ✅ FFmpeg 路径: {FFMPEG_PATH}")
    # 测试 ffmpeg 是否可以执行
    import subprocess
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"  ✅ FFmpeg 版本: {version_line}")
        else:
            print(f"  ❌ FFmpeg 执行失败: {result.stderr}")
    except Exception as e:
        print(f"  ❌ FFmpeg 执行异常: {e}")
else:
    print("  ❌ FFmpeg: 未找到")

# 4. 检查源模块导入
print("\n[4] 检查源模块...")
try:
    from src.decryptor import MusicDecryptor
    print("  ✅ MusicDecryptor: OK")
    print(f"     支持的格式: {MusicDecryptor.SUPPORTED_EXTENSIONS}")
except Exception as e:
    print(f"  ❌ MusicDecryptor: {e}")

try:
    from src.converter import AudioConverter
    print("  ✅ AudioConverter: OK")
    print(f"     支持的格式: {AudioConverter.AUDIO_EXTENSIONS}")
except Exception as e:
    print(f"  ❌ AudioConverter: {e}")

# 5. 检查是否有命令行参数（文件路径）
print("\n[5] 命令行参数检查...")
if len(sys.argv) > 1:
    test_file = sys.argv[1]
    if os.path.isfile(test_file):
        print(f"  测试文件: {test_file}")
        ext = os.path.splitext(test_file)[1].lower()
        print(f"  文件扩展名: {ext}")
        
        if ext in MusicDecryptor.SUPPORTED_EXTENSIONS:
            print("  该格式需要解密后转换")
            try:
                result = MusicDecryptor.decrypt(test_file)
                print(f"  ✅ 解密成功: {result}")
            except Exception as e:
                print(f"  ❌ 解密失败: {e}")
                import traceback
                traceback.print_exc()
        elif ext in AudioConverter.AUDIO_EXTENSIONS:
            print("  该格式可以直接转换")
            try:
                # 测试转换
                output_test = test_file + ".test.mp3"
                AudioConverter.convert_to_mp3(test_file, output_test)
                print(f"  ✅ 转换成功: {output_test}")
            except Exception as e:
                print(f"  ❌ 转换失败: {e}")
                import traceback
                traceback.print_exc()
    else:
        print(f"  ❌ 文件不存在: {test_file}")
else:
    print("  未指定测试文件。用法: python test_convert.py <音乐文件路径>")

print("\n" + "=" * 50)
print("诊断完成")
print("=" * 50)