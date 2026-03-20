from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


EndcardSource = Literal["DEFAULT", "MANAGED"]
DEFAULT_MANAGED_ENDCARD_DIR = Path.home() / ".video-splicer" / "endcard"
_MANAGED_ENDCARD_FILENAMES = ("current-endcard.mp4", "current-endcard.mov")


@dataclass(frozen=True)
class EndcardAsset:
    path: Path
    source: EndcardSource
    file_name: str
    suffix: str
    size_bytes: int
    mime_type: str


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
