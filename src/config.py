"""
配置持久化管理
保存和加载用户设置，支持 JSON 配置文件
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# 默认配置
DEFAULT_CONFIG = {
    # 转换设置
    'output': {
        'bitrate': '320k',
        'sample_rate': 44100,
        'channels': 2,  # 1=mono, 2=stereo
        'mode': 'cbr',  # 'cbr' or 'vbr'
        'preserve_lossless': False,  # 保留无损格式
        'output_format': 'mp3',
        'filename_template': '{歌手} - {歌名}',
        'output_to_source_dir': True,
        'output_dir': '',
    },

    # 处理设置
    'processing': {
        'max_workers': 4,  # 最大并行线程数
        'auto_detect_format': True,  # 自动检测格式
        'export_lyrics': True,  # 导出歌词
        'embed_lyrics': True,  # 嵌入歌词
        'embed_cover': True,  # 嵌入封面
    },

    # UI 设置
    'ui': {
        'theme': 'default',
        'font_size': 10,
        'window_width': 1000,
        'window_height': 750,
        'show_toolbar': True,
        'show_statusbar': True,
        'auto_scroll_log': True,
    },

    # 完成后动作
    'post_action': 'none',  # 'none', 'open_folder', 'play', 'shutdown'

    # 插件设置
    'plugins': {
        'enabled': True,
        'plugin_dir': 'plugins',
    },

    # 版本信息
    'version': '2.0.0',
}

CONFIG_FILE = 'config.json'


class ConfigManager:
    """配置管理器"""

    _instance = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """加载配置"""
        config_path = self._get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                # 合并默认配置（处理新增配置项）
                self._config = self._merge_config(DEFAULT_CONFIG, self._config)
                logger.info(f"配置已加载: {config_path}")
            except Exception as e:
                logger.error(f"加载配置失败: {e}")
                self._config = DEFAULT_CONFIG.copy()
        else:
            self._config = DEFAULT_CONFIG.copy()
            self.save()
            logger.info("使用默认配置")

    def _merge_config(self, default: dict, user: dict) -> dict:
        """递归合并配置"""
        result = default.copy()
        for key, value in user.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._merge_config(result[key], value)
            else:
                result[key] = value
        return result

    def _get_config_path(self) -> str:
        """获取配置文件路径"""
        # 优先使用用户目录
        home = Path.home()
        config_dir = home / '.netease_music_converter'
        config_dir.mkdir(exist_ok=True)
        return str(config_dir / CONFIG_FILE)

    def save(self):
        """保存配置"""
        config_path = self._get_config_path()
        try:
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)
            logger.debug(f"配置已保存: {config_path}")
        except Exception as e:
            logger.error(f"保存配置失败: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值（支持点分隔路径）
        例如: config.get('output.bitrate')
        """
        keys = key.split('.')
        value = self._config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        """
        设置配置值（支持点分隔路径）
        例如: config.set('output.bitrate', '256k')
        """
        keys = key.split('.')
        config = self._config
        for k in keys[:-1]:
            if k not in config or not isinstance(config[k], dict):
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def reset(self):
        """重置为默认配置"""
        self._config = DEFAULT_CONFIG.copy()
        self.save()
        logger.info("配置已重置")

    @property
    def output(self) -> dict:
        return self._config.get('output', {})

    @property
    def processing(self) -> dict:
        return self._config.get('processing', {})

    @property
    def ui(self) -> dict:
        return self._config.get('ui', {})


# 全局配置实例
config = ConfigManager()