# 🎵 音乐格式转换工具 v2.0

将网易云音乐、QQ音乐、酷狗音乐、酷我音乐、喜马拉雅等平台下载的加密音乐文件转换为标准 MP3/FLAC 格式。

## ✨ 功能特点

- **多平台支持**：网易云 (.ncm)、QQ音乐 (.qmc*/.mflac*/.mgg*/.tkm/.ogg)、酷狗 (.kgm/.kgma)、酷我 (.kwm/.vpr)、喜马拉雅 (.xm)
- **文件头魔数自动识别**：拖入文件自动识别所属平台，无需手动选择
- **批量并行转换**：多线程并行处理，充分利用多核 CPU
- **元数据智能修复**：自动提取并写入歌名、歌手、专辑、流派、年份、封面、歌词
- **歌词支持**：导出 .lrc 文件 + 嵌入 USLT 歌词帧
- **自定义文件名**：支持 `{歌手} - {歌名}` 等模板
- **保留无损**：FLAC 内核可选择保留为 .flac 或转为 .mp3
- **GUI 界面**：直观的状态看板、进度条、预估时间、转换速度
- **一键重试**：失败任务可单独或批量重试
- **高级设置**：CBR/VBR、采样率、声道模式、并行线程数
- **配置持久化**：设置自动保存，下次启动自动恢复
- **命令行支持**：也支持通过命令行直接转换文件

## 📋 支持的格式

| 平台 | 加密格式 | 解密后格式 |
|------|---------|-----------|
| 网易云音乐 | `.ncm` | MP3 / FLAC |
| QQ音乐 | `.qmc0` `.qmc2` `.qmc3` `.qmcflac` `.qmcogg` `.tkm` | MP3 / OGG / FLAC |
| QQ音乐 | `.mflac` `.mflac0` `.mgg` `.mgg1` `.mggl` | FLAC / OGG |
| QQ音乐DRM | `.ogg`（新版DRM加密） | OGG（需QQ音乐运行+Frida） |
| 酷狗音乐 | `.kgm` `.kgma` | MP3 |
| 酷我音乐 | `.kwm` `.vpr` | MP3 / FLAC |
| 喜马拉雅 | `.xm` | MP3 |

同时支持普通音频格式：`.flac` `.wav` `.ogg` `.aac` `.wma` `.m4a` `.ape` `.wv` `.opus`

## 🚀 安装

### 1. 环境要求

- Python 3.8+
- FFmpeg（推荐，用于音频转换）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 安装 FFmpeg（推荐）

- 访问 https://ffmpeg.org/download.html 下载
- 将 ffmpeg.exe 放到系统 PATH 中，或放到 `C:\ffmpeg\bin\` 目录
- 也可通过 `pip install imageio-ffmpeg` 自动获取

### 4. QQ音乐 DRM OGG 支持（可选）

新版QQ音乐下载的 `.ogg` 文件使用了应用级 DRM 加密，需要以下额外步骤：

```bash
pip install frida frida-tools psutil
```

**使用方法**：
1. 启动 QQ 音乐客户端 (QQMusic.exe)，确保已登录 VIP 账号
2. 运行本工具，拖入 DRM 加密的 `.ogg` 文件
3. 工具会自动通过 Frida 注入 QQ 音乐进程完成解密

> ⚠️ 此功能需要 QQ 音乐客户端处于运行状态

## 📖 使用方法

### GUI 模式（推荐）

```bash
python main.py
```

1. 拖拽文件/文件夹到窗口，或点击按钮添加
2. 设置输出目录、比特率、输出格式
3. 点击「开始转换」
4. 支持暂停/取消/重试

### 命令行模式

```bash
# 转换单个文件
python main.py "歌曲.ncm"

# 批量转换
python main.py "歌曲1.ncm" "歌曲2.mflac" "歌曲3.kgm"

# 查看帮助
python main.py -h
```

## 🏗️ 项目结构

```
netease_music_converter/
├── main.py                   # 主入口文件
├── requirements.txt          # 依赖列表
├── README.md                 # 项目说明
└── src/
    ├── __init__.py           # 包初始化 (v2.0)
    ├── decryptor.py          # 解密兼容层
    ├── converter.py          # 音频转换模块 (v2.0)
    ├── format_detector.py    # 文件头魔数识别
    ├── metadata.py           # 元数据管理器
    ├── config.py             # 配置持久化
    ├── task_manager.py       # 批量任务管理器
    ├── decryptors/           # 解密器子包
    │   ├── __init__.py       # 统一接口 + 注册中心
    │   ├── base.py           # 基类 + DecryptResult
    │   ├── ncm.py            # 网易云解密器
    │   ├── qmc.py            # QQ音乐解密器
    │   ├── kgm.py            # 酷狗解密器
    │   ├── kwm.py            # 酷我解密器
    │   ├── vpr.py            # 酷我VIP解密器
    │   ├── xm.py             # 喜马拉雅解密器
    │   ├── qq_ogg.py         # QQ音乐DRM解密器 (Frida)
    │   └── qq_ogg_hook.js    # Frida Hook 脚本
    └── gui/                  # GUI 模块
        ├── __init__.py
        └── main_window.py    # 主窗口 (v2.0)
```

## ⚙️ 高级设置

在 GUI 中通过 **设置 → 高级设置** 打开：

- **采样率**：44100 Hz / 48000 Hz
- **声道模式**：立体声 / 联合立体声 / 单声道
- **编码模式**：CBR（恒定码率）/ VBR（动态码率）
- **并行线程数**：1 / 2 / 4 / 8
- **嵌入封面**：自动提取并嵌入封面图片
- **歌词处理**：嵌入歌词到音频文件 + 导出 .lrc 文件

## 🔌 解密插件架构

解密器采用模块化设计，支持热加载：

1. 在 `src/decryptors/` 目录下创建新的解密器 `.py` 文件
2. 继承 `BaseDecryptor` 并实现 `decrypt_file` 方法
3. 在 `__init__.py` 中注册即可

## ⚠️ 注意事项

1. 请确保您有权处理这些音乐文件
2. 建议安装 FFmpeg 以获得最佳转换质量和速度
3. 部分格式的解密算法可能因平台更新而失效，欢迎提交 Issue
4. 配置文件保存在 `~/.netease_music_converter/config.json`
5. QQ音乐DRM加密的 `.ogg` 文件需要 QQ 音乐客户端运行 + Frida 库

## 📄 许可证

本项目仅供学习研究使用，请勿用于商业用途。