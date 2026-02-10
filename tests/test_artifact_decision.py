from __future__ import annotations

import re
import zipfile
from pathlib import Path

from video_splicer.artifact import build_download_artifact
from video_splicer.models import TaskResult


def test_single_success_returns_mp4(tmp_path: Path) -> None:
    output_path = tmp_path / "a.mp4"
    output_path.write_bytes(b"video-bytes")

    results = [
        TaskResult(
            index=0,
            pid="a",
            output_filename="a.mp4",
            status="SUCCESS",
            error="",
            duration_sec=1.23,
            output_path=output_path,
        )
    ]

    mime, name, data = build_download_artifact(results)

    assert mime == "video/mp4"
    assert name == "a.mp4"
    assert data == b"video-bytes"


def test_single_failure_returns_result_csv() -> None:
    results = [
        TaskResult(
            index=0,
            pid="a",
            output_filename="",
            status="FAILED",
            error="boom",
            duration_sec=0.1,
            output_path=None,
        )
    ]

    mime, name, data = build_download_artifact(results)

    assert mime == "text/csv"
    assert name == "result.csv"
    assert b"boom" in data


def test_multiple_rows_return_zip_with_mp4_and_result_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "a.mp4"
    output_path.write_bytes(b"video")

    results = [
        TaskResult(
            index=0,
            pid="a",
            output_filename="a.mp4",
            status="SUCCESS",
            error="",
            duration_sec=1.0,
            output_path=output_path,
        ),
        TaskResult(
            index=1,
            pid="b",
            output_filename="b.mp4",
            status="FAILED",
            error="download error",
            duration_sec=0.2,
            output_path=None,
        ),
    ]

    mime, name, payload = build_download_artifact(results)

    assert mime == "application/zip"
    assert re.fullmatch(r"results-\d{2}-\d{2}-\d{2}-\d{2}\.zip", name)

    archive_path = tmp_path / name
    archive_path.write_bytes(payload)

    with zipfile.ZipFile(archive_path) as archive:
        names = sorted(archive.namelist())
        assert names == ["a.mp4", "result.csv"]
        assert archive.read("a.mp4") == b"video"
        assert b"download error" in archive.read("result.csv")
