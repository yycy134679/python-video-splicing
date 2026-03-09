from __future__ import annotations

import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable

from .downloader import DownloadError, download_video
from .ffmpeg_pipeline import FFmpegError, concat_with_endcard, normalize_video_to_mp4
from .input_parser import assign_attachment_output_filenames, assign_output_filenames
from .models import Config, InputRow, TaskResult


LogCallback = Callable[[str], None]
ProgressCallback = Callable[[int, int], None]
FilenameAssigner = Callable[[list[InputRow]], dict[int, str]]
SingleTaskProcessor = Callable[[InputRow, str, Config, Path, Path], TaskResult]


def process_batch(
    rows: list[InputRow],
    config: Config,
    log_cb: LogCallback | None = None,
    progress_cb: ProgressCallback | None = None,
) -> list[TaskResult]:
    return _process_rows(
        rows=rows,
        config=config,
        log_cb=log_cb,
        progress_cb=progress_cb,
        filename_assigner=assign_output_filenames,
        single_task_processor=_process_single_splice,
        identifier_label="pid",
    )


def process_attachment_batch(
    rows: list[InputRow],
    config: Config,
    log_cb: LogCallback | None = None,
    progress_cb: ProgressCallback | None = None,
) -> list[TaskResult]:
    return _process_rows(
        rows=rows,
        config=config,
        log_cb=log_cb,
        progress_cb=progress_cb,
        filename_assigner=assign_attachment_output_filenames,
        single_task_processor=_process_single_attachment,
        identifier_label="item_id",
    )


def _process_rows(
    rows: list[InputRow],
    config: Config,
    log_cb: LogCallback | None,
    progress_cb: ProgressCallback | None,
    filename_assigner: FilenameAssigner,
    single_task_processor: SingleTaskProcessor,
    identifier_label: str,
) -> list[TaskResult]:
    if not rows:
        return []

    filename_map = filename_assigner(rows)
    work_dir = Path(tempfile.mkdtemp(prefix="video_splice_"))
    download_dir = work_dir / "downloads"
    output_dir = work_dir / "outputs"
    download_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    _log(log_cb, f"批次开始，共 {len(rows)} 条，工作目录: {work_dir}")

    results_by_index: dict[int, TaskResult] = {}
    completed_count = 0

    with ThreadPoolExecutor(max_workers=config.max_workers) as executor:
        futures = {
            executor.submit(
                single_task_processor,
                row=row,
                output_filename=filename_map[row.index],
                config=config,
                download_dir=download_dir,
                output_dir=output_dir,
            ): row
            for row in rows
        }

        for future in as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                output_filename = filename_map[row.index]
                result = TaskResult(
                    index=row.index,
                    pid=row.pid_raw,
                    output_filename=output_filename,
                    status="FAILED",
                    error=f"内部错误: {exc}",
                    duration_sec=0.0,
                    output_path=output_dir / output_filename,
                )

            results_by_index[result.index] = result
            completed_count += 1

            if result.status == "SUCCESS":
                _log(
                    log_cb,
                    (
                        f"[{completed_count}/{len(rows)}] "
                        f"{identifier_label}={result.pid} 成功 -> {result.output_filename}"
                    ),
                )
            else:
                _log(
                    log_cb,
                    (
                        f"[{completed_count}/{len(rows)}] "
                        f"{identifier_label}={result.pid} 失败 -> {result.error}"
                    ),
                )

            if progress_cb:
                progress_cb(completed_count, len(rows))

    ordered_results = sorted(results_by_index.values(), key=lambda item: item.index)
    _log(log_cb, "批次处理完成")
    return ordered_results


def _process_single_splice(
    row: InputRow,
    output_filename: str,
    config: Config,
    download_dir: Path,
    output_dir: Path,
) -> TaskResult:
    started_at = time.monotonic()
    output_path = output_dir / output_filename
    download_path = download_dir / f"{row.index}.mp4"

    try:
        _assert_remaining(started_at, config.task_timeout_sec)
        download_video(
            video_url=row.video_url,
            destination=download_path,
            max_bytes=config.max_video_mb * 1024 * 1024,
            retries=config.download_retries,
            total_timeout_sec=_remaining_seconds(started_at, config.task_timeout_sec),
        )

        _assert_remaining(started_at, config.task_timeout_sec)
        concat_with_endcard(
            source_video=download_path,
            endcard_video=config.endcard_path,
            output_video=output_path,
            timeout_sec=_remaining_seconds(started_at, config.task_timeout_sec),
        )

        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="SUCCESS",
            error="",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except TimeoutError:
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=f"超时：超过 {config.task_timeout_sec} 秒",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except (DownloadError, FFmpegError) as exc:
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=str(exc),
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except Exception as exc:  # noqa: BLE001
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=f"未预期错误: {exc}",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    finally:
        if download_path.exists():
            download_path.unlink(missing_ok=True)


def _process_single_attachment(
    row: InputRow,
    output_filename: str,
    config: Config,
    download_dir: Path,
    output_dir: Path,
) -> TaskResult:
    started_at = time.monotonic()
    output_path = output_dir / output_filename
    download_path = download_dir / f"{row.index}.source"

    try:
        _assert_remaining(started_at, config.task_timeout_sec)
        download_video(
            video_url=row.video_url,
            destination=download_path,
            max_bytes=config.max_video_mb * 1024 * 1024,
            retries=config.download_retries,
            total_timeout_sec=_remaining_seconds(started_at, config.task_timeout_sec),
        )

        _assert_remaining(started_at, config.task_timeout_sec)
        normalize_video_to_mp4(
            source_video=download_path,
            output_video=output_path,
            timeout_sec=_remaining_seconds(started_at, config.task_timeout_sec),
        )

        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="SUCCESS",
            error="",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except TimeoutError:
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=f"超时：超过 {config.task_timeout_sec} 秒",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except (DownloadError, FFmpegError) as exc:
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=str(exc),
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    except Exception as exc:  # noqa: BLE001
        return TaskResult(
            index=row.index,
            pid=row.pid_raw,
            output_filename=output_filename,
            status="FAILED",
            error=f"未预期错误: {exc}",
            duration_sec=time.monotonic() - started_at,
            output_path=output_path,
        )
    finally:
        if download_path.exists():
            download_path.unlink(missing_ok=True)


def _remaining_seconds(started_at: float, total_timeout_sec: int) -> float:
    elapsed = time.monotonic() - started_at
    return max(0.0, total_timeout_sec - elapsed)


def _assert_remaining(started_at: float, total_timeout_sec: int) -> None:
    if _remaining_seconds(started_at, total_timeout_sec) <= 0:
        raise TimeoutError("任务超时")


def _log(log_cb: LogCallback | None, message: str) -> None:
    if log_cb:
        log_cb(message)
