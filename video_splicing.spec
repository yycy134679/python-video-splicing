# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec 文件 - 视频拼接工具 macOS 打包配置

注意：
- 不使用 PyInstaller 的 BUNDLE 步骤（中文名 + 缺少 icon 会导致空 .app）
- .app 结构由 build_macos_app.sh 手动创建，更可靠
"""
import subprocess
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

block_cipher = None
project_root = Path(SPECPATH)

# ---------- FFmpeg 路径自动检测 ----------
def _which(name: str) -> str:
    result = subprocess.run(['which', name], capture_output=True, text=True)
    path = result.stdout.strip()
    if not path:
        raise FileNotFoundError(f"找不到 {name}，请先运行: brew install ffmpeg")
    return path

ffmpeg_path = _which('ffmpeg')
ffprobe_path = _which('ffprobe')

# ---------- 数据文件 ----------
# Streamlit 前端静态资源和运行时文件（必须完整收集）
streamlit_datas = collect_data_files('streamlit')

# 包元数据（Streamlit 用 importlib.metadata 读取版本号，缺失会崩溃）
def _safe_copy_metadata(*names):
    """安全收集包元数据，忽略不存在的包"""
    result = []
    for name in names:
        try:
            result += copy_metadata(name)
        except Exception:
            pass
    return result

pkg_metadata = _safe_copy_metadata(
    'streamlit',
    'streamlit-nightly',
    'altair',
    'pandas',
    'requests',
    'rich',
    'importlib_metadata',
    'click',
    'tornado',
    'packaging',
    'numpy',
    'openpyxl',
    'validators',
    'watchdog',
)

datas = streamlit_datas + pkg_metadata + [
    # 应用源码（Streamlit 需要读取 .py 文件并 exec 执行）
    ('app.py', '.'),
    ('video_splicer', 'video_splicer'),
    # 落版视频资源
    ('assets', 'assets'),
]

# ---------- 隐藏导入 ----------
# Streamlit 子模块（大量动态导入，必须完整收集）
streamlit_hiddenimports = collect_submodules('streamlit')

hiddenimports = streamlit_hiddenimports + [
    # 项目模块（app.py 的 import 在 exec 时解析，PyInstaller 分析不到）
    'video_splicer',
    'video_splicer.artifact',
    'video_splicer.config',
    'video_splicer.downloader',
    'video_splicer.ffmpeg_pipeline',
    'video_splicer.input_parser',
    'video_splicer.models',
    'video_splicer.runner',
    # 第三方库
    'pandas',
    'openpyxl',
    'requests',
    'altair',
    'click',
    'tornado',
    'validators',
    'watchdog',
]

# ---------- Analysis ----------
a = Analysis(
    ['launcher.py'],
    pathex=[str(project_root)],
    binaries=[
        (ffmpeg_path, '.'),
        (ffprobe_path, '.'),
    ],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'numpy.testing',
        'tkinter',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VideoSplicer',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

# 只做 COLLECT，不做 BUNDLE（.app 由 build_macos_app.sh 手动创建）
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VideoSplicer',
)
