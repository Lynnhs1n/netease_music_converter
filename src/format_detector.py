"""
文件格式检测器
通过文件头魔数（Magic Number）自动识别加密音乐文件所属平台
"""

import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class FileSignature:
    """文件签名定义"""
    def __init__(self, magic: bytes, offset: int, format_name: str, extension: str):
        self.magic = magic
        self.offset = offset
        self.format_name = format_name
        self.extension = extension


# 加密格式签名表 (按优先级排序)
ENCRYPTED_SIGNATURES = [
    # 网易云音乐 NCM
    FileSignature(b'CTENFDAM', 0, '网易云音乐', '.ncm'),

    # 酷狗音乐 KGM/KGMA
    FileSignature(b'\x7C\xD9\xA5\xE1', 0, '酷狗音乐', '.kgm'),

    # 酷我音乐 KWM (通常以特定头部开始)
    FileSignature(b'\x32\x34\x6B\x77', 0, '酷我音乐', '.kwm'),
    FileSignature(b'kwm', 0, '酷我音乐', '.kwm'),

    # 酷我 VPR
    FileSignature(b'\x05\x28\x50\x56', 0, '酷我VIP', '.vpr'),

    # 喜马拉雅 XM
    FileSignature(b'\x00\x00\x00\x00', 0, None, None),  # 占位，需特殊处理

    # 虾米音乐
    FileSignature(b'xm\0\0', 0, '虾米音乐', '.xm'),
]

# 普通音频格式签名表
AUDIO_SIGNATURES = [
    FileSignature(b'ID3', 0, 'MP3', '.mp3'),
    FileSignature(b'fLaC', 0, 'FLAC', '.flac'),
    FileSignature(b'OggS', 0, 'OGG', '.ogg'),
    FileSignature(b'RIFF', 0, 'WAV', '.wav'),
    FileSignature(b'MAC ', 0, 'APE', '.ape'),
    FileSignature(b'wvpk', 0, 'WavPack', '.wv'),
]

# 需要进一步检测的签名（匹配后需要额外验证）
NEED_FURTHER_CHECK = {
    b'\x7C\xD9\xA5\xE1': ['.kgm', '.kgma'],
    b'\x00\x00\x00\x00': ['.vpr', '.xm'],  # 可能是多种格式
}


class FormatDetector:
    """文件格式检测器"""

    @staticmethod
    def detect_by_extension(file_path: str) -> Optional[str]:
        """
        通过扩展名检测格式

        Args:
            file_path: 文件路径

        Returns:
            扩展名 (如 '.ncm') 或 None
        """
        ext = os.path.splitext(file_path)[1].lower()
        return ext if ext else None

    @staticmethod
    def detect_by_magic(file_path: str) -> Tuple[Optional[str], Optional[str]]:
        """
        通过文件头魔数检测格式

        Args:
            file_path: 文件路径

        Returns:
            (格式名称, 扩展名) 元组，检测失败返回 (None, None)
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)
        except (IOError, OSError) as e:
            logger.error(f"无法读取文件头: {file_path} - {e}")
            return None, None

        if not header or len(header) < 4:
            return None, None

        # 优先检测加密格式
        for sig in ENCRYPTED_SIGNATURES:
            if header[sig.offset:sig.offset + len(sig.magic)] == sig.magic:
                if sig.format_name is not None:
                    return sig.format_name, sig.extension

        # 检测普通音频格式
        for sig in AUDIO_SIGNATURES:
            if header[sig.offset:sig.offset + len(sig.magic)] == sig.magic:
                return sig.format_name, sig.extension

        # MP3 MPEG sync 检测 (无 ID3 标签)
        if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
            return 'MP3', '.mp3'

        # M4A/MP4 检测
        if b'ftyp' in header[:32]:
            return 'M4A', '.m4a'

        # AAC ADTS
        if header[:2] == b'\xFF\xF1' or header[:2] == b'\xFF\xF9':
            return 'AAC', '.aac'

        return None, None

    @classmethod
    def detect(cls, file_path: str) -> dict:
        """
        综合检测文件格式

        Args:
            file_path: 文件路径

        Returns:
            dict: {
                'extension': str,         # 扩展名
                'magic_format': str|None, # 魔数检测的格式名
                'magic_ext': str|None,    # 魔数检测的扩展名
                'is_encrypted': bool,     # 是否为加密格式
                'platform': str|None,     # 所属平台
                'confidence': str,        # 检测置信度: 'high'/'medium'/'low'
            }
        """
        ext = cls.detect_by_extension(file_path)
        magic_format, magic_ext = cls.detect_by_magic(file_path)

        result = {
            'extension': ext,
            'magic_format': magic_format,
            'magic_ext': magic_ext,
            'is_encrypted': False,
            'platform': None,
            'confidence': 'low',
        }

        # 加密格式扩展名集合
        encrypted_exts = {
            '.ncm': ('网易云音乐', 'NetEase'),
            '.qmc0': ('QQ音乐', 'QQ'),
            '.qmc2': ('QQ音乐', 'QQ'),
            '.qmc3': ('QQ音乐', 'QQ'),
            '.qmcflac': ('QQ音乐', 'QQ'),
            '.qmcogg': ('QQ音乐', 'QQ'),
            '.mflac': ('QQ音乐', 'QQ'),
            '.mflac0': ('QQ音乐', 'QQ'),
            '.mgg': ('QQ音乐', 'QQ'),
            '.mgg1': ('QQ音乐', 'QQ'),
            '.mggl': ('QQ音乐', 'QQ'),
            '.tkm': ('QQ音乐', 'QQ'),
            '.kgm': ('酷狗音乐', 'Kugou'),
            '.kgma': ('酷狗音乐', 'Kugou'),
            '.kwm': ('酷我音乐', 'Kuwo'),
            '.vpr': ('酷我VIP', 'Kuwo'),
            '.xm': ('喜马拉雅', 'Ximalaya'),
        }

        # 音频格式扩展名
        audio_exts = {'.mp3', '.flac', '.ogg', '.wav', '.aac', '.wma', '.m4a', '.ape', '.wv', '.opus'}

        # 优先使用魔数检测结果
        if magic_ext and magic_ext in encrypted_exts:
            result['is_encrypted'] = True
            result['platform'] = encrypted_exts[magic_ext][0]
            result['confidence'] = 'high'
            result['extension'] = magic_ext

        # 魔数检测到普通音频
        elif magic_ext and magic_ext in audio_exts:
            result['is_encrypted'] = False
            result['confidence'] = 'high'

        # 魔数检测到加密格式（如 NCM 的 CTENFDAM）
        elif magic_format:
            for eext, (eformat, eplatform) in encrypted_exts.items():
                if eformat == magic_format:
                    result['is_encrypted'] = True
                    result['platform'] = eformat
                    result['confidence'] = 'high'
                    result['extension'] = eext
                    break

        # 降级到扩展名判断
        elif ext:
            if ext in encrypted_exts:
                result['is_encrypted'] = True
                result['platform'] = encrypted_exts[ext][0]
                result['confidence'] = 'medium'
            elif ext in audio_exts:
                result['is_encrypted'] = False
                result['confidence'] = 'medium'

        # 特殊处理: DRM 加密的 .ogg 文件（文件头非 OggS）
        if ext == '.ogg' and not result['is_encrypted']:
            try:
                with open(file_path, 'rb') as f:
                    file_header = f.read(4)
                if file_header and len(file_header) >= 4 and file_header[:4] != b'OggS':
                    result['is_encrypted'] = True
                    result['platform'] = 'QQ音乐DRM'
                    result['confidence'] = 'medium'
            except (IOError, OSError):
                pass

        return result

    @classmethod
    def is_encrypted(cls, file_path: str) -> bool:
        """快速判断文件是否为加密音乐格式"""
        result = cls.detect(file_path)
        return result['is_encrypted']

    @classmethod
    def is_audio(cls, file_path: str) -> bool:
        """快速判断文件是否为音频文件（包括加密和普通）"""
        ext = cls.detect_by_extension(file_path)
        if ext is None:
            return False

        encrypted_exts = {
            '.ncm', '.qmc0', '.qmc2', '.qmc3', '.qmcflac', '.qmcogg',
            '.mflac', '.mflac0', '.mgg', '.mgg1', '.mggl', '.tkm',
            '.kgm', '.kgma', '.kwm', '.vpr', '.xm',
        }
        audio_exts = {'.mp3', '.flac', '.ogg', '.wav', '.aac', '.wma', '.m4a', '.ape', '.wv', '.opus'}

        return ext in encrypted_exts or ext in audio_exts

    @classmethod
    def get_platform_name(cls, file_path: str) -> str:
        """获取文件所属平台名称"""
        result = cls.detect(file_path)
        if result['platform']:
            return result['platform']
        ext = result.get('extension', os.path.splitext(file_path)[1].lower())
        return ext.upper().lstrip('.') if ext else '未知'