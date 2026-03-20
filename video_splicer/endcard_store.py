from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Callable
from typing import Literal

from .ffmpeg_pipeline import probe_video


EndcardSource = Literal["DEFAULT", "MANAGED"]
DEFAULT_MANAGED_ENDCARD_DIR = Path.home() / ".video-splicer" / "endcard"
_MANAGED_ENDCARD_FILENAMES = ("current-endcard.mp4", "current-endcard.mov")
_ALLOWED_ENDCARD_SUFFIXES = {".mp4", ".mov"}


@dataclass(frozen=True)
class EndcardAsset:
    path: Path
    source: EndcardSource
    file_name: str
    suffix: str
    size_bytes: int
    mime_type: str


class EndcardUploadError(RuntimeError):
    pass


def find_managed_endcard(managed_dir: Path | None = None) -> Path | None:
    target_dir = managed_dir or DEFAULT_MANAGED_ENDCARD_DIR
    for file_name in _MANAGED_ENDCARD_FILENAMES:
        candidate = target_dir / file_name
        if candidate.is_file():
            return candidate
    return None


def build_endcard_asset(path: Path, source: EndcardSource) -> EndcardAsset:
    suffix = path.suffix.lower()
    mime_type = "video/quicktime" if suffix == ".mov" else "video/mp4"
    size_bytes = path.stat().st_size if path.is_file() else 0
    return EndcardAsset(
        path=path,
        source=source,
        file_name=path.name,
        suffix=suffix,
        size_bytes=size_bytes,
        mime_type=mime_type,
    )


def resolve_active_endcard(default_endcard: Path, managed_dir: Path | None = None) -> EndcardAsset:
    managed_file = find_managed_endcard(managed_dir)
    active_path = managed_file if managed_file is not None else default_endcard
    source: EndcardSource = "MANAGED" if managed_file is not None else "DEFAULT"
    return build_endcard_asset(active_path, source=source)


def validate_endcard_extension(upload_name: str) -> str:
    suffix = Path(upload_name).suffix.lower()
    if suffix not in _ALLOWED_ENDCARD_SUFFIXES:
        raise EndcardUploadError("仅支持上传 mp4 或 mov 格式的落版视频")
    return suffix


def _write_temp_upload(managed_dir: Path, suffix: str, upload_bytes: bytes) -> Path:
    with NamedTemporaryFile(dir=managed_dir, prefix="upload-", suffix=suffix, delete=False) as temp_file:
        temp_file.write(upload_bytes)
        return Path(temp_file.name)


def _remove_existing_managed_files(managed_dir: Path) -> None:
    for file_name in _MANAGED_ENDCARD_FILENAMES:
        (managed_dir / file_name).unlink(missing_ok=True)


def replace_endcard_upload(
    upload_name: str,
    upload_bytes: bytes,
    managed_dir: Path | None = None,
    probe_video_fn: Callable[[Path], object] = probe_video,
) -> EndcardAsset:
    if not upload_bytes:
        raise EndcardUploadError("上传失败：落版视频文件为空")

    suffix = validate_endcard_extension(upload_name)
    target_dir = managed_dir or DEFAULT_MANAGED_ENDCARD_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    temp_path = _write_temp_upload(managed_dir=target_dir, suffix=suffix, upload_bytes=upload_bytes)

    try:
        probe_video_fn(temp_path)
        target_path = target_dir / f"current-endcard{suffix}"
        _remove_existing_managed_files(target_dir)
        temp_path.replace(target_path)
        return build_endcard_asset(target_path, source="MANAGED")
    except EndcardUploadError:
        temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:  # noqa: BLE001
        temp_path.unlink(missing_ok=True)
        raise EndcardUploadError("无法识别该落版视频，请确认文件未损坏") from exc
