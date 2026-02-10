from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime
from pathlib import Path

from .models import TaskResult


def build_result_csv(results: list[TaskResult]) -> bytes:
    ordered = sorted(results, key=lambda item: item.index)

    sio = io.StringIO(newline="")
    writer = csv.writer(sio)
    writer.writerow(["pid", "output_filename", "status", "error", "duration_sec"])

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


def build_download_artifact(results: list[TaskResult]) -> tuple[str, str, bytes]:
    ordered = sorted(results, key=lambda item: item.index)
    result_csv = build_result_csv(ordered)

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
