from __future__ import annotations

import zipfile
from pathlib import Path

from video_splicer.artifact import build_download_artifact, build_result_csv
from video_splicer.models import TaskResult


def test_attachment_result_csv_uses_item_id_header() -> None:
    payload = build_result_csv(
        [
            TaskResult(
                index=0,
                pid="item_1",
                output_filename="item_1.mp4",
                status="SUCCESS",
                error="",
                duration_sec=1.2,
                output_path=None,
            )
        ],
        identifier_label="item_id",
    )

    lines = payload.decode("utf-8-sig").splitlines()

    assert lines[0] == "item_id,output_filename,status,error,duration_sec"
    assert lines[1].startswith("item_1,item_1.mp4,SUCCESS")


def test_attachment_download_artifact_writes_item_id_mp4_into_zip(tmp_path: Path) -> None:
    output_path = tmp_path / "item_1.mp4"
    output_path.write_bytes(b"video-bytes")

    mime, name, payload = build_download_artifact(
        [
            TaskResult(
                index=0,
                pid="item_1",
                output_filename="item_1.mp4",
                status="SUCCESS",
                error="",
                duration_sec=1.0,
                output_path=output_path,
            ),
            TaskResult(
                index=1,
                pid="item_2",
                output_filename="item_2.mp4",
                status="FAILED",
                error="download error",
                duration_sec=0.2,
                output_path=None,
            ),
        ],
        identifier_label="item_id",
    )

    assert mime == "application/zip"

    archive_path = tmp_path / name
    archive_path.write_bytes(payload)

    with zipfile.ZipFile(archive_path) as archive:
        assert sorted(archive.namelist()) == ["item_1.mp4", "result.csv"]
        assert archive.read("item_1.mp4") == b"video-bytes"
        result_csv = archive.read("result.csv").decode("utf-8-sig")
        assert result_csv.splitlines()[0] == "item_id,output_filename,status,error,duration_sec"
