from __future__ import annotations

import time
from pathlib import Path

import requests


class DownloadError(RuntimeError):
    pass


def download_video(
    video_url: str,
    destination: Path,
    max_bytes: int,
    retries: int,
    total_timeout_sec: float,
) -> None:
    attempts = max(retries, 0) + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            _download_once(
                video_url=video_url,
                destination=destination,
                max_bytes=max_bytes,
                total_timeout_sec=total_timeout_sec,
            )
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if destination.exists():
                destination.unlink(missing_ok=True)
            if attempt == attempts:
                break
            time.sleep(min(attempt, 2))

    raise DownloadError(str(last_error) if last_error else "下载失败")


def _download_once(
    video_url: str,
    destination: Path,
    max_bytes: int,
    total_timeout_sec: float,
) -> None:
    started_at = time.monotonic()

    with requests.get(video_url, stream=True, timeout=(10, 15), allow_redirects=True) as response:
        response.raise_for_status()

        content_length = response.headers.get("Content-Length")
        if content_length:
            try:
                if int(content_length) > max_bytes:
                    raise DownloadError("源视频超过大小限制")
            except ValueError:
                pass

        bytes_written = 0
        with destination.open("wb") as out_file:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue

                bytes_written += len(chunk)
                if bytes_written > max_bytes:
                    raise DownloadError("源视频超过大小限制")

                elapsed = time.monotonic() - started_at
                if elapsed > total_timeout_sec:
                    raise TimeoutError("下载超时")

                out_file.write(chunk)
