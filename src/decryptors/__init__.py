"""
解密器统一接口
自动发现和注册所有解密器，提供统一的解密入口
"""

import os
import logging
from typing import Optional, Dict, Type, List

from .base import BaseDecryptor, DecryptResult
from .ncm import NCMDecryptor
from .qmc import QMCDecryptor
from .kgm import KGMDecryptor
from .kwm import KWMDecryptor
from .vpr import VPRDecryptor
from .xm import XMDecryptor

# QQ音乐 DRM 解密器 (Frida 注入，可选依赖)
try:
    from .qq_ogg import QQOGGDecryptor
    _has_qq_ogg = True
except ImportError:
    _has_qq_ogg = False

logger = logging.getLogger(__name__)


class DecryptorRegistry:
    """解密器注册中心"""

    # 所有已注册的解密器
    _decryptors: List[Type[BaseDecryptor]] = [
        NCMDecryptor,
        QMCDecryptor,
        KGMDecryptor,
        KWMDecryptor,
        VPRDecryptor,
        XMDecryptor,
    ] + ([QQOGGDecryptor] if _has_qq_ogg else [])

    # 扩展名到解密器的映射（运行时构建）
    _ext_map: Optional[Dict[str, Type[BaseDecryptor]]] = None

    # 魔数到解密器的映射（运行时构建）
    _magic_map: Optional[Dict[bytes, Type[BaseDecryptor]]] = None

    @classmethod
    def _build_maps(cls):
        """构建映射表"""
        if cls._ext_map is not None:
            return

        cls._ext_map = {}
        cls._magic_map = {}

        for decryptor_cls in cls._decryptors:
            # 注册扩展名映射
            for ext in decryptor_cls.EXTENSIONS:
                if ext in cls._ext_map:
                    logger.warning(f"扩展名 {ext} 已被 {cls._ext_map[ext].FORMAT_NAME} 注册，"
                                   f"被 {decryptor_cls.FORMAT_NAME} 覆盖")
                cls._ext_map[ext] = decryptor_cls

            # 注册魔数映射
            for magic in decryptor_cls.MAGIC_SIGNATURES:
                cls._magic_map[magic] = decryptor_cls

    @classmethod
    def get_decryptor_by_ext(cls, ext: str) -> Optional[Type[BaseDecryptor]]:
        """通过扩展名获取解密器"""
        cls._build_maps()
        return cls._ext_map.get(ext.lower())

    @classmethod
    def get_decryptor_by_magic(cls, file_path: str) -> Optional[Type[BaseDecryptor]]:
        """通过文件头魔数获取解密器"""
        cls._build_maps()
        try:
            with open(file_path, 'rb') as f:
                header = f.read(32)
        except (IOError, OSError):
            return None

        if not header:
            return None

        for magic, decryptor_cls in cls._magic_map.items():
            if header[:len(magic)] == magic:
                return decryptor_cls

        return None

    @classmethod
    def _is_encrypted_ogg(cls, file_path: str) -> bool:
        """
        检测 .ogg 文件是否为 DRM 加密格式。
        普通 OGG 以 'OggS' 开头，加密的则不是。
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
            return header[:4] != b'OggS'
        except (IOError, OSError):
            return False

    @classmethod
    def get_decryptor(cls, file_path: str) -> Optional[Type[BaseDecryptor]]:
        """
        自动识别并获取合适的解密器
        优先使用魔数识别，降级使用扩展名

        Args:
            file_path: 文件路径

        Returns:
            解密器类 或 None
        """
        # 优先魔数识别
        decryptor = cls.get_decryptor_by_magic(file_path)
        if decryptor is not None:
            return decryptor

        # 特殊处理: 加密的 .ogg 文件（不以 OggS 开头）
        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.ogg' and _has_qq_ogg:
            if cls._is_encrypted_ogg(file_path):
                return QQOGGDecryptor
            # 普通 OGG 文件，不需要解密
            return None

        # 降级到扩展名
        return cls.get_decryptor_by_ext(ext)

    @classmethod
    def get_all_extensions(cls) -> set:
        """获取所有支持的加密格式扩展名"""
        cls._build_maps()
        return set(cls._ext_map.keys())

    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """检查文件是否为支持的加密格式"""
        ext = os.path.splitext(file_path)[1].lower()
        cls._build_maps()
        return ext in cls._ext_map

    @classmethod
    def get_format_name(cls, file_path: str) -> str:
        """获取文件格式的友好名称"""
        decryptor = cls.get_decryptor(file_path)
        if decryptor:
            return decryptor.FORMAT_NAME
        ext = os.path.splitext(file_path)[1].lower()
        return ext.upper().lstrip('.') if ext else '未知格式'

    @classmethod
    def register(cls, decryptor_cls: Type[BaseDecryptor]):
        """注册新的解密器（用于插件热加载）"""
        if decryptor_cls not in cls._decryptors:
            cls._decryptors.append(decryptor_cls)
            # 重建映射
            cls._ext_map = None
            cls._magic_map = None
            logger.info(f"注册解密器: {decryptor_cls.FORMAT_NAME}")


# 需要 Frida 降级重试的扩展名（新版 DRM 加密的 QQ 音乐格式）
_QMC_EXTENSIONS_NEEDING_FRIDA = {'.mgg', '.mgg1', '.mggl', '.mflac', '.mflac0'}


def decrypt_file(input_path: str, output_path: Optional[str] = None,
                 output_format: str = 'mp3') -> DecryptResult:
    """
    统一解密入口函数

    自动识别文件格式并调用对应的解密器。
    对于普通音频文件（无需解密），直接复制到输出路径。
    当 QMC 解密器对 .mgg/.mflac 等格式失败时，自动尝试 Frida 注入方案。

    Args:
        input_path: 输入文件路径
        output_path: 输出文件路径 (None 则自动生成)
        output_format: 输出格式 ('mp3', 'flac', 'ogg')

    Returns:
        DecryptResult 对象

    Raises:
        ValueError: 不支持的文件格式
        FileNotFoundError: 文件不存在
    """
    if not os.path.isfile(input_path):
        raise FileNotFoundError(f"文件不存在: {input_path}")

    decryptor_cls = DecryptorRegistry.get_decryptor(input_path)
    if decryptor_cls is None:
        # 检查是否为普通音频文件（无需解密）
        ext = os.path.splitext(input_path)[1].lower()
        audio_exts = {'.mp3', '.flac', '.ogg', '.wav', '.aac', '.wma', '.m4a', '.ape', '.wv', '.opus'}
        if ext in audio_exts:
            # 普通音频文件，直接复制
            if output_path is None:
                base = os.path.splitext(input_path)[0]
                output_path = f"{base}.{output_format}"
            import shutil
            shutil.copy2(input_path, output_path)
            logger.info(f"普通音频文件，直接复制: {output_path}")
            return DecryptResult(
                audio_path=output_path,
                source_format="普通音频",
                detected_type=BaseDecryptor._detect_audio_type(open(input_path, 'rb').read(4)),
            )
        raise ValueError(f"不支持的加密格式: {ext}")

    logger.info(f"使用 {decryptor_cls.FORMAT_NAME} 解密器处理: {input_path}")

    try:
        return decryptor_cls.decrypt_file(input_path, output_path, output_format)
    except RuntimeError as e:
        # QMC 解密失败时，尝试 Frida 降级方案
        ext = os.path.splitext(input_path)[1].lower()
        if ext in _QMC_EXTENSIONS_NEEDING_FRIDA and _has_qq_ogg:
            logger.warning(f"{decryptor_cls.FORMAT_NAME} 解密失败: {e}")
            logger.info(f"尝试使用 QQ音乐 DRM (Frida) 解密器处理: {input_path}")
            try:
                result = QQOGGDecryptor.decrypt_file(input_path, output_path, output_format)
                return result
            except Exception as frida_err:
                # Frida 也失败了，抛出包含两种错误信息的异常
                raise RuntimeError(
                    f"解密失败:\n"
                    f"  1) QMC 解密: {e}\n"
                    f"  2) Frida DRM 解密: {frida_err}\n"
                    f"请确保 QQ 音乐客户端正在运行，且已安装 frida (pip install frida frida-tools)"
                )
        else:
            # 非 QMC 格式或 Frida 不可用，直接抛出原始错误
            raise


# 导出公共接口
__all__ = [
    'BaseDecryptor',
    'DecryptResult',
    'DecryptorRegistry',
    'decrypt_file',
    'NCMDecryptor',
    'QMCDecryptor',
    'KGMDecryptor',
    'KWMDecryptor',
    'VPRDecryptor',
    'XMDecryptor',
] + (['QQOGGDecryptor'] if _has_qq_ogg else [])
