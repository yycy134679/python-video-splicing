from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


Status = Literal["SUCCESS", "FAILED"]
PreviewSource = Literal["EMPTY", "TEXT", "UPLOAD"]


@dataclass(frozen=True)
class Config:
    endcard_path: Path
    results_root_dir: Path = field(default_factory=lambda: Path.home() / "Downloads" / "video-splicer-results")
    max_video_mb: int = 50
    max_workers: int = 4
    task_timeout_sec: int = 180
    download_retries: int = 2


@dataclass(frozen=True)
class InputRow:
    index: int
    pid_raw: str
    pid_sanitized: str
    video_url: str


@dataclass(frozen=True)
class ParseFailure:
    index: int
    pid_raw: str
    error: str


@dataclass(frozen=True)
class PreviewRow:
    index: int
    pid_raw: str
    video_url: str


@dataclass(frozen=True)
class InputPreview:
    source: PreviewSource
    identifier_count: int
    video_url_count: int
    rows: list[PreviewRow]
    blocking_errors: list[str]
    notices: list[str]


@dataclass
class TaskResult:
    index: int
    pid: str
    output_filename: str
    status: Status
    error: str
    duration_sec: float
    output_path: Path | None
