from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoProbe:
    width: int
    height: int
    duration_sec: float
    has_audio: bool


def ensure_ffmpeg_available() -> None:
    if shutil.which("ffmpeg") is None:
        raise FFmpegError("未找到 ffmpeg 可执行文件")
    if shutil.which("ffprobe") is None:
        raise FFmpegError("未找到 ffprobe 可执行文件")


def probe_video(video_path: Path) -> VideoProbe:
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        str(video_path),
    ]

    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else ""
        raise FFmpegError(f"ffprobe 失败: {stderr or exc}") from exc

    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise FFmpegError("ffprobe 输出无法解析") from exc

    streams = payload.get("streams", [])
    format_data = payload.get("format", {})

    video_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
    if video_stream is None:
        raise FFmpegError("输入文件缺少视频轨")

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise FFmpegError("无法获取视频分辨率")

    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    duration_str = format_data.get("duration") or video_stream.get("duration")
    try:
        duration = float(duration_str) if duration_str is not None else 0.0
    except (TypeError, ValueError):
        duration = 0.0

    return VideoProbe(width=width, height=height, duration_sec=duration, has_audio=has_audio)


def concat_with_endcard(
    source_video: Path,
    endcard_video: Path,
    output_video: Path,
    timeout_sec: float,
) -> None:
    if timeout_sec <= 0:
        raise TimeoutError("任务超时")

    source_probe = probe_video(source_video)
    endcard_probe = probe_video(endcard_video)

    input_args = ["-i", str(source_video), "-i", str(endcard_video)]
    filter_parts = [
        "[0:v]setsar=1[v0]",
        (
            "[1:v]"
            f"scale={source_probe.width}:{source_probe.height}:force_original_aspect_ratio=decrease,"
            f"pad={source_probe.width}:{source_probe.height}:(ow-iw)/2:(oh-ih)/2:black,"
            "setsar=1[v1]"
        ),
    ]

    next_input_index = 2

    if source_probe.has_audio:
        filter_parts.append(
            "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a0]"
        )
    else:
        if source_probe.duration_sec <= 0:
            raise FFmpegError("源视频无音轨且无法获取时长")
        input_args.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{source_probe.duration_sec:.3f}",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        filter_parts.append(
            f"[{next_input_index}:a]atrim=0:{source_probe.duration_sec:.3f},asetpts=N/SR/TB[a0]"
        )
        next_input_index += 1

    if endcard_probe.has_audio:
        filter_parts.append(
            "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a1]"
        )
    else:
        if endcard_probe.duration_sec <= 0:
            raise FFmpegError("落版视频无音轨且无法获取时长")
        input_args.extend(
            [
                "-f",
                "lavfi",
                "-t",
                f"{endcard_probe.duration_sec:.3f}",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=48000",
            ]
        )
        filter_parts.append(
            f"[{next_input_index}:a]atrim=0:{endcard_probe.duration_sec:.3f},asetpts=N/SR/TB[a1]"
        )

    filter_parts.append("[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]")
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        *input_args,
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(output_video),
    ]

    try:
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError("ffmpeg 处理超时") from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        message = stderr.splitlines()[-1] if stderr else "ffmpeg 执行失败"
        raise FFmpegError(message) from exc
