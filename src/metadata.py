"""
元数据管理器
统一处理 ID3 标签写入、歌词嵌入、封面图片处理
支持 MP3 (ID3v2)、FLAC (Vorbis Comments)、OGG (Vorbis Comments)
"""

import os
import logging
import tempfile
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class MetadataManager:
    """元数据管理器"""

    @staticmethod
    def detect_cover_mime(cover_data: bytes) -> str:
        """检测封面图片 MIME 类型"""
        if not cover_data or len(cover_data) < 4:
            return "image/jpeg"
        if cover_data[:3] == b'\xFF\xD8\xFF':
            return "image/jpeg"
        if cover_data[:8] == b'\x89PNG\r\n\x1a\n':
            return "image/png"
        if cover_data[:4] == b'RIFF' and len(cover_data) > 12 and cover_data[8:12] == b'WEBP':
            return "image/webp"
        if cover_data[:4] == b'GIF8':
            return "image/gif"
        return "image/jpeg"

    @staticmethod
    def write_mp3_metadata(file_path: str, metadata: Optional[Dict[str, Any]] = None,
                           cover_data: Optional[bytes] = None,
                           cover_mime: str = "image/jpeg",
                           lyrics: Optional[str] = None) -> bool:
        """
        为 MP3 文件写入 ID3v2 标签

        Args:
            file_path: MP3 文件路径
            metadata: 元数据字典 (title, artist, album, genre, date, track)
            cover_data: 封面图片二进制数据
            cover_mime: 封面 MIME 类型
            lyrics: 歌词文本 (LRC 格式)

        Returns:
            是否成功
        """
        try:
            from mutagen.mp3 import MP3
            from mutagen.id3 import (
                ID3, TIT2, TPE1, TALB, TCON, TDRC, TRCK,
                APIC, USLT, ID3NoHeaderError
            )
        except ImportError:
            logger.warning("mutagen 未安装，无法写入元数据")
            return False

        try:
            audio = MP3(file_path)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()

        if audio.tags is None:
            audio.add_tags()

        tags = audio.tags

        # 写入文本元数据
        if metadata:
            if metadata.get('title'):
                tags.delall('TIT2')
                tags.add(TIT2(encoding=3, text=str(metadata['title'])))

            if metadata.get('artist'):
                tags.delall('TPE1')
                tags.add(TPE1(encoding=3, text=str(metadata['artist'])))

            if metadata.get('album'):
                tags.delall('TALB')
                tags.add(TALB(encoding=3, text=str(metadata['album'])))

            if metadata.get('genre'):
                tags.delall('TCON')
                tags.add(TCON(encoding=3, text=str(metadata['genre'])))

            if metadata.get('date'):
                tags.delall('TDRC')
                tags.add(TDRC(encoding=3, text=str(metadata['date'])))

            if metadata.get('track'):
                tags.delall('TRCK')
                tags.add(TRCK(encoding=3, text=str(metadata['track'])))

        # 写入封面
        if cover_data:
            actual_mime = cover_mime if cover_mime != "image/jpeg" else MetadataManager.detect_cover_mime(cover_data)
            tags.delall('APIC')
            tags.add(APIC(
                encoding=3,
                mime=actual_mime,
                type=3,  # 封面 (前)
                desc='Cover',
                data=cover_data
            ))

        # 写入歌词 (USLT)
        if lyrics:
            tags.delall('USLT')
            tags.add(USLT(
                encoding=3,
                lang='eng',
                desc='',
                text=lyrics
            ))

        audio.save()
        logger.info(f"元数据写入完成: {file_path}")
        return True

    @staticmethod
    def write_flac_metadata(file_path: str, metadata: Optional[Dict[str, Any]] = None,
                            cover_data: Optional[bytes] = None,
                            lyrics: Optional[str] = None) -> bool:
        """
        为 FLAC 文件写入 Vorbis Comments 标签

        Args:
            file_path: FLAC 文件路径
            metadata: 元数据字典
            cover_data: 封面图片数据
            lyrics: 歌词

        Returns:
            是否成功
        """
        try:
            from mutagen.flac import FLAC, Picture
        except ImportError:
            logger.warning("mutagen 未安装，无法写入元数据")
            return False

        try:
            audio = FLAC(file_path)
        except Exception as e:
            logger.error(f"无法打开 FLAC 文件: {e}")
            return False

        if metadata:
            if metadata.get('title'):
                audio['TITLE'] = str(metadata['title'])
            if metadata.get('artist'):
                audio['ARTIST'] = str(metadata['artist'])
            if metadata.get('album'):
                audio['ALBUM'] = str(metadata['album'])
            if metadata.get('genre'):
                audio['GENRE'] = str(metadata['genre'])
            if metadata.get('date'):
                audio['DATE'] = str(metadata['date'])
            if metadata.get('track'):
                audio['TRACKNUMBER'] = str(metadata['track'])

        if lyrics:
            audio['LYRICS'] = lyrics

        if cover_data:
            pic = Picture()
            pic.type = 3
            pic.mime = MetadataManager.detect_cover_mime(cover_data)
            pic.data = cover_data
            audio.clear_pictures()
            audio.add_picture(pic)

        audio.save()
        logger.info(f"FLAC 元数据写入完成: {file_path}")
        return True

    @classmethod
    def write_metadata(cls, file_path: str, metadata: Optional[Dict[str, Any]] = None,
                       cover_data: Optional[bytes] = None,
                       cover_mime: str = "image/jpeg",
                       lyrics: Optional[str] = None) -> bool:
        """
        自动检测格式并写入元数据

        Args:
            file_path: 音频文件路径
            metadata: 元数据字典
            cover_data: 封面图片数据
            cover_mime: 封面 MIME 类型
            lyrics: 歌词

        Returns:
            是否成功
        """
        ext = os.path.splitext(file_path)[1].lower()

        if ext == '.mp3':
            return cls.write_mp3_metadata(file_path, metadata, cover_data, cover_mime, lyrics)
        elif ext == '.flac':
            return cls.write_flac_metadata(file_path, metadata, cover_data, lyrics)
        else:
            # 对于其他格式，尝试通过 ffmpeg 写入
            logger.info(f"格式 {ext} 不直接支持元数据写入，将通过 ffmpeg 处理")
            return False

    @staticmethod
    def export_lyrics(lyrics: str, output_path: str) -> bool:
        """
        导出歌词为 .lrc 文件

        Args:
            lyrics: 歌词内容
            output_path: 输出路径

        Returns:
            是否成功
        """
        try:
            os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(lyrics)
            logger.info(f"歌词已导出: {output_path}")
            return True
        except Exception as e:
            logger.error(f"歌词导出失败: {e}")
            return False

    @staticmethod
    def read_audio_metadata(file_path: str) -> Optional[Dict[str, Any]]:
        """
        从音频文件读取元数据（标题、歌手、专辑、比特率等）

        Args:
            file_path: 音频文件路径

        Returns:
            元数据字典，失败返回 None
        """
        ext = os.path.splitext(file_path)[1].lower()
        try:
            if ext == '.mp3':
                from mutagen.mp3 import MP3
                audio = MP3(file_path)
                if audio.tags is None:
                    return None
                tags = audio.tags
                return {
                    'title': str(tags.get('TIT2', '')) if tags.get('TIT2') else '',
                    'artist': str(tags.get('TPE1', '')) if tags.get('TPE1') else '',
                    'album': str(tags.get('TALB', '')) if tags.get('TALB') else '',
                    'genre': str(tags.get('TCON', '')) if tags.get('TCON') else '',
                    'date': str(tags.get('TDRC', '')) if tags.get('TDRC') else '',
                    'bitrate': int(audio.info.bitrate / 1000) if audio.info else 0,
                    'sample_rate': audio.info.sample_rate if audio.info else 0,
                    'channels': audio.info.channels if audio.info else 0,
                    'duration': audio.info.length if audio.info else 0,
                }
            elif ext == '.flac':
                from mutagen.flac import FLAC
                audio = FLAC(file_path)
                return {
                    'title': audio.get('TITLE', [''])[0],
                    'artist': audio.get('ARTIST', [''])[0],
                    'album': audio.get('ALBUM', [''])[0],
                    'genre': audio.get('GENRE', [''])[0],
                    'date': audio.get('DATE', [''])[0],
                    'bitrate': int(audio.info.bitrate / 1000) if audio.info else 0,
                    'sample_rate': audio.info.sample_rate if audio.info else 0,
                    'channels': audio.info.channels if audio.info else 0,
                    'duration': audio.info.length if audio.info else 0,
                }
            else:
                # 通用方式：尝试通过文件内容识别格式
                # 先按扩展名尝试，失败则用 mutagen 自动识别
                try:
                    from mutagen import File as MutagenFile
                    audio = MutagenFile(file_path)
                except Exception:
                    # 扩展名不被识别时，尝试通过文件头判断格式
                    try:
                        with open(file_path, 'rb') as f:
                            header = f.read(32)
                        if header[:4] == b'OggS':
                            from mutagen.oggvorbis import OggVorbis
                            audio = OggVorbis(file_path)
                        elif header[:4] == b'fLaC':
                            from mutagen.flac import FLAC
                            audio = FLAC(file_path)
                        elif header[:3] == b'ID3' or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
                            from mutagen.mp3 import MP3
                            audio = MP3(file_path)
                        else:
                            return None
                    except Exception:
                        return None

                if audio is None or audio.tags is None:
                    return None

                # 提取元数据（兼容 ID3 和 Vorbis Comments 两种标签格式）
                tags = audio.tags

                def _get_tag(tag_keys):
                    """从标签中提取值，兼容 ID3 对象和 Vorbis 列表两种格式"""
                    for key in tag_keys:
                        val = tags.get(key)
                        if val is None:
                            continue
                        # ID3 标签返回对象，有 .text 属性
                        if hasattr(val, 'text'):
                            texts = val.text
                            if texts:
                                return str(texts[0]) if hasattr(texts, '__getitem__') else str(texts)
                        # Vorbis Comments 返回列表
                        elif hasattr(val, '__getitem__') and not isinstance(val, str):
                            return str(val[0])
                        # 字符串值
                        elif isinstance(val, str) and val:
                            return val
                    return ''

                result = {
                    'title': _get_tag(['TIT2', 'TITLE']),
                    'artist': _get_tag(['TPE1', 'ARTIST']),
                    'album': _get_tag(['TALB', 'ALBUM']),
                    'genre': _get_tag(['TCON', 'GENRE']),
                    'date': _get_tag(['TDRC', 'DATE']),
                    'bitrate': int(audio.info.bitrate / 1000) if audio.info else 0,
                    'sample_rate': audio.info.sample_rate if audio.info else 0,
                    'channels': audio.info.channels if audio.info else 0,
                    'duration': audio.info.length if audio.info else 0,
                }
                return result
        except Exception as e:
            logger.debug(f"读取元数据失败: {file_path} - {e}")
            return None

    @staticmethod
    def scan_directory_metadata(directory: str) -> Dict[str, list]:
        """
        扫描目录中所有音频文件的元数据，建立以 (title, artist) 为键的索引。

        Args:
            directory: 目录路径

        Returns:
            字典: {(title, artist): [file_info, ...]}
            每个 file_info 包含: {'path': str, 'bitrate': int, 'format': str}
        """
        index = {}
        if not directory or not os.path.isdir(directory):
            return index

        audio_exts = {'.mp3', '.flac', '.ogg', '.wav', '.aac', '.m4a', '.ape', '.wv', '.opus'}
        for root_dir, dirs, files in os.walk(directory):
            for filename in files:
                ext = os.path.splitext(filename)[1].lower()
                if ext not in audio_exts:
                    continue
                file_path = os.path.join(root_dir, filename)
                meta = MetadataManager.read_audio_metadata(file_path)
                if meta and meta.get('title') and meta.get('artist'):
                    key = (meta['title'].strip().lower(), meta['artist'].strip().lower())
                    if key not in index:
                        index[key] = []
                    index[key].append({
                        'path': file_path,
                        'bitrate': meta.get('bitrate', 0),
                        'format': ext.lstrip('.'),
                        'filename': filename,
                    })
        return index

    @staticmethod
    def find_duplicate(title: str, artist: str, directory: str,
                       output_format: str = 'mp3') -> Optional[Dict[str, Any]]:
        """
        在目标目录中查找已存在的同名歌曲。

        Args:
            title: 歌曲标题
            artist: 歌手名
            directory: 输出目录
            output_format: 输出格式

        Returns:
            匹配的文件信息字典，无匹配返回 None
        """
        if not title or not artist or not directory:
            return None

        index = MetadataManager.scan_directory_metadata(directory)
        key = (title.strip().lower(), artist.strip().lower())
        matches = index.get(key, [])

        for match in matches:
            if match['format'] == output_format:
                return match

        return None

    @staticmethod
    def build_filename(template: str, metadata: Dict[str, Any],
                       index: int = 0, fallback_name: str = "未知") -> str:
        """
        根据模板构建文件名

        支持的变量:
            {歌手} / {artist} - 歌手名
            {歌名} / {title} - 歌名
            {专辑} / {album} - 专辑名
            {序号} / {index} - 序号
            {年份} / {year} - 年份
            {流派} / {genre} - 流派

        Args:
            template: 文件名模板
            metadata: 元数据字典
            index: 序号
            fallback_name: 元数据缺失时的默认名

        Returns:
            格式化后的文件名（不含扩展名）
        """
        # 构建替换字典
        replacements = {
            '{歌手}': metadata.get('artist', '') or fallback_name,
            '{artist}': metadata.get('artist', '') or fallback_name,
            '{歌名}': metadata.get('title', '') or fallback_name,
            '{title}': metadata.get('title', '') or fallback_name,
            '{专辑}': metadata.get('album', '') or '未知专辑',
            '{album}': metadata.get('album', '') or '未知专辑',
            '{序号}': str(index).zfill(2),
            '{index}': str(index).zfill(2),
            '{年份}': metadata.get('date', '') or '未知',
            '{year}': metadata.get('date', '') or '未知',
            '{流派}': metadata.get('genre', '') or '未知',
            '{genre}': metadata.get('genre', '') or '未知',
        }

        result = template
        for key, value in replacements.items():
            result = result.replace(key, value)

        # 清理非法文件名字符
        illegal_chars = '<>:"/\\|?*'
        for ch in illegal_chars:
            result = result.replace(ch, '_')

        # 清理连续的空格和点
        result = result.replace('  ', ' ').strip('. ')

        return result if result else fallback_name