from __future__ import annotations

from dataclasses import replace
import os
import shutil
from pathlib import Path

from .endcard_store import resolve_active_endcard
from .models import Config


DEFAULT_ENDCARD_PATH = Path(
    "/Users/bytedance/Documents/Code/python-video-splicing/assets/video/endcard.mp4"
)
DEFAULT_RESULTS_ROOT_DIR = Path.home() / "Downloads" / "video-splicer-results"


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
    default_endcard_path = Path(os.getenv("SP_ENDCARD_PATH", str(DEFAULT_ENDCARD_PATH))).expanduser()
    endcard_path = resolve_active_endcard(default_endcard=default_endcard_path).path
    results_root_dir = Path(os.getenv("SP_RESULTS_ROOT_DIR", str(DEFAULT_RESULTS_ROOT_DIR))).expanduser()
    return Config(
        endcard_path=endcard_path,
        results_root_dir=results_root_dir,
        max_video_mb=_read_positive_int("SP_MAX_VIDEO_MB", 50),
        max_workers=_read_positive_int("SP_MAX_WORKERS", 4),
        task_timeout_sec=_read_positive_int("SP_TASK_TIMEOUT_SEC", 180),
        download_retries=_read_positive_int("SP_DOWNLOAD_RETRIES", 2),
    )


def build_runtime_config(
    base_config: Config,
    max_video_mb: int,
    max_workers: int,
    task_timeout_sec: int,
    download_retries: int,
) -> Config:
    return replace(
        base_config,
        max_video_mb=max(max_video_mb, 1),
        max_workers=max(max_workers, 1),
        task_timeout_sec=max(task_timeout_sec, 1),
        download_retries=max(download_retries, 0),
    )


def _validate_ffmpeg_runtime() -> list[str]:
    return _build_runtime_errors(
        ffmpeg_available=shutil.which("ffmpeg") is not None,
        ffprobe_available=shutil.which("ffprobe") is not None,
    )


def _build_runtime_errors(
    ffmpeg_available: bool,
    ffprobe_available: bool,
    endcard_error: str | None = None,
) -> list[str]:
    errors: list[str] = []
    if endcard_error:
        errors.append(endcard_error)
    if not ffmpeg_available:
        errors.append("未找到 ffmpeg 可执行文件")
    if not ffprobe_available:
        errors.append("未找到 ffprobe 可执行文件")
    return errors


def validate_splice_runtime(config: Config) -> list[str]:
    endcard_error = None if config.endcard_path.is_file() else f"落版视频不存在: {config.endcard_path}"
    return _build_runtime_errors(
        ffmpeg_available=shutil.which("ffmpeg") is not None,
        ffprobe_available=shutil.which("ffprobe") is not None,
        endcard_error=endcard_error,
    )


def validate_attachment_runtime() -> list[str]:
    return _validate_ffmpeg_runtime()


def validate_runtime(config: Config) -> list[str]:
    return validate_splice_runtime(config)
