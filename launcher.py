#!/usr/bin/env python3
"""
视频拼接工具启动器
用于在打包的 macOS .app 中启动 Streamlit 应用

核心原理：
- PyInstaller 打包后，sys.executable 指向冻结二进制，不能当 Python 用
- 所以不能用 subprocess 调用 `python -m streamlit`
- 正确做法是直接在进程内调用 Streamlit 的 CLI 入口
"""
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def _get_base_path() -> Path:
    """获取资源根目录（兼容 PyInstaller 打包环境和开发环境）"""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def _setup_environment(base_path: Path) -> None:
    """设置运行环境"""
    # 将打包目录加入 PATH，使 ffmpeg / ffprobe 可被 shutil.which 找到
    os.environ["PATH"] = f"{base_path}:{os.environ.get('PATH', '')}"

    # 指定落版视频路径（覆盖 config.py 中的硬编码默认值）
    endcard = base_path / "assets" / "video" / "endcard.mp4"
    if endcard.exists():
        os.environ["SP_ENDCARD_PATH"] = str(endcard)


def _open_browser_later(url: str, delay: float = 4.0) -> None:
    """后台线程延迟打开浏览器"""
    def _open():
        time.sleep(delay)
        webbrowser.open(url)
    threading.Thread(target=_open, daemon=True).start()


def main() -> None:
    base_path = _get_base_path()
    _setup_environment(base_path)

    app_script = str(base_path / "app.py")
    if not Path(app_script).exists():
        print(f"错误：找不到应用入口 {app_script}")
        sys.exit(1)

    port = "8501"

    # 后台打开浏览器
    _open_browser_later(f"http://localhost:{port}")

    # 构造 Streamlit CLI 参数（在同一进程内调用，无需 subprocess）
    sys.argv = [
        "streamlit", "run", app_script,
        "--server.port", port,
        "--server.headless", "true",
        "--server.fileWatcherType", "none",
        "--browser.gatherUsageStats", "false",
        "--global.developmentMode", "false",
    ]

    from streamlit.web.cli import main as st_main  # noqa: E402
    st_main()


if __name__ == "__main__":
    main()
