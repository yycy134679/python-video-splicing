from __future__ import annotations

from pathlib import Path

from video_splicer.config import build_runtime_config, validate_attachment_runtime, validate_splice_runtime
from video_splicer.models import Config


def test_attachment_runtime_does_not_require_endcard_but_splice_runtime_does(tmp_path: Path) -> None:
    missing_endcard = tmp_path / "missing_endcard.mp4"
    config = Config(endcard_path=missing_endcard)

    attachment_errors = validate_attachment_runtime()
    splice_errors = validate_splice_runtime(config)

    assert all("落版视频不存在" not in error for error in attachment_errors)
    assert any("落版视频不存在" in error for error in splice_errors)


def test_build_runtime_config_uses_web_overrides() -> None:
    base_config = Config(endcard_path=Path("/tmp/endcard.mp4"))

    runtime_config = build_runtime_config(
        base_config=base_config,
        max_video_mb=120,
        max_workers=6,
        task_timeout_sec=300,
        download_retries=4,
    )

    assert runtime_config.endcard_path == base_config.endcard_path
    assert runtime_config.max_video_mb == 120
    assert runtime_config.max_workers == 6
    assert runtime_config.task_timeout_sec == 300
    assert runtime_config.download_retries == 4
