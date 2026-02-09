from video_splicer.ffmpeg_pipeline import (
    DEFAULT_AUDIO_BITRATE,
    MIN_VIDEO_BITRATE,
    VideoProbe,
    _select_audio_bitrate,
    _select_video_bitrate,
)


def _probe(video_bitrate: int, audio_bitrate: int, format_bitrate: int) -> VideoProbe:
    return VideoProbe(
        width=1080,
        height=1920,
        duration_sec=12.0,
        has_audio=audio_bitrate > 0,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        format_bitrate=format_bitrate,
    )


def test_video_bitrate_prefers_source_video_stream() -> None:
    probe = _probe(video_bitrate=4_500_000, audio_bitrate=128_000, format_bitrate=5_000_000)
    assert _select_video_bitrate(probe) == 4_500_000


def test_video_bitrate_fallbacks_to_format_minus_audio() -> None:
    probe = _probe(video_bitrate=0, audio_bitrate=128_000, format_bitrate=2_000_000)
    assert _select_video_bitrate(probe) == 1_872_000


def test_video_bitrate_has_min_floor() -> None:
    probe = _probe(video_bitrate=50_000, audio_bitrate=64_000, format_bitrate=120_000)
    assert _select_video_bitrate(probe) == MIN_VIDEO_BITRATE


def test_audio_bitrate_default_when_missing() -> None:
    probe = _probe(video_bitrate=2_000_000, audio_bitrate=0, format_bitrate=2_100_000)
    assert _select_audio_bitrate(probe) == DEFAULT_AUDIO_BITRATE
