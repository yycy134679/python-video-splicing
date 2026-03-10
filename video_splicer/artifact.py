from __future__ import annotations

import csv
import io
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from .models import TaskResult


def _sort_results(results: list[TaskResult]) -> list[TaskResult]:
    return sorted(results, key=lambda item: item.index)


def build_result_csv(results: list[TaskResult], identifier_label: str = "pid") -> bytes:
    ordered = _sort_results(results)

    sio = io.StringIO(newline="")
    writer = csv.writer(sio)
    writer.writerow([identifier_label, "output_filename", "status", "error", "duration_sec"])

    for result in ordered:
        writer.writerow(
            [
                result.pid,
                result.output_filename,
                result.status,
                result.error,
                f"{result.duration_sec:.3f}",
            ]
        )

    return sio.getvalue().encode("utf-8-sig")


def build_download_artifact(
    results: list[TaskResult],
    identifier_label: str = "pid",
) -> tuple[str, str, bytes]:
    ordered = _sort_results(results)
    result_csv = build_result_csv(ordered, identifier_label=identifier_label)

    if not ordered:
        return "text/csv", "result.csv", result_csv

    if len(ordered) == 1:
        single = ordered[0]
        if single.status == "SUCCESS" and single.output_path and single.output_path.exists():
            return "video/mp4", single.output_filename, single.output_path.read_bytes()
        return "text/csv", "result.csv", result_csv

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for result in ordered:
            if result.status != "SUCCESS":
                continue
            if result.output_path is None:
                continue
            if not result.output_path.exists():
                continue
            archive.writestr(result.output_filename, result.output_path.read_bytes())

        archive.writestr("result.csv", result_csv)

    timestamp = datetime.now().strftime("%m-%d-%H-%M")
    zip_name = f"results-{timestamp}.zip"
    return "application/zip", zip_name, zip_buffer.getvalue()


def save_results_directory(
    results: list[TaskResult],
    results_root_dir: Path,
    result_dir_prefix: str,
    identifier_label: str = "pid",
    created_at: datetime | None = None,
) -> Path:
    ordered = _sort_results(results)
    timestamp = (created_at or datetime.now()).strftime("%Y%m%d-%H%M%S")

    results_root_dir.mkdir(parents=True, exist_ok=True)
    result_dir = _create_result_dir(results_root_dir, f"{result_dir_prefix}-{timestamp}")
    result_dir.joinpath("result.csv").write_bytes(build_result_csv(ordered, identifier_label=identifier_label))

    for result in ordered:
        if result.status != "SUCCESS":
            continue
        if result.output_path is None or not result.output_path.exists():
            continue
        shutil.copy2(result.output_path, result_dir / result.output_filename)

    return result_dir


def _create_result_dir(results_root_dir: Path, dir_name: str) -> Path:
    candidate = results_root_dir / dir_name
    suffix = 2
    while candidate.exists():
        candidate = results_root_dir / f"{dir_name}-{suffix}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def collect_work_dirs(results: list[TaskResult]) -> list[Path]:
    work_dirs: set[Path] = set()
    for result in results:
        if result.output_path is None:
            continue
        try:
            work_dir = result.output_path.parent.parent
        except IndexError:
            continue
        if work_dir.name.startswith("video_splice_"):
            work_dirs.add(work_dir)
    return sorted(work_dirs)
