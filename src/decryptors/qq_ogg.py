"""
QQ音乐 DRM 加密 OGG 解密器
通过 Frida 动态注入 QQ 音乐客户端，调用其 EncAndDesMediaFile API 解密文件。

适用格式: QQ音乐新版 DRM 加密的 .ogg 文件（文件头非 OggS）

前置条件:
1. 安装 frida: pip install frida frida-tools
2. 启动 QQ 音乐客户端 (QQMusic.exe)
3. 用户需为 VIP（已购歌曲可离线播放）
"""

import os
import sys
import shutil
import hashlib
import tempfile
import logging
import threading
import time
from typing import Optional

from .base import BaseDecryptor, DecryptResult

logger = logging.getLogger(__name__)


class QQOGGDecryptor(BaseDecryptor):
    """QQ音乐 DRM 加密 OGG 解密器（基于 Frida 注入）"""

    FORMAT_NAME = "QQ音乐DRM"
    EXTENSIONS = []  # 不注册 .ogg 扩展名，避免普通 OGG 文件被误判为加密格式
    MAGIC_SIGNATURES = []  # 无固定魔数，通过文件头非 OggS 判定

    # Frida hook 脚本路径
    _HOOK_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), 'qq_ogg_hook.js')

    # QQ音乐进程名
    _QQ_MUSIC_PROCESS = "QQMusic.exe"

    # 默认下载目录
    _DEFAULT_DOWNLOAD_DIR = os.path.join(
        os.path.expanduser("~"), "Music", "VipSongsDownload"
    )

    @classmethod
    def is_available(cls) -> bool:
        """检查 Frida 是否可用"""
        try:
            import frida
            return True
        except ImportError:
            return False

    @classmethod
    def _is_qq_music_running(cls) -> bool:
        """检测 QQ 音乐是否正在运行"""
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] and cls._QQ_MUSIC_PROCESS.lower() in proc.info['name'].lower():
                    return True
        except ImportError:
            # psutil 不可用时使用 tasklist
            try:
                import subprocess
                result = subprocess.run(
                    ['tasklist', '/FI', f'IMAGENAME eq {cls._QQ_MUSIC_PROCESS}'],
                    capture_output=True, text=True, timeout=5
                )
                return cls._QQ_MUSIC_PROCESS.lower() in result.stdout.lower()
            except Exception:
                pass
        return False

    @classmethod
    def _is_encrypted_ogg(cls, file_path: str) -> bool:
        """
        判断 .ogg 文件是否为 DRM 加密格式。
        普通 OGG 文件以 'OggS' 开头，加密的则不是。
        """
        try:
            with open(file_path, 'rb') as f:
                header = f.read(4)
            return header[:4] != b'OggS'
        except (IOError, OSError):
            return False

    @classmethod
    def _load_hook_script(cls) -> str:
        """加载 Frida hook 脚本内容"""
        if not os.path.isfile(cls._HOOK_SCRIPT_PATH):
            raise FileNotFoundError(
                f"Frida hook 脚本未找到: {cls._HOOK_SCRIPT_PATH}\n"
                "请确保 qq_ogg_hook.js 文件位于 src/decryptors/ 目录下。"
            )
        with open(cls._HOOK_SCRIPT_PATH, 'r', encoding='utf-8') as f:
            return f.read()

    @classmethod
    def _get_session(cls):
        """获取 Frida session（附加到 QQ 音乐进程）"""
        import frida

        # 方法1: 直接附加到 QQMusic.exe
        try:
            session = frida.attach(cls._QQ_MUSIC_PROCESS)
            logger.info("已附加到 QQMusic.exe 进程")
            return session
        except frida.ProcessNotFoundError:
            pass

        # 方法2: 通过 PID 查找
        try:
            import psutil
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and cls._QQ_MUSIC_PROCESS.lower() in proc.info['name'].lower():
                    session = frida.attach(proc.info['pid'])
                    logger.info(f"已附加到 QQMusic.exe (PID: {proc.info['pid']})")
                    return session
        except (ImportError, frida.ProcessNotFoundError):
            pass

        raise RuntimeError(
            "未找到 QQ 音乐进程 (QQMusic.exe)。\n"
            "请先启动 QQ 音乐客户端，确保可以播放需要解密的歌曲。"
        )

    @classmethod
    def decrypt_file(cls, input_path: str, output_path: Optional[str] = None,
                     output_format: str = 'mp3') -> DecryptResult:
        """
        通过 Frida 注入解密 QQ 音乐 DRM 加密的 OGG 文件。

        Args:
            input_path: 输入的加密 .ogg 文件路径
            output_path: 输出文件路径 (None 则自动生成)
            output_format: 输出格式 (解密后为 ogg，可选转码)

        Returns:
            DecryptResult 对象

        Raises:
            FileNotFoundError: 文件不存在
            RuntimeError: QQ音乐未运行或 Frida 不可用
        """
        if not os.path.isfile(input_path):
            raise FileNotFoundError(f"文件不存在: {input_path}")

        # 检查是否为加密的 OGG（非 OggS 开头）
        if not cls._is_encrypted_ogg(input_path):
            # 文件已经是普通 OGG，直接返回
            if output_path is None:
                output_path = cls._auto_output_path(input_path, 'ogg')
            if input_path != output_path:
                shutil.copy2(input_path, output_path)
            logger.info(f"文件已是普通 OGG 格式，直接复制: {output_path}")
            return DecryptResult(
                audio_path=output_path,
                source_format="OGG (未加密)",
                detected_type='ogg',
            )

        # 检查 Frida
        if not cls.is_available():
            raise RuntimeError(
                "此格式需要 Frida 库来解密。\n"
                "请安装: pip install frida frida-tools\n"
                "并确保 QQ 音乐客户端正在运行。"
            )

        # 检查 QQ 音乐是否运行
        if not cls._is_qq_music_running():
            raise RuntimeError(
                "此格式需要 QQ 音乐客户端运行才能解密。\n"
                "请先启动 QQ 音乐 (QQMusic.exe)，\n"
                "确保可以播放需要解密的歌曲（可能需要登录 VIP 账号）。"
            )

        # 准备输出路径
        if output_path is None:
            output_path = cls._auto_output_path(input_path, 'ogg')

        # 使用 Frida 解密
        return cls._frida_decrypt(input_path, output_path)

    # 类级别的线程锁，确保同一时间只有一个 Frida session 活动
    _frida_lock = threading.Lock()

    @classmethod
    def _frida_decrypt(cls, input_path: str, output_path: str,
                       max_retries: int = 2) -> DecryptResult:
        """
        通过 Frida 注入解密文件。
        使用线程锁确保同一时间只有一个 Frida session 活动，
        避免并发注入导致 QQMusic 崩溃或 "device is gone" 错误。
        """
        import frida

        abs_input = os.path.abspath(input_path)
        abs_output = os.path.abspath(output_path)

        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return cls._frida_decrypt_once(abs_input, abs_output)
            except Exception as e:
                last_error = e
                error_msg = str(e).lower()
                # 对 "device is gone" 或连接断开类错误进行重试
                if attempt < max_retries and ('device is gone' in error_msg
                                              or 'terminated' in error_msg
                                              or 'pipe is closed' in error_msg
                                              or 'unable to connect' in error_msg):
                    logger.warning(f"Frida 解密失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}，"
                                   f"等待 1 秒后重试...")
                    time.sleep(1)
                    continue
                raise

        # 不应到达这里，但以防万一
        raise RuntimeError(f"Frida 解密失败（重试 {max_retries} 次后）: {last_error}")

    @classmethod
    def _frida_decrypt_once(cls, abs_input: str, abs_output: str) -> DecryptResult:
        """单次 Frida 解密尝试（在锁保护下执行）"""
        import frida

        with cls._frida_lock:
            # 获取 Frida session
            session = cls._get_session()

            try:
                # 加载 hook 脚本
                script_content = cls._load_hook_script()
                script = session.create_script(script_content)
                script.load()
                logger.info("Frida hook 脚本已加载")

                # 验证 probe
                try:
                    probe_ok = script.exports_sync.probe()
                    if not probe_ok:
                        raise RuntimeError(
                            "QQMusicCommon.dll 中未找到 EncAndDesMediaFile 函数。\n"
                            "请确认 QQ 音乐版本较新（2024 年后版本）。"
                        )
                except Exception as e:
                    if "probe" in str(e).lower():
                        logger.warning("probe 调用失败，继续尝试解密...")
                    else:
                        raise

                # 调用解密
                logger.info(f"开始 Frida 解密: {abs_input}")
                bytes_written = script.exports_sync.decrypt(abs_input, abs_output)
                logger.info(f"Frida 解密完成，写入 {bytes_written} 字节")

                # 验证输出文件
                if not os.path.isfile(abs_output) or os.path.getsize(abs_output) == 0:
                    raise RuntimeError("解密输出文件为空或不存在")

                # 检查解密后的文件是否为有效 OGG
                with open(abs_output, 'rb') as f:
                    header = f.read(4)
                if header[:4] != b'OggS':
                    logger.warning("解密后的文件头不是 OggS，可能解密失败")

                detected_type = cls._detect_audio_type(header)
                logger.info(f"解密成功: {abs_output} (类型: {detected_type})")

                return DecryptResult(
                    audio_path=abs_output,
                    source_format=f"{cls.FORMAT_NAME} (Frida)",
                    detected_type=detected_type,
                )

            finally:
                try:
                    session.detach()
                except Exception:
                    pass

    @classmethod
    def decrypt_batch_frida(cls, file_list: list, output_dir: str,
                            output_format: str = 'ogg',
                            progress_callback=None) -> list:
        """
        批量解密（共享同一个 Frida session，效率更高）

        Args:
            file_list: 输入文件路径列表
            output_dir: 输出目录
            output_format: 输出格式
            progress_callback: 进度回调 (current, total)

        Returns:
            DecryptResult 列表
        """
        if not cls.is_available():
            raise RuntimeError("Frida 未安装: pip install frida frida-tools")

        if not cls._is_qq_music_running():
            raise RuntimeError("QQ 音乐未运行，请先启动 QQMusic.exe")

        results = []
        temp_dir = tempfile.mkdtemp(prefix='qqmusic_drm_batch_')

        try:
            session = cls._get_session()
            try:
                script_content = cls._load_hook_script()
                script = session.create_script(script_content)
                script.load()
                logger.info("批量解密: Frida hook 脚本已加载")

                for i, input_path in enumerate(file_list):
                    if progress_callback:
                        progress_callback(i, len(file_list))

                    filename = os.path.basename(input_path)
                    base_name = os.path.splitext(filename)[0]
                    output_path = os.path.join(output_dir, f"{base_name}.{output_format}")

                    try:
                        abs_input = os.path.abspath(input_path)
                        temp_input = os.path.join(
                            temp_dir,
                            hashlib.md5(abs_input.encode()).hexdigest() + '.ogg'
                        )
                        shutil.copy2(abs_input, temp_input)

                        abs_output = os.path.abspath(output_path)
                        bytes_written = script.exports_sync.decrypt(temp_input, abs_output)

                        if bytes_written > 0 and os.path.isfile(abs_output):
                            detected_type = cls._detect_audio_type(open(abs_output, 'rb').read(4))
                            result = DecryptResult(
                                audio_path=abs_output,
                                source_format=f"{cls.FORMAT_NAME} (Frida)",
                                detected_type=detected_type,
                            )
                            results.append(result)
                            logger.info(f"[{i+1}/{len(file_list)}] 解密成功: {filename}")
                        else:
                            results.append(None)
                            logger.error(f"[{i+1}/{len(file_list)}] 解密失败（输出为空）: {filename}")

                    except Exception as e:
                        results.append(None)
                        logger.error(f"[{i+1}/{len(file_list)}] 解密失败: {filename} - {e}")

                if progress_callback:
                    progress_callback(len(file_list), len(file_list))

            finally:
                try:
                    session.detach()
                except Exception:
                    pass

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return results