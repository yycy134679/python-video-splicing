from __future__ import annotations

import os
import shutil
from pathlib import Path

from .models import Config


DEFAULT_ENDCARD_PATH = Path(
    "/Users/bytedance/Documents/Code/python-video-splicing/assets/video/endcard.mp4"
)


def _read_positive_int(env_name: str, default: int) -> int:
    raw = os.getenv(env_name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


def load_config() -> Config:
    endcard_path = Path(os.getenv("SP_ENDCARD_PATH", str(DEFAULT_ENDCARD_PATH))).expanduser()
    return Config(
        endcard_path=endcard_path,
        max_video_mb=_read_positive_int("SP_MAX_VIDEO_MB", 50),
        max_workers=_read_positive_int("SP_MAX_WORKERS", 6),
        task_timeout_sec=_read_positive_int("SP_TASK_TIMEOUT_SEC", 180),
        download_retries=_read_positive_int("SP_DOWNLOAD_RETRIES", 2),
    )


def validate_runtime(config: Config) -> list[str]:
    errors: list[str] = []
    if not config.endcard_path.is_file():
        errors.append(f"落版视频不存在: {config.endcard_path}")
    if shutil.which("ffmpeg") is None:
        errors.append("未找到 ffmpeg 可执行文件")
    if shutil.which("ffprobe") is None:
        errors.append("未找到 ffprobe 可执行文件")
    return errors
