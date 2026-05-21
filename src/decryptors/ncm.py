"""
网易云音乐 .ncm 格式解密器
支持完整元数据提取（歌名、歌手、专辑、封面、歌词）
"""

import os
import json
import base64
import struct
import logging
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class NCMDecryptor(BaseDecryptor):
    """网易云音乐 .ncm 格式解密器"""

    FORMAT_NAME = "网易云音乐"
    EXTENSIONS = ['.ncm']
    MAGIC_SIGNATURES = [b'CTENFDAM']

    # NCM 使用 AES-128-ECB 解密
    CORE_KEY = b'\x68\x7A\x48\x52\x41\x6D\x73\x6F\x35\x6B\x49\x6E\x62\x61\x78\x57'
    META_KEY = b'\x23\x31\x34\x6C\x6A\x6B\x5F\x21\x5C\x5D\x26\x30\x55\x3C\x27\x28'
    MAGIC_HEADER = b'CTENFDAM'

    @staticmethod
    def _create_key_box(key: bytes) -> list:
        """创建 RC4 密钥盒"""
        key_length = len(key)
        box = list(range(256))
        j = 0
        for i in range(256):
            j = (box[i] + j + key[i % key_length]) & 0xFF
            box[i], box[j] = box[j], box[i]
        return box

    @classmethod
    def _aes_ecb_decrypt(cls, data: bytes, key: bytes) -> bytes:
        """AES-128-ECB 解密"""
        from Crypto.Cipher import AES
        cipher = AES.new(key, AES.MODE_ECB)
        return cipher.decrypt(data)

    @classmethod
    def _unpad(cls, data: bytes) -> bytes:
        """移除 PKCS7 填充"""
        if not data:
            return data
        pad_len = data[-1]
        if pad_len < 1 or pad_len > 16:
            return data
        if all(b == pad_len for b in data[-pad_len:]):
            return data[:-pad_len]
        return data

    @classmethod
    def _parse_metadata(cls, meta_json: dict) -> dict:
        """从 NCM 元数据 JSON 中提取标准化元数据"""
        music_meta = meta_json.get('music', {})
        metadata = {}

        # 歌名
        song_name = music_meta.get('songName', '')
        if song_name:
            metadata['title'] = song_name

        # 歌手 (NCM 格式: [[name, id], ...])
        artists = music_meta.get('artist', [])
        if artists:
            artist_names = []
            for a in artists:
                if isinstance(a, (list, tuple)) and len(a) > 0:
                    artist_names.append(str(a[0]))
                elif isinstance(a, str):
                    artist_names.append(a)
            if artist_names:
                metadata['artist'] = ', '.join(artist_names)

        # 专辑
        album_name = music_meta.get('album', '')
        if album_name:
            metadata['album'] = album_name

        # 流派
        genre = music_meta.get('genre', '')
        if genre:
            metadata['genre'] = genre

        # 发行年份
        year = music_meta.get('year', '') or music_meta.get('publishTime', '')
        if year:
            if isinstance(year, (int, float)) and year > 0:
                # 时间戳转年份
                import datetime
                try:
                    metadata['date'] = datetime.datetime.fromtimestamp(year / 1000).strftime('%Y')
                except (OSError, ValueError):
                    metadata['date'] = str(year)
            elif isinstance(year, str) and year:
                metadata['date'] = year

        # 比特率信息
        bitrate = music_meta.get('bitrate', 0)
        if bitrate:
            metadata['bitrate'] = bitrate

        # 时长
        duration = music_meta.get('duration', 0)
        if duration:
            metadata['duration'] = duration

        return metadata

    @classmethod
    def _parse_lyrics(cls, meta_json: dict) -> Optional[str]:
        """尝试从元数据中提取歌词"""
        music_meta = meta_json.get('music', {})
        # 有些 NCM 文件在元数据中嵌入歌词
        lyrics = music_meta.get('lyrics', '') or meta_json.get('lyric', '')
        if lyrics and isinstance(lyrics, str) and lyrics.strip():
            return lyrics
        return None

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        解密 .ncm 文件

        Args:
            input_path: 输入的 .ncm 文件路径
            output_path: 输出文件路径
            output_format: 输出格式 ('mp3', 'flac', 'ogg')

        Returns:
            DecryptResult 对象
        """
        if output_path is None:
            output_path = cls._auto_output_path(input_path, output_format)

        with open(input_path, 'rb') as f:
            # 检查魔数头
            header = f.read(8)
            if not header.startswith(cls.MAGIC_HEADER):
                raise ValueError(f"不是有效的NCM文件: {input_path}")

            # 跳过 gap
            f.read(2)

            # 读取 key 数据长度
            key_length = struct.unpack('<I', f.read(4))[0]
            key_data = bytearray(f.read(key_length))

            # XOR 0x64 解密 key_data
            for i in range(len(key_data)):
                key_data[i] ^= 0x64

            # AES 解密 key_data
            key_data = cls._aes_ecb_decrypt(bytes(key_data), cls.CORE_KEY)
            key_data = cls._unpad(key_data)

            # 跳过 "neteasecloudmusic" 前缀 (17 bytes)
            key_data = key_data[17:]

            # 创建 key_box
            key_box = cls._create_key_box(key_data)

            # 读取 meta 数据长度
            meta_length = struct.unpack('<I', f.read(4))[0]
            meta_data = bytearray(f.read(meta_length))

            # XOR 0x63 解密 meta_data
            for i in range(len(meta_data)):
                meta_data[i] ^= 0x63

            # Base64 解码
            meta_data = base64.b64decode(bytes(meta_data[22:]))

            # AES 解密 meta_data
            meta_data = cls._aes_ecb_decrypt(meta_data, cls.META_KEY)
            meta_data = cls._unpad(meta_data)

            # 跳过 "music:" 前缀 (6 bytes) 获取 JSON 元数据
            meta_json_str = meta_data[6:]
            metadata = {}
            lyrics = None
            try:
                meta_json = json.loads(meta_json_str)
                metadata = cls._parse_metadata(meta_json)
                lyrics = cls._parse_lyrics(meta_json)
                logger.info(f"歌曲信息: {metadata.get('title', '未知')} - {metadata.get('artist', '未知')}")
            except (json.JSONDecodeError, IndexError) as e:
                logger.warning(f"无法解析元数据: {e}")

            # 跳过 CRC32 和间隔
            f.read(4)  # crc32
            f.read(5)  # gap

            # 读取封面图片
            image_size = struct.unpack('<I', f.read(4))[0]
            cover_data = None
            cover_mime = "image/jpeg"
            if image_size > 0:
                cover_data = f.read(image_size)
                cover_mime = cls._detect_cover_mime(cover_data)
                logger.info(f"发现封面图片 ({len(cover_data)} bytes, {cover_mime})")

            # 解密音频数据
            audio_data = bytearray()
            while True:
                chunk = f.read(0x8000)
                if not chunk:
                    break
                chunk = bytearray(chunk)
                for i in range(len(chunk)):
                    j = (i + 1) & 0xFF
                    chunk[i] ^= key_box[(key_box[j] + key_box[(key_box[j] + j) & 0xFF]) & 0xFF]
                audio_data.extend(chunk)

            # 检测解密后的音频类型
            detected_type = cls._detect_audio_type(bytes(audio_data[:32]))

            # 如果检测到的类型与目标格式匹配，直接输出
            if detected_type and detected_type == output_format:
                with open(output_path, 'wb') as out:
                    out.write(audio_data)
            else:
                # 写入临时文件，后续由 converter 处理
                with open(output_path, 'wb') as out:
                    out.write(audio_data)

            logger.info(f"解密完成: {output_path} (内部格式: {detected_type})")

            return DecryptResult(
                audio_path=output_path,
                cover_data=cover_data,
                cover_mime=cover_mime,
                metadata=metadata,
                lyrics=lyrics,
                source_format=cls.FORMAT_NAME,
                detected_type=detected_type,
            )