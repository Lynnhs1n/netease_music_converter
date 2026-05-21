#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
音乐格式转换工具 v2.0
将网易云、QQ音乐、酷狗、酷我、喜马拉雅等音乐平台下载的加密音乐转换为标准格式

支持格式:
  加密格式:
  - 网易云音乐: .ncm
  - QQ音乐: .qmc0, .qmc2, .qmc3, .qmcflac, .qmcogg, .mflac, .mflac0, .mgg, .mgg1, .mggl, .tkm
  - 酷狗音乐: .kgm, .kgma
  - 酷我音乐: .kwm, .vpr
  - 喜马拉雅: .xm
  普通音频:
  - .flac, .wav, .ogg, .aac, .wma, .m4a, .ape, .wv, .opus

用法:
  python main.py              # 启动 GUI 界面
  python main.py -h           # 查看帮助
  python main.py file.ncm     # 命令行转换单个文件
  python main.py *.ncm        # 批量转换
"""

import sys
import os

# 确保 src 目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    """主入口"""
    if len(sys.argv) > 1:
        # 命令行模式
        args = sys.argv[1:]
        if args[0] in ('-h', '--help'):
            print(__doc__)
            return

        from src.decryptors import DecryptorRegistry, decrypt_file
        from src.converter import AudioConverter
        from src.metadata import MetadataManager
        from src.format_detector import FormatDetector

        for filepath in args:
            if not os.path.isfile(filepath):
                print(f"文件不存在: {filepath}")
                continue

            ext = os.path.splitext(filepath)[1].lower()
            output_path = os.path.splitext(filepath)[0] + '.mp3'

            try:
                if DecryptorRegistry.is_supported(filepath):
                    # 加密格式
                    fmt_name = DecryptorRegistry.get_format_name(filepath)
                    print(f"解密: {filepath} ({fmt_name})")
                    result = decrypt_file(filepath)
                    print(f"转换为 MP3...")
                    AudioConverter.convert_to_mp3(
                        result.audio_path, output_path,
                        cover_data=result.cover_data,
                        metadata=result.metadata,
                    )
                    # 写入元数据
                    MetadataManager.write_metadata(
                        output_path,
                        metadata=result.metadata,
                        cover_data=result.cover_data,
                        cover_mime=result.cover_mime,
                        lyrics=result.lyrics,
                    )
                    # 导出歌词
                    if result.has_lyrics:
                        lrc_path = os.path.splitext(output_path)[0] + '.lrc'
                        MetadataManager.export_lyrics(result.lyrics, lrc_path)
                        print(f"  歌词已导出: {lrc_path}")
                    # 清理临时文件
                    if result.audio_path != filepath and os.path.exists(result.audio_path):
                        os.unlink(result.audio_path)
                elif ext in AudioConverter.AUDIO_EXTENSIONS:
                    # 普通音频格式
                    print(f"转换: {filepath}")
                    AudioConverter.convert_to_mp3(filepath, output_path)
                else:
                    print(f"不支持的格式: {ext}")
                    continue

                print(f"✅ 完成: {output_path}")
            except Exception as e:
                print(f"❌ 失败: {filepath} - {e}")
    else:
        # GUI 模式
        from src.gui import run_gui
        run_gui()


if __name__ == '__main__':
    main()