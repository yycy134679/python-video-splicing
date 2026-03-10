from __future__ import annotations

from datetime import datetime
from pathlib import Path

from video_splicer.artifact import save_results_directory
from video_splicer.models import TaskResult


def test_save_results_directory_writes_success_files_and_result_csv(tmp_path: Path) -> None:
    output_a = tmp_path / "item_1.mp4"
    output_b = tmp_path / "item_2.mp4"
    output_a.write_bytes(b"video-a")
    output_b.write_bytes(b"video-b")

    result_dir = save_results_directory(
        [
            TaskResult(
                index=0,
                pid="item_1",
                output_filename="item_1.mp4",
                status="SUCCESS",
                error="",
                duration_sec=1.0,
                output_path=output_a,
            ),
            TaskResult(
                index=1,
                pid="item_2",
                output_filename="item_2.mp4",
                status="SUCCESS",
                error="",
                duration_sec=1.2,
                output_path=output_b,
            ),
        ],
        results_root_dir=tmp_path / "saved-results",
        result_dir_prefix="attachment",
        identifier_label="item_id",
        created_at=datetime(2026, 3, 10, 11, 17, 0),
    )

    assert result_dir == tmp_path / "saved-results" / "attachment-20260310-111700"
    assert sorted(path.name for path in result_dir.iterdir()) == ["item_1.mp4", "item_2.mp4", "result.csv"]
    assert (result_dir / "item_1.mp4").read_bytes() == b"video-a"
    assert (result_dir / "item_2.mp4").read_bytes() == b"video-b"
    assert (result_dir / "result.csv").read_text(encoding="utf-8-sig").splitlines()[0] == (
        "item_id,output_filename,status,error,duration_sec"
    )


def test_save_results_directory_skips_failed_outputs_but_keeps_csv(tmp_path: Path) -> None:
    output_path = tmp_path / "item_1.mp4"
    output_path.write_bytes(b"video-a")

    result_dir = save_results_directory(
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
        results_root_dir=tmp_path / "saved-results",
        result_dir_prefix="attachment",
        identifier_label="item_id",
        created_at=datetime(2026, 3, 10, 11, 17, 0),
    )

    assert sorted(path.name for path in result_dir.iterdir()) == ["item_1.mp4", "result.csv"]
    assert "download error" in (result_dir / "result.csv").read_text(encoding="utf-8-sig")


def test_save_results_directory_still_creates_result_csv_when_all_tasks_fail(tmp_path: Path) -> None:
    result_dir = save_results_directory(
        [
            TaskResult(
                index=0,
                pid="item_1",
                output_filename="item_1.mp4",
                status="FAILED",
                error="download error",
                duration_sec=0.2,
                output_path=None,
            )
        ],
        results_root_dir=tmp_path / "saved-results",
        result_dir_prefix="attachment",
        identifier_label="item_id",
        created_at=datetime(2026, 3, 10, 11, 17, 0),
    )

    assert sorted(path.name for path in result_dir.iterdir()) == ["result.csv"]
    assert "download error" in (result_dir / "result.csv").read_text(encoding="utf-8-sig")


def test_save_results_directory_appends_numeric_suffix_when_timestamp_collides(tmp_path: Path) -> None:
    output_path = tmp_path / "1.mp4"
    output_path.write_bytes(b"video-a")
    results_root_dir = tmp_path / "saved-results"
    first_dir = results_root_dir / "splice-20260310-111700"
    first_dir.mkdir(parents=True)

    result_dir = save_results_directory(
        [
            TaskResult(
                index=0,
                pid="demo001",
                output_filename="1.mp4",
                status="SUCCESS",
                error="",
                duration_sec=1.0,
                output_path=output_path,
            )
        ],
        results_root_dir=results_root_dir,
        result_dir_prefix="splice",
        created_at=datetime(2026, 3, 10, 11, 17, 0),
    )

    assert result_dir == results_root_dir / "splice-20260310-111700-2"
    assert sorted(path.name for path in result_dir.iterdir()) == ["1.mp4", "result.csv"]
