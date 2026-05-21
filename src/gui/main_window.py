"""
音乐格式转换工具 v2.0 - GUI 主窗口
功能:
  - 拖入即转换
  - 状态可视化看板（等待/解密/编码/完成/失败）
  - 总进度条 + 预估时间 + 转换速度
  - 一键重试失败任务
  - 完成后动作（打开文件夹/关机）
  - 高级音频设置面板
  - 文件名模板自定义
"""

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import logging
import time
from pathlib import Path

from src.decryptors import DecryptorRegistry
from src.converter import AudioConverter, FFMPEG_PATH
from src.format_detector import FormatDetector
from src.task_manager import TaskManager, TaskStatus, TaskItem, BatchProgress
from src.metadata import MetadataManager
from src.config import config

logger = logging.getLogger(__name__)


class MusicConverterGUI:
    """音乐格式转换器 GUI v2.0"""

    # 状态图标映射
    STATUS_ICONS = {
        TaskStatus.PENDING: '⏳',
        TaskStatus.DECRYPTING: '🔓',
        TaskStatus.ENCODING: '🔄',
        TaskStatus.DONE: '✅',
        TaskStatus.FAILED: '❌',
        TaskStatus.CANCELLED: '⚠️',
    }

    STATUS_COLORS = {
        TaskStatus.PENDING: '#757575',
        TaskStatus.DECRYPTING: '#FF9800',
        TaskStatus.ENCODING: '#2196F3',
        TaskStatus.DONE: '#4CAF50',
        TaskStatus.FAILED: '#F44336',
        TaskStatus.CANCELLED: '#9E9E9E',
    }

    def __init__(self, root):
        self.root = root
        self.root.title(f"音乐格式转换工具 v{config.get('version', '2.0.0')}")
        self.root.geometry(f"{config.get('ui.window_width', 1200)}x{config.get('ui.window_height', 850)}")
        self.root.minsize(1000, 750)

        # 任务管理器
        self.task_manager = TaskManager()
        self._setup_task_callbacks()

        # 状态
        self.is_converting = False

        # 日志颜色
        self.colors = {
            'primary': '#2196F3',
            'primary_dark': '#1976D2',
            'success': '#4CAF50',
            'warning': '#FF9800',
            'error': '#F44336',
            'bg': '#F5F5F5',
            'surface': '#FFFFFF',
            'text': '#212121',
            'text_secondary': '#757575',
        }

        # 样式配置
        self._setup_styles()

        # 创建界面
        self._create_menu()
        self._create_widgets()

        # 日志系统
        self._setup_logging()

        # 拖拽支持
        self._setup_drop_target()

    def _setup_styles(self):
        """配置 UI 样式"""
        style = ttk.Style()
        style.theme_use('clam')

        self.root.configure(bg=self.colors['bg'])

        style.configure('Custom.Treeview', rowheight=32, font=('Microsoft YaHei UI', 11))
        style.configure('Custom.Treeview.Heading', font=('Microsoft YaHei UI', 11, 'bold'))
        style.configure('Primary.TButton', font=('Microsoft YaHei UI', 12, 'bold'))
        style.configure('Status.TLabel', font=('Microsoft YaHei UI', 10))
        style.configure('Header.TLabel', font=('Microsoft YaHei UI', 13, 'bold'))

    def _create_menu(self):
        """创建菜单栏"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        # 文件菜单
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="文件", menu=file_menu)
        file_menu.add_command(label="添加文件...", command=self._add_files, accelerator="Ctrl+O")
        file_menu.add_command(label="添加文件夹...", command=self._add_folder, accelerator="Ctrl+Shift+O")
        file_menu.add_separator()
        file_menu.add_command(label="清空列表", command=self._clear_list)
        file_menu.add_separator()
        file_menu.add_command(label="退出", command=self.root.quit)

        # 转换菜单
        convert_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="转换", menu=convert_menu)
        convert_menu.add_command(label="开始转换", command=self._start_convert, accelerator="F5")
        convert_menu.add_command(label="取消转换", command=self._cancel_convert, accelerator="Esc")
        convert_menu.add_separator()
        convert_menu.add_command(label="重试失败任务", command=self._retry_failed)

        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(label="高级设置...", command=self._show_settings)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="关于...", command=self._show_about)

        # 快捷键
        self.root.bind('<Control-o>', lambda e: self._add_files())
        self.root.bind('<Control-O>', lambda e: self._add_folder())
        self.root.bind('<F5>', lambda e: self._start_convert())
        self.root.bind('<Escape>', lambda e: self._cancel_convert())

    def _create_widgets(self):
        """创建所有 GUI 组件"""
        main_frame = ttk.Frame(self.root, padding=8)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 上半部分: 文件列表
        self._create_file_section(main_frame)

        # 中部: 设置 + 状态面板 (使用 PanedWindow)
        mid_frame = ttk.Frame(main_frame)
        mid_frame.pack(fill=tk.X, pady=(0, 8))

        self._create_settings_section(mid_frame)
        self._create_status_panel(mid_frame)

        # 下半部分: 进度 + 日志
        self._create_progress_section(main_frame)

    def _create_file_section(self, parent):
        """文件列表区域"""
        frame = ttk.LabelFrame(parent, text=" 📁 文件列表 ", padding=5)
        frame.pack(fill=tk.BOTH, expand=True, pady=(0, 8))

        # 按钮栏
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 5))

        ttk.Button(btn_frame, text="➕ 添加文件", command=self._add_files).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="📂 添加文件夹", command=self._add_folder).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🗑️ 移除选中", command=self._remove_selected).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🗑️ 清空", command=self._clear_list).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="🔄 重试失败", command=self._retry_failed).pack(side=tk.LEFT, padx=(0, 5))

        self.file_count_label = ttk.Label(btn_frame, text="共 0 个文件",
                                          foreground=self.colors['text_secondary'])
        self.file_count_label.pack(side=tk.RIGHT)

        # 文件列表 Treeview
        columns = ('filename', 'format', 'platform', 'size', 'status', 'time')
        self.file_tree = ttk.Treeview(frame, columns=columns, show='headings',
                                       style='Custom.Treeview', selectmode='extended')

        self.file_tree.heading('filename', text='文件名', anchor='w')
        self.file_tree.heading('format', text='格式', anchor='center')
        self.file_tree.heading('platform', text='平台', anchor='center')
        self.file_tree.heading('size', text='大小', anchor='center')
        self.file_tree.heading('status', text='状态', anchor='center')
        self.file_tree.heading('time', text='耗时', anchor='center')

        self.file_tree.column('filename', width=420, minwidth=250)
        self.file_tree.column('format', width=100, minwidth=80, anchor='center')
        self.file_tree.column('platform', width=120, minwidth=90, anchor='center')
        self.file_tree.column('size', width=100, minwidth=80, anchor='center')
        self.file_tree.column('status', width=150, minwidth=100, anchor='center')
        self.file_tree.column('time', width=100, minwidth=80, anchor='center')

        scrollbar_y = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scrollbar_y.set)
        self.file_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)

        # 右键菜单
        self.context_menu = tk.Menu(self.root, tearoff=0)
        self.context_menu.add_command(label="重试", command=self._retry_selected)
        self.context_menu.add_command(label="移除", command=self._remove_selected)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="打开文件所在目录", command=self._open_file_dir)
        self.file_tree.bind('<Button-3>', self._show_context_menu)

        # 拖拽提示
        ttk.Label(frame, text="💡 提示：可拖拽文件或文件夹到窗口 | 右键菜单可重试失败任务",
                  foreground=self.colors['text_secondary'],
                  font=('Microsoft YaHei UI', 9)).pack(anchor='w', pady=(3, 0))

    def _create_settings_section(self, parent):
        """设置区域"""
        frame = ttk.LabelFrame(parent, text=" ⚙️ 转换设置 ", padding=8)
        frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))

        # 输出目录
        row1 = ttk.Frame(frame)
        row1.pack(fill=tk.X, pady=(0, 5))
        ttk.Label(row1, text="输出目录：").pack(side=tk.LEFT)
        self.output_dir = tk.StringVar(value=config.get('output.output_dir', ''))
        self.output_dir_entry = ttk.Entry(row1, textvariable=self.output_dir, width=30)
        self.output_dir_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        ttk.Button(row1, text="浏览", command=self._select_output_dir, width=6).pack(side=tk.LEFT)

        self.same_dir_var = tk.BooleanVar(value=config.get('output.output_to_source_dir', True))
        ttk.Checkbutton(row1, text="源文件目录", variable=self.same_dir_var,
                        command=self._toggle_output_dir).pack(side=tk.LEFT, padx=(5, 0))

        # 比特率 + 输出格式
        row2 = ttk.Frame(frame)
        row2.pack(fill=tk.X, pady=(0, 5))

        ttk.Label(row2, text="比特率：").pack(side=tk.LEFT)
        self.bitrate = tk.StringVar(value=config.get('output.bitrate', '320k'))
        bitrate_combo = ttk.Combobox(row2, textvariable=self.bitrate, width=8,
                                      values=['128k', '192k', '256k', '320k'],
                                      state='readonly')
        bitrate_combo.pack(side=tk.LEFT, padx=(2, 15))

        ttk.Label(row2, text="输出：").pack(side=tk.LEFT)
        self.output_format = tk.StringVar(value=config.get('output.output_format', 'mp3'))
        format_combo = ttk.Combobox(row2, textvariable=self.output_format, width=8,
                                     values=['mp3', 'flac'],
                                     state='readonly')
        format_combo.pack(side=tk.LEFT, padx=(2, 15))

        self.preserve_lossless = tk.BooleanVar(value=config.get('output.preserve_lossless', False))
        ttk.Checkbutton(row2, text="保留无损", variable=self.preserve_lossless).pack(side=tk.LEFT)

        # 文件名模板
        row3 = ttk.Frame(frame)
        row3.pack(fill=tk.X, pady=(0, 3))
        ttk.Label(row3, text="文件名：").pack(side=tk.LEFT)
        self.filename_template = tk.StringVar(value=config.get('output.filename_template', '{歌手} - {歌名}'))
        ttk.Entry(row3, textvariable=self.filename_template, width=30).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 5))
        ttk.Label(row3, text="{歌手} {歌名} {专辑} {序号}",
                  foreground=self.colors['text_secondary'],
                  font=('Microsoft YaHei UI', 9)).pack(side=tk.LEFT)

    def _create_status_panel(self, parent):
        """状态看板"""
        frame = ttk.LabelFrame(parent, text=" 📊 状态看板 ", padding=8)
        frame.pack(side=tk.RIGHT, fill=tk.BOTH, padx=(4, 0))

        # 统计数据
        self.status_labels = {}
        statuses = [
            ('pending', '⏳ 等待', '#757575'),
            ('decrypting', '🔓 解密', '#FF9800'),
            ('encoding', '🔄 编码', '#2196F3'),
            ('done', '✅ 完成', '#4CAF50'),
            ('failed', '❌ 失败', '#F44336'),
        ]

        for key, label, color in statuses:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=1)
            ttk.Label(row, text=label, foreground=color, font=('Microsoft YaHei UI', 10)).pack(side=tk.LEFT)
            lbl = ttk.Label(row, text="0", font=('Microsoft YaHei UI', 13, 'bold'), foreground=color)
            lbl.pack(side=tk.RIGHT)
            self.status_labels[key] = lbl

        # 速度和时间
        sep = ttk.Separator(frame, orient=tk.HORIZONTAL)
        sep.pack(fill=tk.X, pady=5)

        row_speed = ttk.Frame(frame)
        row_speed.pack(fill=tk.X, pady=1)
        ttk.Label(row_speed, text="🚀 速度：").pack(side=tk.LEFT)
        self.speed_label = ttk.Label(row_speed, text="--", font=('Microsoft YaHei UI', 11, 'bold'))
        self.speed_label.pack(side=tk.RIGHT)

        row_eta = ttk.Frame(frame)
        row_eta.pack(fill=tk.X, pady=1)
        ttk.Label(row_eta, text="⏱️ 剩余：").pack(side=tk.LEFT)
        self.eta_label = ttk.Label(row_eta, text="--", font=('Microsoft YaHei UI', 11, 'bold'))
        self.eta_label.pack(side=tk.RIGHT)

    def _create_progress_section(self, parent):
        """进度和日志区域"""
        frame = ttk.LabelFrame(parent, text=" 📋 转换进度 ", padding=5)
        frame.pack(fill=tk.BOTH, expand=True)

        # 控制按钮行
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        self.convert_btn = ttk.Button(btn_frame, text="🚀 开始转换",
                                       command=self._start_convert, style='Primary.TButton')
        self.convert_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.cancel_btn = ttk.Button(btn_frame, text="⏹ 取消",
                                      command=self._cancel_convert, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.pause_btn = ttk.Button(btn_frame, text="⏸ 暂停",
                                     command=self._toggle_pause, state=tk.DISABLED)
        self.pause_btn.pack(side=tk.LEFT, padx=(0, 20))

        # 完成后动作
        ttk.Label(btn_frame, text="完成后：").pack(side=tk.LEFT)
        self.post_action = tk.StringVar(value=config.get('post_action', 'none'))
        post_combo = ttk.Combobox(btn_frame, textvariable=self.post_action, width=12,
                                   values=['none', 'open_folder', 'shutdown'],
                                   state='readonly')
        post_combo.pack(side=tk.LEFT, padx=(2, 0))
        post_combo.set('none')

        # FFmpeg 状态
        ffmpeg_text = "✅ FFmpeg" if FFMPEG_PATH else "⚠️ 无FFmpeg"
        ffmpeg_color = self.colors['success'] if FFMPEG_PATH else self.colors['warning']
        ttk.Label(btn_frame, text=ffmpeg_text, foreground=ffmpeg_color,
                  font=('Microsoft YaHei UI', 9)).pack(side=tk.RIGHT)

        # 进度条
        progress_frame = ttk.Frame(frame)
        progress_frame.pack(fill=tk.X, pady=(0, 5))

        self.progress_label = ttk.Label(progress_frame, text="就绪", width=50, anchor='w')
        self.progress_label.pack(side=tk.LEFT)

        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate', length=300)
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 10))

        self.progress_pct = ttk.Label(progress_frame, text="0%", width=6, anchor='e')
        self.progress_pct.pack(side=tk.LEFT)

        # 日志
        self.log_text = scrolledtext.ScrolledText(frame, height=10, font=('Consolas', 11),
                                                   wrap=tk.WORD, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        self.log_text.tag_config('INFO', foreground='#212121')
        self.log_text.tag_config('SUCCESS', foreground='#4CAF50')
        self.log_text.tag_config('WARNING', foreground='#FF9800')
        self.log_text.tag_config('ERROR', foreground='#F44336')
        self.log_text.tag_config('HEADER', foreground='#2196F3', font=('Consolas', 11, 'bold'))

    def _setup_drop_target(self):
        """设置拖拽支持"""
        try:
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop_files)
            self._log_message("✅ 已启用文件拖拽功能 (windnd)", 'SUCCESS')
        except ImportError:
            try:
                self.root.drop_target_register('DND_Files')
                self.root.dnd_bind('<<Drop>>', self._on_tkdnd_drop)
            except Exception:
                self._log_message("💡 安装 windnd 库可启用拖拽功能: pip install windnd", 'INFO')

    def _on_drop_files(self, files):
        """处理拖拽文件（windnd）"""
        if isinstance(files, list):
            file_list = []
            for f in files:
                if isinstance(f, bytes):
                    f = f.decode('utf-8', errors='ignore')
                f = f.strip()
                if os.path.isfile(f):
                    file_list.append(f)
                elif os.path.isdir(f):
                    # 递归扫描文件夹
                    for root_dir, dirs, fnames in os.walk(f):
                        for fn in fnames:
                            fp = os.path.join(root_dir, fn)
                            if FormatDetector.is_audio(fp):
                                file_list.append(fp)
            if file_list:
                self._add_files_to_list(file_list)

    def _on_tkdnd_drop(self, event):
        """处理拖拽文件（tkinterdnd2）"""
        files = event.data.split()
        file_list = []
        for f in files:
            f = f.strip('{}')
            if os.path.isfile(f):
                file_list.append(f)
            elif os.path.isdir(f):
                for root_dir, dirs, fnames in os.walk(f):
                    for fn in fnames:
                        fp = os.path.join(root_dir, fn)
                        if FormatDetector.is_audio(fp):
                            file_list.append(fp)
        if file_list:
            self._add_files_to_list(file_list)

    def _setup_logging(self):
        """配置日志系统"""
        class TextHandler(logging.Handler):
            def __init__(self, gui):
                super().__init__()
                self.gui = gui
            def emit(self, record):
                msg = self.format(record)
                self.gui.root.after(0, self.gui._log_message, msg, record.levelname)

        # 避免重复添加 handler（防止日志重复输出）
        for h in logging.root.handlers[:]:
            if isinstance(h, TextHandler):
                logging.root.removeHandler(h)

        handler = TextHandler(self)
        handler.setFormatter(logging.Formatter('%(message)s'))
        logging.root.addHandler(handler)
        logging.root.setLevel(logging.INFO)

        self._log_message("=" * 60, 'HEADER')
        self._log_message(f"  音乐格式转换工具 v{config.get('version', '2.0.0')}", 'HEADER')
        exts = ', '.join(sorted(DecryptorRegistry.get_all_extensions()))
        self._log_message(f"  支持格式: {exts}", 'HEADER')
        self._log_message("=" * 60, 'HEADER')

    def _setup_task_callbacks(self):
        """设置任务管理器回调"""
        self.task_manager.set_callbacks(
            on_task_start=self._on_task_start,
            on_task_progress=self._on_task_progress,
            on_task_done=self._on_task_done,
            on_task_failed=self._on_task_failed,
            on_batch_done=self._on_batch_done,
            on_log=self._on_log,
            on_duplicate_check=self._on_duplicate_check,
            on_output_dir_missing=self._on_output_dir_missing,
        )

    # ===== 任务管理器回调 =====

    def _on_task_start(self, task: TaskItem):
        """任务开始回调"""
        self.root.after(0, self._update_task_ui, task)

    def _on_task_progress(self, task: TaskItem, progress: float):
        """任务进度回调"""
        self.root.after(0, self._update_task_ui, task)

    def _on_task_done(self, task: TaskItem):
        """任务完成回调"""
        self.root.after(0, self._update_task_ui, task)
        self.root.after(0, self._update_status_panel)

    def _on_task_failed(self, task: TaskItem):
        """任务失败回调"""
        self.root.after(0, self._update_task_ui, task)
        self.root.after(0, self._update_status_panel)

    def _on_batch_done(self, progress: BatchProgress):
        """批量完成回调"""
        self.root.after(0, self._on_convert_complete, progress)

    def _on_log(self, message: str, level: str):
        """日志回调"""
        self.root.after(0, self._log_message, message, level)

    def _update_task_ui(self, task: TaskItem):
        """更新任务在 Treeview 中的显示"""
        iid = None
        for child in self.file_tree.get_children():
            vals = self.file_tree.item(child, 'values')
            if vals and vals[0] == task.filename:
                iid = child
                break

        if iid is None:
            return

        icon = self.STATUS_ICONS.get(task.status, '')
        status_text = f"{icon} {task.status.value}"
        time_text = f"{task.elapsed:.1f}s" if task.elapsed > 0 else ""

        if task.status == TaskStatus.FAILED and task.error_message:
            status_text = f"❌ {task.error_message[:20]}"

        values = list(self.file_tree.item(iid, 'values'))
        values[4] = status_text
        values[5] = time_text
        self.file_tree.item(iid, values=values)

    def _update_status_panel(self):
        """更新状态看板"""
        pending = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.PENDING)
        decrypting = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.DECRYPTING)
        encoding = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.ENCODING)
        done = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.DONE)
        failed = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.FAILED)

        self.status_labels['pending'].config(text=str(pending))
        self.status_labels['decrypting'].config(text=str(decrypting))
        self.status_labels['encoding'].config(text=str(encoding))
        self.status_labels['done'].config(text=str(done))
        self.status_labels['failed'].config(text=str(failed))

        prog = self.task_manager.progress
        self.speed_label.config(text=prog.speed_text if prog.total > 0 else "--")
        self.eta_label.config(text=prog.eta_text if prog.total > 0 else "--")

    # ===== 文件管理 =====

    def _add_files(self):
        """添加文件"""
        ext_groups = [
            ("所有支持的格式", " ".join(f"*{e}" for e in DecryptorRegistry.get_all_extensions() | AudioConverter.AUDIO_EXTENSIONS)),
            ("加密音乐格式", " ".join(f"*{e}" for e in sorted(DecryptorRegistry.get_all_extensions()))),
            ("普通音频格式", "*.flac *.wav *.ogg *.aac *.wma *.m4a *.ape *.wv *.opus"),
        ]
        filetypes = [(name, pattern) for name, pattern in ext_groups]
        filetypes.append(("所有文件", "*.*"))

        files = filedialog.askopenfilenames(title="选择音乐文件", filetypes=filetypes)
        if files:
            self._add_files_to_list(list(files))

    def _add_folder(self):
        """添加文件夹"""
        folder = filedialog.askdirectory(title="选择包含音乐文件的文件夹")
        if folder:
            file_list = []
            for root_dir, dirs, files in os.walk(folder):
                for f in files:
                    fp = os.path.join(root_dir, f)
                    if FormatDetector.is_audio(fp):
                        file_list.append(fp)
            if file_list:
                self._add_files_to_list(file_list)
            else:
                self._log_message(f"未在文件夹中找到支持的音乐文件: {folder}", 'WARNING')

    def _add_files_to_list(self, file_paths):
        """批量添加文件到列表"""
        added = self.task_manager.add_files(file_paths)

        # 刷新 Treeview
        self._refresh_file_tree()

        if added > 0:
            self._log_message(f"已添加 {added} 个文件", 'SUCCESS')
        elif added == 0 and file_paths:
            self._log_message("未添加新文件（可能已存在或格式不支持）", 'WARNING')

    def _remove_selected(self):
        """移除选中文件"""
        selected = self.file_tree.selection()
        if not selected:
            return
        indices = sorted([int(s) for s in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(self.task_manager.tasks):
                self.task_manager.remove_task(self.task_manager.tasks[idx].id)
        self._refresh_file_tree()

    def _clear_list(self):
        """清空文件列表"""
        self.task_manager.clear_tasks()
        self.file_tree.delete(*self.file_tree.get_children())
        self._update_file_count()

    def _refresh_file_tree(self):
        """刷新文件列表显示"""
        self.file_tree.delete(*self.file_tree.get_children())
        for i, task in enumerate(self.task_manager.tasks):
            icon = self.STATUS_ICONS.get(task.status, '')
            size = self._format_size(os.path.getsize(task.input_path)) if os.path.isfile(task.input_path) else "?"
            self.file_tree.insert('', tk.END, iid=str(i), values=(
                task.filename,
                task.source_format or os.path.splitext(task.filename)[1],
                task.platform or '未知',
                size,
                f"{icon} {task.status.value}",
                "",
            ))
        self._update_file_count()

    def _update_file_count(self):
        """更新文件计数"""
        count = len(self.task_manager.tasks)
        self.file_count_label.config(text=f"共 {count} 个文件")

    # ===== 设置 =====

    def _select_output_dir(self):
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_dir.set(folder)
            self.same_dir_var.set(False)

    def _toggle_output_dir(self):
        if self.same_dir_var.get():
            self.output_dir.set("")

    # ===== 右键菜单 =====

    def _show_context_menu(self, event):
        """显示右键菜单"""
        iid = self.file_tree.identify_row(event.y)
        if iid:
            self.file_tree.selection_set(iid)
            self.context_menu.post(event.x_root, event.y_root)

    def _retry_selected(self):
        """重试选中的失败任务"""
        selected = self.file_tree.selection()
        for iid in selected:
            idx = int(iid)
            if 0 <= idx < len(self.task_manager.tasks):
                task = self.task_manager.tasks[idx]
                if task.status == TaskStatus.FAILED:
                    self.task_manager.retry_task(task.id)
        self._refresh_file_tree()

    def _open_file_dir(self):
        """打开文件所在目录"""
        selected = self.file_tree.selection()
        if selected:
            idx = int(selected[0])
            if 0 <= idx < len(self.task_manager.tasks):
                task = self.task_manager.tasks[idx]
                path = task.output_path if task.output_path and os.path.exists(task.output_path) else task.input_path
                if os.path.exists(path):
                    os.startfile(os.path.dirname(path))

    def _retry_failed(self):
        """重试所有失败任务"""
        failed_count = sum(1 for t in self.task_manager.tasks if t.status == TaskStatus.FAILED)
        if failed_count == 0:
            messagebox.showinfo("提示", "没有失败的任务")
            return
        for task in self.task_manager.tasks:
            if task.status == TaskStatus.FAILED:
                task.status = TaskStatus.PENDING
                task.error_message = ""
        self._refresh_file_tree()
        self._start_convert()

    # ===== 转换逻辑 =====

    def _start_convert(self):
        """开始转换"""
        if self.is_converting:
            return

        if not self.task_manager.tasks:
            messagebox.showwarning("提示", "请先添加要转换的音乐文件！")
            return

        # 保存设置到配置
        config.set('output.bitrate', self.bitrate.get())
        config.set('output.output_format', self.output_format.get())
        config.set('output.preserve_lossless', self.preserve_lossless.get())
        config.set('output.output_to_source_dir', self.same_dir_var.get())
        config.set('output.output_dir', self.output_dir.get())
        config.set('output.filename_template', self.filename_template.get())
        config.set('post_action', self.post_action.get())
        config.save()

        self.is_converting = True
        self.convert_btn.config(state=tk.DISABLED)
        self.cancel_btn.config(state=tk.NORMAL)
        self.pause_btn.config(state=tk.NORMAL)
        self.progress_bar['value'] = 0

        # 在后台线程中执行
        thread = threading.Thread(target=self._convert_worker, daemon=True)
        thread.start()

    def _convert_worker(self):
        """转换工作线程"""
        try:
            self.task_manager.start()
        finally:
            self.root.after(0, self._convert_worker_done)

    def _convert_worker_done(self):
        """工作线程完成"""
        self.is_converting = False
        self.convert_btn.config(state=tk.NORMAL)
        self.cancel_btn.config(state=tk.DISABLED)
        self.pause_btn.config(state=tk.DISABLED)
        self._refresh_file_tree()
        self._update_status_panel()

    def _cancel_convert(self):
        """取消转换"""
        if self.is_converting:
            self.task_manager.cancel()

    def _toggle_pause(self):
        """暂停/恢复"""
        if self.task_manager._pause_flag.is_set():
            self.task_manager.pause()
            self.pause_btn.config(text="▶ 继续")
        else:
            self.task_manager.resume()
            self.pause_btn.config(text="⏸ 暂停")

    def _on_convert_complete(self, progress: BatchProgress):
        """转换完成回调"""
        elapsed = progress.elapsed
        elapsed_str = f"{elapsed:.1f}秒" if elapsed < 60 else f"{elapsed/60:.1f}分钟"

        self.progress_bar['value'] = 100
        self.progress_pct.config(text="100%")
        self.progress_label.config(text="转换完成")

        # 执行完成后动作
        post_action = self.post_action.get()
        if post_action == 'open_folder':
            output_dir = self.output_dir.get()
            if output_dir and os.path.isdir(output_dir):
                os.startfile(output_dir)
        elif post_action == 'shutdown':
            if messagebox.askyesno("关机确认", "转换完成后将自动关机，确定吗？"):
                os.system('shutdown /s /t 60')

    # ===== 日志 =====

    def _log_message(self, message, level='INFO'):
        """添加日志消息"""
        self.log_text.config(state=tk.NORMAL)
        tag = level if level in ('INFO', 'SUCCESS', 'WARNING', 'ERROR', 'HEADER') else 'INFO'
        self.log_text.insert(tk.END, message + '\n', tag)
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    # ===== 高级设置 =====

    def _show_settings(self):
        """显示高级设置对话框"""
        settings_win = tk.Toplevel(self.root)
        settings_win.title("高级设置")
        settings_win.geometry("450x400")
        settings_win.resizable(False, False)
        settings_win.transient(self.root)
        settings_win.grab_set()

        frame = ttk.Frame(settings_win, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)

        # 音频设置
        audio_frame = ttk.LabelFrame(frame, text=" 🎵 音频设置 ", padding=10)
        audio_frame.pack(fill=tk.X, pady=(0, 10))

        # 采样率
        row = ttk.Frame(audio_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="采样率：").pack(side=tk.LEFT)
        sample_rate_var = tk.StringVar(value=str(config.get('output.sample_rate', 44100)))
        ttk.Combobox(row, textvariable=sample_rate_var, width=12,
                     values=['44100', '48000'], state='readonly').pack(side=tk.LEFT, padx=5)
        ttk.Label(row, text="Hz", foreground='gray').pack(side=tk.LEFT)

        # 声道
        row = ttk.Frame(audio_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="声道模式：").pack(side=tk.LEFT)
        channels_var = tk.StringVar(value=str(config.get('output.channels', 2)))
        ttk.Combobox(row, textvariable=channels_var, width=12,
                     values=[('2', '立体声'), ('2', '联合立体声'), ('1', '单声道')],
                     state='readonly').pack(side=tk.LEFT, padx=5)

        # 编码模式
        row = ttk.Frame(audio_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="编码模式：").pack(side=tk.LEFT)
        mode_var = tk.StringVar(value=config.get('output.mode', 'cbr'))
        ttk.Combobox(row, textvariable=mode_var, width=12,
                     values=['cbr', 'vbr'], state='readonly').pack(side=tk.LEFT, padx=5)
        ttk.Label(row, text="CBR=恒定码率, VBR=动态码率", foreground='gray',
                  font=('Microsoft YaHei UI', 8)).pack(side=tk.LEFT, padx=5)

        # 并行线程数
        row = ttk.Frame(audio_frame)
        row.pack(fill=tk.X, pady=3)
        ttk.Label(row, text="并行线程：").pack(side=tk.LEFT)
        workers_var = tk.StringVar(value=str(config.get('processing.max_workers', 4)))
        ttk.Combobox(row, textvariable=workers_var, width=8,
                     values=['1', '2', '4', '8'], state='readonly').pack(side=tk.LEFT, padx=5)

        # 处理选项
        proc_frame = ttk.LabelFrame(frame, text=" 📋 处理选项 ", padding=10)
        proc_frame.pack(fill=tk.X, pady=(0, 10))

        embed_cover_var = tk.BooleanVar(value=config.get('processing.embed_cover', True))
        ttk.Checkbutton(proc_frame, text="嵌入封面图片", variable=embed_cover_var).pack(anchor='w')

        embed_lyrics_var = tk.BooleanVar(value=config.get('processing.embed_lyrics', True))
        ttk.Checkbutton(proc_frame, text="嵌入歌词到音频文件 (USLT)", variable=embed_lyrics_var).pack(anchor='w')

        export_lyrics_var = tk.BooleanVar(value=config.get('processing.export_lyrics', True))
        ttk.Checkbutton(proc_frame, text="导出歌词为 .lrc 文件", variable=export_lyrics_var).pack(anchor='w')

        # 按钮
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        def save_settings():
            config.set('output.sample_rate', int(sample_rate_var.get()))
            config.set('output.channels', int(channels_var.get()))
            config.set('output.mode', mode_var.get())
            config.set('processing.max_workers', int(workers_var.get()))
            config.set('processing.embed_cover', embed_cover_var.get())
            config.set('processing.embed_lyrics', embed_lyrics_var.get())
            config.set('processing.export_lyrics', export_lyrics_var.get())
            config.save()
            # 更新任务管理器线程数
            self.task_manager.max_workers = int(workers_var.get())
            self._log_message("✅ 设置已保存", 'SUCCESS')
            settings_win.destroy()

        ttk.Button(btn_frame, text="保存", command=save_settings, style='Primary.TButton').pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="取消", command=settings_win.destroy).pack(side=tk.RIGHT)

    def _show_about(self):
        """显示关于对话框"""
        about_win = tk.Toplevel(self.root)
        about_win.title("关于")
        about_win.geometry("480x520")
        about_win.resizable(False, False)
        about_win.transient(self.root)
        about_win.grab_set()

        frame = ttk.Frame(about_win, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        # 应用图标和名称
        ttk.Label(frame, text="🎵 音乐格式转换工具",
                  font=('Microsoft YaHei UI', 16, 'bold'),
                  foreground=self.colors['primary']).pack(pady=(0, 2))

        version = config.get('version', '2.0.0')
        ttk.Label(frame, text=f"v{version}",
                  font=('Microsoft YaHei UI', 12),
                  foreground=self.colors['text_secondary']).pack(pady=(0, 10))

        # 作者信息
        info_frame = ttk.Frame(frame)
        info_frame.pack(fill=tk.X, pady=(0, 10))

        info_items = [
            ("作者", "Hsin"),
            ("年份", "© 2026"),
            ("版本", f"v{version}"),
        ]
        for label, value in info_items:
            row = ttk.Frame(info_frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}：", font=('Microsoft YaHei UI', 10),
                      foreground=self.colors['text_secondary']).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=('Microsoft YaHei UI', 10, 'bold')).pack(side=tk.LEFT)

        # 分隔线
        ttk.Separator(frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # 支持平台
        platforms_frame = ttk.LabelFrame(frame, text=" 支持平台 ", padding=8)
        platforms_frame.pack(fill=tk.X, pady=(0, 8))

        platforms = [
            "网易云音乐 (.ncm)",
            "QQ音乐 (.qmc*/.mflac*/.mgg*/.tkm)",
            "酷狗音乐 (.kgm/.kgma)",
            "酷我音乐 (.kwm/.vpr)",
            "喜马拉雅 (.xm)",
        ]
        for p in platforms:
            ttk.Label(platforms_frame, text=f"  • {p}",
                      font=('Microsoft YaHei UI', 9)).pack(anchor='w')

        # 功能特性
        features_frame = ttk.LabelFrame(frame, text=" 功能特性 ", padding=8)
        features_frame.pack(fill=tk.X, pady=(0, 8))

        features = [
            "文件头魔数自动识别平台",
            "多线程并行转换",
            "元数据智能修复",
            "封面/歌词嵌入",
            "自定义文件名模板",
            "支持保留无损格式",
        ]
        for f in features:
            ttk.Label(features_frame, text=f"  • {f}",
                      font=('Microsoft YaHei UI', 9)).pack(anchor='w')

        # 关闭按钮
        ttk.Button(frame, text="确定", command=about_win.destroy,
                   style='Primary.TButton', width=12).pack(pady=(5, 0))

        # 居中显示
        about_win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - about_win.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - about_win.winfo_height()) // 2
        about_win.geometry(f"+{x}+{y}")

    # ===== 重复检测 =====

    def _on_duplicate_check(self, title: str, artist: str, existing_info: dict, dup_type: str = 'same_spec') -> str:
        """
        重复检测回调 - 在主线程中显示对话框询问用户。

        Args:
            title: 歌曲标题
            artist: 歌手名
            existing_info: 已存在文件信息
            dup_type: 重复类型 'same_spec'(同名同规格) 或 'diff_spec'(同名不同规格)

        Returns:
            'skip' / 'skip_all' / 'overwrite' / 'overwrite_all' / 'version' / 'version_all'
        """
        # 使用 threading.Event 同步等待用户选择
        result = ['skip']
        event = threading.Event()

        def show_dialog():
            try:
                existing_name = existing_info.get('filename', '未知文件')
                existing_bitrate = existing_info.get('bitrate', 0)
                new_bitrate = existing_info.get('new_bitrate', 0)
                bitrate_str = f"{existing_bitrate}kbps" if existing_bitrate > 0 else "未知规格"

                dialog = tk.Toplevel(self.root)
                dialog.title("发现重复文件" if dup_type == 'same_spec' else "发现同名不同规格文件")
                dialog.geometry("520x280")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()

                frame = ttk.Frame(dialog, padding=15)
                frame.pack(fill=tk.BOTH, expand=True)

                if dup_type == 'same_spec':
                    # 同名同规格
                    info_text = (
                        f"🎵 发现目标文件夹中已存在相同歌曲（同规格）：\n\n"
                        f"  歌曲: {title}\n"
                        f"  歌手: {artist}\n"
                        f"  已存在: {existing_name}\n"
                        f"  规格: {bitrate_str}\n\n"
                        f"请选择处理方式："
                    )
                else:
                    # 同名不同规格
                    info_text = (
                        f"🎵 发现目标文件夹中已存在相同歌曲（不同规格）：\n\n"
                        f"  歌曲: {title}\n"
                        f"  歌手: {artist}\n"
                        f"  已存在: {existing_name}\n"
                        f"  现有规格: {bitrate_str}\n"
                        f"  新规格: {new_bitrate}kbps\n\n"
                        f"请选择处理方式："
                    )

                ttk.Label(frame, text=info_text, justify=tk.LEFT,
                         font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(0, 10))

                # 按钮区域
                btn_frame = ttk.Frame(frame)
                btn_frame.pack(fill=tk.X, pady=(5, 0))

                btn_frame2 = ttk.Frame(frame)
                btn_frame2.pack(fill=tk.X, pady=(5, 0))

                def on_overwrite():
                    result[0] = 'overwrite'
                    dialog.destroy()
                    event.set()

                def on_overwrite_all():
                    result[0] = 'overwrite_all'
                    dialog.destroy()
                    event.set()

                def on_version():
                    result[0] = 'version'
                    dialog.destroy()
                    event.set()

                def on_version_all():
                    result[0] = 'version_all'
                    dialog.destroy()
                    event.set()

                def on_skip():
                    result[0] = 'skip'
                    dialog.destroy()
                    event.set()

                def on_skip_all():
                    result[0] = 'skip_all'
                    dialog.destroy()
                    event.set()

                # 第一行：覆盖和版本化
                ttk.Button(btn_frame, text="📄 覆盖源文件", command=on_overwrite, width=16).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Button(btn_frame, text="📋 覆盖全部", command=on_overwrite_all, width=14).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Button(btn_frame, text="📑 保存多个版本", command=on_version, width=16).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Button(btn_frame, text="📑 版本化全部", command=on_version_all, width=14).pack(side=tk.LEFT)

                # 第二行：跳过
                ttk.Button(btn_frame2, text="⏭ 跳过此文件", command=on_skip, width=16).pack(side=tk.LEFT, padx=(0, 5))
                ttk.Button(btn_frame2, text="⏭ 全部跳过", command=on_skip_all, width=14).pack(side=tk.LEFT)

                # 居中显示
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
                dialog.geometry(f"+{x}+{y}")

                # 关闭窗口时默认跳过
                dialog.protocol("WM_DELETE_WINDOW", on_skip)

            except Exception as e:
                logger.error(f"重复检测对话框错误: {e}")
                result[0] = 'skip'
                event.set()

        # 在主线程中显示对话框
        self.root.after(0, show_dialog)
        # 等待用户选择（阻塞工作线程）
        event.wait(timeout=300)  # 5分钟超时

        return result[0]

    def _on_output_dir_missing(self, dir_path: str) -> str:
        """
        输出目录不存在回调 - 在主线程中显示对话框询问用户。

        Args:
            dir_path: 不存在的目录路径

        Returns:
            'create' / 'skip'
        """
        result = ['skip']
        event = threading.Event()

        def show_dialog():
            try:
                dialog = tk.Toplevel(self.root)
                dialog.title("输出目录不存在")
                dialog.geometry("480x180")
                dialog.resizable(False, False)
                dialog.transient(self.root)
                dialog.grab_set()

                frame = ttk.Frame(dialog, padding=15)
                frame.pack(fill=tk.BOTH, expand=True)

                info_text = (
                    f"📁 目标输出目录不存在：\n\n"
                    f"  {dir_path}\n\n"
                    f"是否自动创建该目录？"
                )
                ttk.Label(frame, text=info_text, justify=tk.LEFT,
                         font=('Microsoft YaHei UI', 10)).pack(anchor='w', pady=(0, 10))

                btn_frame = ttk.Frame(frame)
                btn_frame.pack(fill=tk.X, pady=(5, 0))

                def on_create():
                    result[0] = 'create'
                    dialog.destroy()
                    event.set()

                def on_skip():
                    result[0] = 'skip'
                    dialog.destroy()
                    event.set()

                ttk.Button(btn_frame, text="📁 创建目录", command=on_create, width=14).pack(side=tk.LEFT, padx=(0, 10))
                ttk.Button(btn_frame, text="⏭ 跳过", command=on_skip, width=14).pack(side=tk.LEFT)

                # 居中显示
                dialog.update_idletasks()
                x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
                y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
                dialog.geometry(f"+{x}+{y}")

                dialog.protocol("WM_DELETE_WINDOW", on_skip)

            except Exception as e:
                logger.error(f"目录检查对话框错误: {e}")
                result[0] = 'skip'
                event.set()

        self.root.after(0, show_dialog)
        event.wait(timeout=300)

        return result[0]

    # ===== 工具方法 =====

    @staticmethod
    def _format_size(size_bytes):
        """格式化文件大小"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def run_gui():
    """启动 GUI 应用"""
    root = tk.Tk()

    # DPI 感知（Windows 高分屏适配）
    try:
        from ctypes import windll
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # 获取系统 DPI 缩放比例并设置 tkinter 缩放
    try:
        from ctypes import windll, byref, sizeof, c_int
        dpi = windll.user32.GetDpiForSystem()
        if dpi > 0:
            scale_factor = dpi / 96.0
            root.tk.call('tk', 'scaling', scale_factor)
    except Exception:
        pass

    app = MusicConverterGUI(root)
    root.mainloop()
