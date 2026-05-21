"""
音频转换模块 (v2.0)
支持 MP3/FLAC 输出、高级音频参数（CBR/VBR、采样率、声道）
"""

import os
import logging
import shutil
import subprocess

logger = logging.getLogger(__name__)


def _find_ffmpeg():
    """查找 ffmpeg 路径"""
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        if ffmpeg_path and os.path.isfile(ffmpeg_path):
            return ffmpeg_path
    except ImportError:
        pass
    except Exception:
        pass

    ffmpeg_path = shutil.which('ffmpeg')
    if ffmpeg_path:
        return ffmpeg_path

    common_paths = [
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe',
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p

    conda_base = os.environ.get('CONDA_PREFIX', '')
    if conda_base:
        conda_paths = [
            os.path.join(conda_base, 'Library', 'bin', 'ffmpeg.exe'),
            os.path.join(conda_base, 'bin', 'ffmpeg.exe'),
        ]
        for p in conda_paths:
            if os.path.isfile(p):
                return p

    miniconda_paths = [
        os.path.join(os.path.expanduser('~'), 'miniconda3', 'Library', 'bin', 'ffmpeg.exe'),
        os.path.join(os.path.expanduser('~'), 'miniconda3', 'bin', 'ffmpeg.exe'),
        os.path.join(os.path.expanduser('~'), 'anaconda3', 'Library', 'bin', 'ffmpeg.exe'),
    ]
    for p in miniconda_paths:
        if os.path.isfile(p):
            return p

    pkgs_base = os.path.join(os.path.expanduser('~'), 'miniconda3', 'pkgs')
    if os.path.isdir(pkgs_base):
        ffmpeg_dirs = sorted(
            [d for d in os.listdir(pkgs_base) if d.startswith('ffmpeg-')],
            reverse=True
        )
        for d in ffmpeg_dirs:
            ffmpeg_exe = os.path.join(pkgs_base, d, 'Library', 'bin', 'ffmpeg.exe')
            if os.path.isfile(ffmpeg_exe):
                return ffmpeg_exe
    return None


FFMPEG_PATH = _find_ffmpeg()


class AudioConverter:
    """音频格式转换器 (v2.0)"""

    AUDIO_EXTENSIONS = {'.mp3', '.flac', '.ogg', '.wav', '.aac', '.wma', '.m4a', '.ape', '.wv', '.opus'}

    FORMAT_SIGNATURES = {
        'mp3': [b'ID3', bytes([0xFF, 0xFB]), bytes([0xFF, 0xF3]), bytes([0xFF, 0xF2])],
        'flac': [b'fLaC'],
        'ogg': [b'OggS'],
        'wav': [b'RIFF'],
        'aac': [b'\xFF\xF1', b'\xFF\xF9'],
        'm4a': [b'\x00\x00\x00', b'ftyp'],
        'ape': [b'MAC '],
    }

    @staticmethod
    def detect_format(file_path: str):
        """检测音频文件格式"""
        with open(file_path, 'rb') as f:
            header = f.read(32)
        if not header or len(header) < 2:
            return None
        for fmt, signatures in AudioConverter.FORMAT_SIGNATURES.items():
            for sig in signatures:
                if header[:len(sig)] == sig:
                    return fmt
        if header[:3] == b'ID3':
            return 'mp3'
        if header[0] == 0xFF and (header[1] & 0xE0) == 0xE0:
            return 'mp3'
        if b'ftyp' in header[:32]:
            return 'm4a'
        return None

    @classmethod
    def convert_to_mp3(cls, input_path: str, output_path: str = None,
                       bitrate: str = '320k', cover_data: bytes = None,
                       metadata: dict = None, progress_callback=None,
                       sample_rate: int = None, channels: int = None,
                       mode: str = 'cbr'):
        """
        将音频文件转换为 MP3

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            bitrate: 比特率 (默认 320k)
            cover_data: 封面图片数据
            metadata: 元数据字典
            progress_callback: 进度回调
            sample_rate: 采样率 (None 则保持源采样率)
            channels: 声道数 (None 则保持源声道)
            mode: 'cbr' 或 'vbr'
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        if output_path is None:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}.mp3"

        source_format = cls.detect_format(input_path)
        logger.info(f"检测到源格式: {source_format or '未知'}")

        if FFMPEG_PATH:
            return cls._convert_with_ffmpeg(
                input_path, output_path, bitrate, cover_data, metadata,
                progress_callback, sample_rate, channels, mode
            )
        return cls._convert_with_pydub(
            input_path, output_path, bitrate, cover_data, metadata,
            progress_callback
        )

    @classmethod
    def convert_to_flac(cls, input_path: str, output_path: str = None,
                        cover_data: bytes = None, metadata: dict = None,
                        progress_callback=None):
        """
        将音频文件转换为 FLAC

        Args:
            input_path: 输入文件路径
            output_path: 输出文件路径
            cover_data: 封面图片数据
            metadata: 元数据字典
            progress_callback: 进度回调
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")
        if output_path is None:
            base = os.path.splitext(input_path)[0]
            output_path = f"{base}.flac"

        if FFMPEG_PATH:
            return cls._convert_flac_ffmpeg(
                input_path, output_path, cover_data, metadata, progress_callback
            )
        return cls._convert_flac_pydub(
            input_path, output_path, cover_data, metadata, progress_callback
        )

    @classmethod
    def _convert_with_ffmpeg(cls, input_path, output_path, bitrate,
                              cover_data, metadata, progress_callback,
                              sample_rate=None, channels=None, mode='cbr'):
        """使用 ffmpeg 转换为 MP3"""
        cmd = [FFMPEG_PATH, '-y', '-i', input_path]

        # 音频编码参数
        cmd.extend(['-codec:a', 'libmp3lame'])

        if mode == 'vbr':
            # VBR 模式: 使用 -q:a (0=最高质量, 9=最低质量)
            quality_map = {'320k': '0', '256k': '2', '192k': '4', '128k': '6'}
            cmd.extend(['-q:a', quality_map.get(bitrate, '0')])
        else:
            # CBR 模式
            cmd.extend(['-b:a', bitrate])

        # 采样率
        if sample_rate:
            cmd.extend(['-ar', str(sample_rate)])

        # 声道数
        if channels:
            cmd.extend(['-ac', str(channels)])

        # 元数据
        if metadata:
            if metadata.get('title'):
                cmd.extend(['-metadata', f'title={metadata["title"]}'])
            if metadata.get('artist'):
                cmd.extend(['-metadata', f'artist={metadata["artist"]}'])
            if metadata.get('album'):
                cmd.extend(['-metadata', f'album={metadata["album"]}'])
            if metadata.get('genre'):
                cmd.extend(['-metadata', f'genre={metadata["genre"]}'])
            if metadata.get('date'):
                cmd.extend(['-metadata', f'date={metadata["date"]}'])

        # 封面
        temp_cover = None
        if cover_data:
            import tempfile
            temp_cover = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            temp_cover.write(cover_data)
            temp_cover.close()
            cmd = [
                FFMPEG_PATH, '-y',
                '-i', input_path,
                '-i', temp_cover.name,
                '-map', '0:a', '-map', '1:0',
                '-codec:a', 'libmp3lame',
                '-codec:v', 'mjpeg',
                '-disposition:v', 'attached_pic',
            ]
            if mode == 'vbr':
                quality_map = {'320k': '0', '256k': '2', '192k': '4', '128k': '6'}
                cmd.extend(['-q:a', quality_map.get(bitrate, '0')])
            else:
                cmd.extend(['-b:a', bitrate])
            if sample_rate:
                cmd.extend(['-ar', str(sample_rate)])
            if channels:
                cmd.extend(['-ac', str(channels)])
            if metadata:
                for key in ('title', 'artist', 'album', 'genre', 'date'):
                    if metadata.get(key):
                        cmd.extend(['-metadata', f'{key}={metadata[key]}'])

        cmd.append(output_path)

        try:
            if progress_callback:
                progress_callback(10)
            logger.debug(f"执行 ffmpeg 命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if progress_callback:
                progress_callback(90)
            if result.returncode != 0:
                stderr_text = result.stderr or ''
                stdout_text = result.stdout or ''
                error_detail = stderr_text.strip() or stdout_text.strip() or '(无错误输出)'
                logger.error(f"ffmpeg 错误 (返回码={result.returncode}): {error_detail}")
                if cover_data:
                    logger.info("尝试不嵌入封面重新转换...")
                    cmd_simple = [
                        FFMPEG_PATH, '-y', '-i', input_path,
                        '-codec:a', 'libmp3lame', '-b:a', bitrate,
                        output_path
                    ]
                    result2 = subprocess.run(cmd_simple, capture_output=True, text=True, timeout=300)
                    if result2.returncode != 0:
                        stderr2 = result2.stderr or ''
                        stdout2 = result2.stdout or ''
                        detail2 = stderr2.strip() or stdout2.strip() or '(无错误输出)'
                        raise RuntimeError(
                            f"ffmpeg 转换失败 (输入文件可能不是有效音频): "
                            f"{detail2[:300]}"
                        )
                else:
                    raise RuntimeError(
                        f"ffmpeg 转换失败 (输入文件可能不是有效音频): "
                        f"{error_detail[:300]}"
                    )
            if progress_callback:
                progress_callback(100)
            logger.info(f"转换完成 (ffmpeg): {output_path}")
            return output_path
        finally:
            if temp_cover and os.path.exists(temp_cover.name):
                try:
                    os.unlink(temp_cover.name)
                except OSError:
                    pass

    @classmethod
    def _convert_flac_ffmpeg(cls, input_path, output_path, cover_data,
                              metadata, progress_callback):
        """使用 ffmpeg 转换为 FLAC"""
        cmd = [FFMPEG_PATH, '-y', '-i', input_path, '-codec:a', 'flac']

        if metadata:
            for key in ('title', 'artist', 'album', 'genre', 'date'):
                if metadata.get(key):
                    cmd.extend(['-metadata', f'{key}={metadata[key]}'])

        temp_cover = None
        if cover_data:
            import tempfile
            temp_cover = tempfile.NamedTemporaryFile(suffix='.jpg', delete=False)
            temp_cover.write(cover_data)
            temp_cover.close()
            cmd = [
                FFMPEG_PATH, '-y',
                '-i', input_path,
                '-i', temp_cover.name,
                '-map', '0:a', '-map', '1:0',
                '-codec:a', 'flac',
                '-codec:v', 'mjpeg',
                '-disposition:v', 'attached_pic',
            ]
            if metadata:
                for key in ('title', 'artist', 'album', 'genre', 'date'):
                    if metadata.get(key):
                        cmd.extend(['-metadata', f'{key}={metadata[key]}'])

        cmd.append(output_path)

        try:
            if progress_callback:
                progress_callback(10)
            logger.debug(f"执行 ffmpeg FLAC 命令: {' '.join(cmd)}")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            if progress_callback:
                progress_callback(90)
            if result.returncode != 0:
                stderr_text = result.stderr or ''
                stdout_text = result.stdout or ''
                error_detail = stderr_text.strip() or stdout_text.strip() or '(无错误输出)'
                logger.error(f"ffmpeg FLAC 转换错误 (返回码={result.returncode}): {error_detail}")
                raise RuntimeError(f"FLAC 转换失败: {error_detail[:300]}")
            if progress_callback:
                progress_callback(100)
            logger.info(f"FLAC 转换完成: {output_path}")
            return output_path
        finally:
            if temp_cover and os.path.exists(temp_cover.name):
                try:
                    os.unlink(temp_cover.name)
                except OSError:
                    pass

    @classmethod
    def _convert_with_pydub(cls, input_path, output_path, bitrate,
                             cover_data, metadata, progress_callback):
        """使用 pydub 转换"""
        from pydub import AudioSegment
        if progress_callback:
            progress_callback(10)
        source_format = cls.detect_format(input_path)
        if source_format is None:
            source_format = os.path.splitext(input_path)[1].lstrip('.')
        logger.info(f"使用 pydub 加载 ({source_format})...")
        try:
            audio = AudioSegment.from_file(input_path, format=source_format)
        except Exception:
            audio = AudioSegment.from_file(input_path)
        if progress_callback:
            progress_callback(50)
        export_params = {'format': 'mp3', 'bitrate': bitrate}
        audio.export(output_path, **export_params)
        if progress_callback:
            progress_callback(80)
        if metadata or cover_data:
            try:
                cls._add_metadata(output_path, metadata, cover_data)
            except Exception as e:
                logger.warning(f"添加元数据失败: {e}")
        if progress_callback:
            progress_callback(100)
        logger.info(f"转换完成 (pydub): {output_path}")
        return output_path

    @classmethod
    def _convert_flac_pydub(cls, input_path, output_path, cover_data,
                             metadata, progress_callback):
        """使用 pydub 转换为 FLAC"""
        from pydub import AudioSegment
        if progress_callback:
            progress_callback(10)
        source_format = cls.detect_format(input_path)
        if source_format is None:
            source_format = os.path.splitext(input_path)[1].lstrip('.')
        try:
            audio = AudioSegment.from_file(input_path, format=source_format)
        except Exception:
            audio = AudioSegment.from_file(input_path)
        if progress_callback:
            progress_callback(60)
        audio.export(output_path, format='flac')
        if progress_callback:
            progress_callback(100)
        logger.info(f"FLAC 转换完成 (pydub): {output_path}")
        return output_path

    @staticmethod
    def _add_metadata(file_path, metadata=None, cover_data=None):
        """为 MP3 文件添加元数据和封面"""
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3, TIT2, TPE1, TALB, APIC, ID3NoHeaderError
        try:
            audio = MP3(file_path)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()
        if audio.tags is None:
            audio.add_tags()
        if metadata:
            if metadata.get('title'):
                audio.tags.delall('TIT2')
                audio.tags.add(TIT2(encoding=3, text=metadata['title']))
            if metadata.get('artist'):
                audio.tags.delall('TPE1')
                audio.tags.add(TPE1(encoding=3, text=metadata['artist']))
            if metadata.get('album'):
                audio.tags.delall('TALB')
                audio.tags.add(TALB(encoding=3, text=metadata['album']))
        if cover_data:
            from src.metadata import MetadataManager
            mime = MetadataManager.detect_cover_mime(cover_data)
            audio.tags.delall('APIC')
            audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=cover_data))
        audio.save()

    @classmethod
    def get_supported_input_formats(cls):
        """获取支持的输入文件格式列表"""
        return cls.AUDIO_EXTENSIONS