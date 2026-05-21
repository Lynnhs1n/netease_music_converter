# -*- mode: python ; coding: utf-8 -*-
"""
音乐格式转换工具 - PyInstaller 打包配置
"""

import os
import sys

block_cipher = None

# 查找 imageio_ffmpeg 的 ffmpeg 可执行文件
ffmpeg_data = []
try:
    import imageio_ffmpeg
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    if ffmpeg_exe and os.path.isfile(ffmpeg_exe):
        # 将 ffmpeg.exe 打包到根目录
        ffmpeg_data = [(ffmpeg_exe, '.')]
except Exception:
    pass

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=ffmpeg_data,
    datas=[
        ('src/decryptors/qq_ogg_hook.js', 'src/decryptors'),
    ],
    hiddenimports=[
        'src',
        'src.config',
        'src.converter',
        'src.decryptor',
        'src.format_detector',
        'src.metadata',
        'src.task_manager',
        'src.gui',
        'src.gui.main_window',
        'src.decryptors',
        'src.decryptors.base',
        'src.decryptors.ncm',
        'src.decryptors.qmc',
        'src.decryptors.kgm',
        'src.decryptors.kwm',
        'src.decryptors.vpr',
        'src.decryptors.xm',
        'src.decryptors.qq_ogg',
        'pydub',
        'mutagen',
        'mutagen.mp3',
        'mutagen.id3',
        'mutagen.flac',
        'mutagen.oggvorbis',
        'mutagen.mp4',
        'Crypto',
        'Crypto.Cipher',
        'Crypto.Cipher.AES',
        'audioop',
        'imageio_ffmpeg',
        'frida',
        'frida_tools',
        'psutil',
        'windnd',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'PIL',
        'cv2',
        'torch',
        'tensorflow',
        'IPython',
        'jupyter',
        'notebook',
        'pytest',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MusicConverter',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 保留控制台以便 CLI 模式使用
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)