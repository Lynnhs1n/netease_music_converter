"""
任务管理器
批量任务管理 + 线程池并行处理
支持进度回调、取消、重试
"""

import os
import time
import logging
import tempfile
import threading
from enum import Enum
from typing import Optional, Callable, List, Dict, Any
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, Future

from src.decryptors import DecryptorRegistry, decrypt_file, DecryptResult
from src.converter import AudioConverter
from src.metadata import MetadataManager
from src.config import config

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态"""
    PENDING = "pending"         # 等待中
    DECRYPTING = "decrypting"   # 解密中
    ENCODING = "encoding"       # 编码中
    DONE = "done"               # 完成
    FAILED = "failed"           # 失败
    CANCELLED = "cancelled"     # 已取消


@dataclass
class TaskItem:
    """单个转换任务"""
    id: int
    input_path: str
    output_path: Optional[str] = None
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    error_message: str = ""
    source_format: str = ""
    platform: str = ""
    detected_type: Optional[str] = None
    result: Optional[DecryptResult] = None
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed(self) -> float:
        if self.start_time == 0:
            return 0
        end = self.end_time if self.end_time > 0 else time.time()
        return end - self.start_time

    @property
    def filename(self) -> str:
        return os.path.basename(self.input_path)


@dataclass
class BatchProgress:
    """批量处理进度"""
    total: int = 0
    completed: int = 0
    failed: int = 0
    cancelled: int = 0
    current_file: str = ""
    start_time: float = 0.0

    @property
    def percent(self) -> float:
        if self.total == 0:
            return 0
        return (self.completed + self.failed + self.cancelled) / self.total * 100

    @property
    def elapsed(self) -> float:
        return time.time() - self.start_time if self.start_time > 0 else 0

    @property
    def eta_seconds(self) -> float:
        done = self.completed + self.failed + self.cancelled
        if done == 0:
            return 0
        avg_time = self.elapsed / done
        remaining = self.total - done
        return avg_time * remaining

    @property
    def speed(self) -> float:
        """转换速度（文件/秒）"""
        elapsed = self.elapsed
        if elapsed <= 0:
            return 0
        return (self.completed + self.failed + self.cancelled) / elapsed

    @property
    def speed_text(self) -> str:
        """速度文本"""
        spd = self.speed
        if spd < 1:
            return f"{spd:.2f}x"
        return f"{spd:.1f}x"

    @property
    def eta_text(self) -> str:
        """预估剩余时间文本"""
        eta = self.eta_seconds
        if eta <= 0:
            return "计算中..."
        if eta < 60:
            return f"{eta:.0f}秒"
        elif eta < 3600:
            return f"{eta/60:.1f}分钟"
        else:
            return f"{eta/3600:.1f}小时"


class TaskManager:
    """任务管理器"""

    def __init__(self, max_workers: Optional[int] = None):
        if max_workers is None:
            max_workers = config.get('processing.max_workers', 4)
        self.max_workers = max_workers
        self.tasks: List[TaskItem] = []
        self.progress = BatchProgress()
        self._cancel_flag = threading.Event()
        self._pause_flag = threading.Event()
        self._pause_flag.set()  # 默认非暂停
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._next_id = 0

        # 重复检测相关
        self._duplicate_mode: Optional[str] = None  # 'overwrite_all', 'version_all', 'skip_all', None
        self._metadata_cache: Optional[Dict] = None  # 目录元数据缓存

        # 回调函数
        self._on_task_start: Optional[Callable[[TaskItem], None]] = None
        self._on_task_progress: Optional[Callable[[TaskItem, float], None]] = None
        self._on_task_done: Optional[Callable[[TaskItem], None]] = None
        self._on_task_failed: Optional[Callable[[TaskItem], None]] = None
        self._on_batch_done: Optional[Callable[[BatchProgress], None]] = None
        self._on_log: Optional[Callable[[str, str], None]] = None
        self._on_duplicate_check: Optional[Callable[[str, str, Dict, str], str]] = None
        self._on_output_dir_missing: Optional[Callable[[str], str]] = None

    def set_callbacks(self,
                      on_task_start: Optional[Callable] = None,
                      on_task_progress: Optional[Callable] = None,
                      on_task_done: Optional[Callable] = None,
                      on_task_failed: Optional[Callable] = None,
                      on_batch_done: Optional[Callable] = None,
                      on_log: Optional[Callable] = None,
                      on_duplicate_check: Optional[Callable] = None,
                      on_output_dir_missing: Optional[Callable] = None):
        """设置回调函数"""
        if on_task_start:
            self._on_task_start = on_task_start
        if on_task_progress:
            self._on_task_progress = on_task_progress
        if on_task_done:
            self._on_task_done = on_task_done
        if on_task_failed:
            self._on_task_failed = on_task_failed
        if on_batch_done:
            self._on_batch_done = on_batch_done
        if on_log:
            self._on_log = on_log
        if on_duplicate_check:
            self._on_duplicate_check = on_duplicate_check
        if on_output_dir_missing:
            self._on_output_dir_missing = on_output_dir_missing

    def _log(self, message: str, level: str = 'INFO'):
        """发送日志（只通过回调发送，避免与 root logger 的 TextHandler 重复输出）"""
        if self._on_log:
            self._on_log(message, level)
        else:
            # 仅在没有 GUI 回调时才使用 logger（命令行模式）
            logger.log(getattr(logging, level, logging.INFO), message)

    def add_files(self, file_paths: List[str]) -> int:
        """
        添加文件到任务列表

        Args:
            file_paths: 文件路径列表

        Returns:
            成功添加的文件数量
        """
        from src.format_detector import FormatDetector

        added = 0
        for path in file_paths:
            if not os.path.isfile(path):
                continue

            # 检查是否为音频文件
            if not FormatDetector.is_audio(path):
                continue

            # 检查重复
            if any(t.input_path == os.path.abspath(path) for t in self.tasks):
                continue

            detection = FormatDetector.detect(path)
            task = TaskItem(
                id=self._next_id,
                input_path=os.path.abspath(path),
                source_format=detection.get('extension', ''),
                platform=detection.get('platform', ''),
            )
            self._next_id += 1
            self.tasks.append(task)
            added += 1

        return added

    def clear_tasks(self):
        """清空任务列表"""
        self.tasks.clear()
        self._next_id = 0

    def remove_task(self, task_id: int):
        """移除指定任务"""
        self.tasks = [t for t in self.tasks if t.id != task_id]

    def get_pending_tasks(self) -> List[TaskItem]:
        """获取待处理的任务"""
        return [t for t in self.tasks if t.status in (TaskStatus.PENDING, TaskStatus.FAILED)]

    def cancel(self):
        """取消所有任务"""
        self._cancel_flag.set()
        self._log("用户取消转换...", 'WARNING')

    def pause(self):
        """暂停转换"""
        self._pause_flag.clear()
        self._log("转换已暂停", 'WARNING')

    def resume(self):
        """恢复转换"""
        self._pause_flag.set()
        self._log("转换已恢复", 'INFO')

    def _convert_single(self, task: TaskItem) -> TaskItem:
        """转换单个文件"""
        self._pause_flag.wait()  # 等待暂停恢复
        if self._cancel_flag.is_set():
            task.status = TaskStatus.CANCELLED
            return task

        task.start_time = time.time()
        task.status = TaskStatus.DECRYPTING
        task.progress = 0

        if self._on_task_start:
            self._on_task_start(task)

        try:
            # 确定输出路径
            output_path = task.output_path
            if not output_path:
                # 使用文件名模板
                template = config.get('output.filename_template', '{歌手} - {歌名}')
                output_format = config.get('output.output_format', 'mp3')
                preserve_lossless = config.get('output.preserve_lossless', False)

                if config.get('output.output_to_source_dir', True):
                    output_dir = os.path.dirname(task.input_path)
                else:
                    output_dir = config.get('output.output_dir', '')
                    if not output_dir:
                        output_dir = os.path.dirname(task.input_path)

                # 检查输出目录是否存在
                if not os.path.isdir(output_dir):
                    if self._on_output_dir_missing:
                        try:
                            dir_action = self._on_output_dir_missing(output_dir)
                        except Exception:
                            dir_action = 'skip'
                        if dir_action == 'create':
                            os.makedirs(output_dir, exist_ok=True)
                            self._log(f"📁 已创建输出目录: {output_dir}", 'INFO')
                        else:
                            self._log(f"⏭️ 跳过: {task.filename} (输出目录不存在)", 'WARNING')
                            task.status = TaskStatus.FAILED
                            task.error_message = f"输出目录不存在: {output_dir}"
                            task.end_time = time.time()
                            if self._on_task_failed:
                                self._on_task_failed(task)
                            return task
                    else:
                        # 没有回调，自动创建
                        os.makedirs(output_dir, exist_ok=True)
                        self._log(f"📁 已创建输出目录: {output_dir}", 'INFO')

                # 解密
                temp_output = os.path.join(
                    tempfile.gettempdir(),
                    f"_temp_{task.id}_{int(time.time())}.bin"
                )

                # 格式检测
                from src.format_detector import FormatDetector
                detection = FormatDetector.detect(task.input_path)
                task.platform = detection.get('platform', '')

                result = decrypt_file(task.input_path, temp_output, output_format)
                task.result = result
                task.detected_type = result.detected_type

                # 如果解密器未提供元数据，尝试从解密后的音频文件中读取
                if not result.metadata and os.path.isfile(temp_output):
                    try:
                        meta_from_file = MetadataManager.read_audio_metadata(temp_output)
                        if meta_from_file:
                            result.metadata = meta_from_file
                            logger.debug(f"从解密文件中读取到元数据: {meta_from_file.get('title', '')} - {meta_from_file.get('artist', '')} [{meta_from_file.get('album', '')}]")
                    except Exception as meta_err:
                        logger.debug(f"读取解密文件元数据失败: {meta_err}")

                task.progress = 40

                if self._on_task_progress:
                    self._on_task_progress(task, 40)

                # 确定最终输出格式
                if preserve_lossless and result.detected_type in ('flac', 'wav'):
                    final_format = result.detected_type
                else:
                    final_format = output_format

                # 构建输出文件名
                if result.metadata:
                    base_name = MetadataManager.build_filename(
                        template, result.metadata,
                        index=task.id + 1,
                        fallback_name=os.path.splitext(task.filename)[0]
                    )
                else:
                    base_name = os.path.splitext(task.filename)[0]

                output_path = os.path.normpath(os.path.join(output_dir, f"{base_name}.{final_format}"))

                # 重复检测：检查输出目录中是否已有相同歌曲
                bitrate_cfg = config.get('output.bitrate', '320k')
                mode_cfg = config.get('output.mode', 'cbr')
                dup_action, dup_data = self._check_duplicate(
                    task, result, output_dir, final_format,
                    base_name, bitrate_cfg, mode_cfg
                )
                if dup_action == 'skip':
                    # 用户选择跳过此文件
                    self._log(f"⏭️ 跳过: {task.filename} ({dup_data})", 'WARNING')
                    task.progress = 100
                    task.status = TaskStatus.DONE
                    task.end_time = time.time()
                    if self._on_task_done:
                        self._on_task_done(task)

                    # 清理临时文件
                    if os.path.exists(temp_output):
                        try:
                            os.unlink(temp_output)
                        except OSError:
                            pass
                    return task
                elif dup_action == 'overwrite':
                    # 用户选择覆盖现有文件
                    output_path = dup_data
                    self._log(f"📝 覆盖现有文件: {os.path.basename(output_path)}", 'INFO')
                elif dup_action == 'version':
                    # 用户选择保存新版本（带日期时间+码率）
                    output_path = dup_data
                    self._log(f"📝 保存新版本: {os.path.basename(output_path)}", 'INFO')

                task.output_path = output_path

                # 编码转换
                task.status = TaskStatus.ENCODING
                task.progress = 50
                if self._on_task_progress:
                    self._on_task_progress(task, 50)

                # 获取音频转换设置
                bitrate = config.get('output.bitrate', '320k')
                sample_rate = config.get('output.sample_rate', 44100)
                channels = config.get('output.channels', 2)

                # 如果目标格式与源格式相同且不需要转换，直接复制
                if result.detected_type == final_format:
                    import shutil
                    shutil.copy2(result.audio_path, output_path)
                else:
                    AudioConverter.convert_to_mp3(
                        input_path=result.audio_path,
                        output_path=output_path,
                        bitrate=bitrate,
                        cover_data=result.cover_data if config.get('processing.embed_cover', True) else None,
                        metadata=result.metadata,
                        sample_rate=sample_rate,
                        channels=channels,
                    )

                task.progress = 80
                if self._on_task_progress:
                    self._on_task_progress(task, 80)

                # 写入元数据
                if final_format in ('mp3', 'flac'):
                    MetadataManager.write_metadata(
                        output_path,
                        metadata=result.metadata,
                        cover_data=result.cover_data if config.get('processing.embed_cover', True) else None,
                        cover_mime=result.cover_mime,
                        lyrics=result.lyrics if config.get('processing.embed_lyrics', True) else None,
                    )

                # 导出歌词
                if config.get('processing.export_lyrics', True) and result.has_lyrics:
                    lrc_path = os.path.splitext(output_path)[0] + '.lrc'
                    MetadataManager.export_lyrics(result.lyrics, lrc_path)

                # 清理临时文件
                if os.path.exists(temp_output):
                    try:
                        os.unlink(temp_output)
                    except OSError:
                        pass

                task.progress = 100
                task.status = TaskStatus.DONE
                task.end_time = time.time()

                output_size = os.path.getsize(output_path)
                size_str = self._format_size(output_size)
                self._log(f"✅ 转换完成: {task.filename} → {os.path.basename(output_path)} ({size_str})", 'SUCCESS')

                if self._on_task_done:
                    self._on_task_done(task)

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            task.end_time = time.time()
            self._log(f"❌ 转换失败: {task.filename} - {e}", 'ERROR')

            # 清理临时文件
            if 'temp_output' in locals() and os.path.exists(temp_output):
                try:
                    os.unlink(temp_output)
                except OSError:
                    pass

            if self._on_task_failed:
                self._on_task_failed(task)

        return task

    def _check_duplicate(self, task: TaskItem, result: 'DecryptResult',
                         output_dir: str, output_format: str,
                         base_name: str, bitrate: str, mode: str) -> tuple:
        """
        检查输出目录中是否已存在相同的音乐文件。
        区分同名同规格和同名不同规格两种情况。

        Returns:
            (action, path) 元组:
                ('proceed', None) - 无重复，正常继续
                ('skip', reason) - 用户选择跳过
                ('overwrite', existing_path) - 用户选择覆盖现有文件
                ('version', new_path) - 用户选择保存新版本（带日期时间+码率）
        """
        import datetime

        # 无元数据则无法匹配，正常继续
        if not result.metadata or not result.metadata.get('title') or not result.metadata.get('artist'):
            return ('proceed', None)

        title = result.metadata['title']
        artist = result.metadata['artist']

        # 查找重复
        existing = MetadataManager.find_duplicate(title, artist, output_dir, output_format)
        if existing is None:
            return ('proceed', None)

        # 发现重复 - 通知用户
        existing_info = {
            'filename': existing.get('filename', ''),
            'bitrate': existing.get('bitrate', 0),
            'format': existing.get('format', output_format),
            'path': existing.get('path', ''),
        }

        # 判断是同名同规格还是同名不同规格
        existing_bitrate = existing.get('bitrate', 0)
        bitrate_num = int(bitrate.replace('k', '')) if 'k' in bitrate else int(bitrate)
        is_same_spec = (existing_bitrate == bitrate_num) or (existing_bitrate == 0)

        dup_type = 'same_spec' if is_same_spec else 'diff_spec'
        existing_info['dup_type'] = dup_type
        existing_info['new_bitrate'] = bitrate_num

        if is_same_spec:
            self._log(f"⚠️ 发现同名同规格文件: {title} - {artist} → {existing_info['filename']} ({existing_bitrate}kbps)", 'WARNING')
        else:
            self._log(f"⚠️ 发现同名不同规格文件: {title} - {artist} → {existing_info['filename']} (现有{existing_bitrate}kbps, 新{bitrate_num}kbps)", 'WARNING')

        # 检查全局模式
        if self._duplicate_mode == 'skip_all':
            return ('skip', f"已存在: {existing_info['filename']}")
        if self._duplicate_mode == 'overwrite_all':
            return ('overwrite', existing_info['path'])
        if self._duplicate_mode == 'version_all':
            timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
            new_base = f"{base_name}_{timestamp}_{bitrate_num}kbps"
            new_path = os.path.normpath(os.path.join(output_dir, f"{new_base}.{output_format}"))
            return ('version', new_path)

        # 通过回调询问用户
        if self._on_duplicate_check:
            try:
                decision = self._on_duplicate_check(title, artist, existing_info, dup_type)
            except Exception:
                decision = 'skip'

            if decision == 'skip_all':
                self._duplicate_mode = 'skip_all'
                return ('skip', f"已存在: {existing_info['filename']}")
            elif decision == 'skip':
                return ('skip', f"已存在: {existing_info['filename']}")
            elif decision == 'overwrite_all':
                self._duplicate_mode = 'overwrite_all'
                return ('overwrite', existing_info['path'])
            elif decision == 'overwrite':
                return ('overwrite', existing_info['path'])
            elif decision == 'version_all':
                self._duplicate_mode = 'version_all'
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                new_base = f"{base_name}_{timestamp}_{bitrate_num}kbps"
                new_path = os.path.normpath(os.path.join(output_dir, f"{new_base}.{output_format}"))
                return ('version', new_path)
            elif decision == 'version':
                timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
                new_base = f"{base_name}_{timestamp}_{bitrate_num}kbps"
                new_path = os.path.normpath(os.path.join(output_dir, f"{new_base}.{output_format}"))
                return ('version', new_path)
            else:
                return ('skip', f"已存在: {existing_info['filename']}")
        else:
            # 没有回调，默认跳过
            return ('skip', f"已存在: {existing_info['filename']}")

    def start(self):
        """开始批量转换"""
        # 重置重复检测状态
        self._duplicate_mode = None
        self._metadata_cache = None

        pending = self.get_pending_tasks()
        if not pending:
            self._log("没有待处理的任务", 'WARNING')
            return

        self._cancel_flag.clear()
        self._pause_flag.set()
        self.progress = BatchProgress(
            total=len(pending),
            completed=0,
            failed=0,
            cancelled=0,
            start_time=time.time()
        )

        self._log(f"🚀 开始批量转换，共 {len(pending)} 个文件 (并行数: {self.max_workers})", 'HEADER')

        # 使用线程池并行处理
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            self._executor = executor
            futures: Dict[Future, TaskItem] = {}

            for task in pending:
                if self._cancel_flag.is_set():
                    break
                future = executor.submit(self._convert_single, task)
                futures[future] = task

            # 等待所有任务完成
            for future in futures:
                try:
                    result_task = future.result()
                    if result_task.status == TaskStatus.DONE:
                        self.progress.completed += 1
                    elif result_task.status == TaskStatus.FAILED:
                        self.progress.failed += 1
                    elif result_task.status == TaskStatus.CANCELLED:
                        self.progress.cancelled += 1
                except Exception as e:
                    self.progress.failed += 1
                    self._log(f"任务执行异常: {e}", 'ERROR')

        # 批量完成
        if self._on_batch_done:
            self._on_batch_done(self.progress)

        self._log("", 'INFO')
        self._log("=" * 50, 'HEADER')
        self._log(f"🎉 批量转换完成！", 'HEADER')
        self._log(f"  ✅ 成功: {self.progress.completed} 个", 'SUCCESS')
        if self.progress.failed > 0:
            self._log(f"  ❌ 失败: {self.progress.failed} 个", 'ERROR')
        if self.progress.cancelled > 0:
            self._log(f"  ⚠️ 取消: {self.progress.cancelled} 个", 'WARNING')
        self._log(f"  ⏱️ 耗时: {self.progress.elapsed:.1f}秒", 'INFO')
        self._log(f"  🚀 速度: {self.progress.speed_text}", 'INFO')
        self._log("=" * 50, 'HEADER')

    def retry_failed(self):
        """重试所有失败的任务"""
        for task in self.tasks:
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error_message = ""
                task.progress = 0
        self.start()

    def retry_task(self, task_id: int):
        """重试指定任务"""
        for task in self.tasks:
            if task.id == task_id and task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error_message = ""
                task.progress = 0
                break

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"