from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


Status = Literal["SUCCESS", "FAILED"]


@dataclass(frozen=True)
class Config:
    endcard_path: Path
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


@dataclass
class TaskResult:
    index: int
    pid: str
    output_filename: str
    status: Status
    error: str
    duration_sec: float
    output_path: Path | None
