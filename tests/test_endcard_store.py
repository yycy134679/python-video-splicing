from __future__ import annotations

from pathlib import Path

import pytest

from video_splicer.endcard_store import EndcardUploadError, replace_endcard_upload, resolve_active_endcard


def test_resolve_active_endcard_prefers_managed_file(tmp_path: Path) -> None:
    default_endcard = tmp_path / "assets" / "video" / "endcard.mp4"
    managed_dir = tmp_path / "managed-endcard"
    managed_file = managed_dir / "current-endcard.mov"
    default_endcard.parent.mkdir(parents=True)
    managed_dir.mkdir(parents=True)
    default_endcard.write_bytes(b"default")
    managed_file.write_bytes(b"managed")

    asset = resolve_active_endcard(default_endcard=default_endcard, managed_dir=managed_dir)

    assert asset.path == managed_file
    assert asset.source == "MANAGED"


def test_resolve_active_endcard_falls_back_to_default_file(tmp_path: Path) -> None:
    default_endcard = tmp_path / "assets" / "video" / "endcard.mp4"
    default_endcard.parent.mkdir(parents=True)
    default_endcard.write_bytes(b"default")

    asset = resolve_active_endcard(default_endcard=default_endcard, managed_dir=tmp_path / "managed-endcard")

    assert asset.path == default_endcard
    assert asset.source == "DEFAULT"


def test_replace_endcard_upload_overwrites_previous_file(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    old_file = managed_dir / "current-endcard.mp4"
    old_file.write_bytes(b"old")

    def fake_probe(video_path: Path) -> object:
        assert video_path.suffix == ".mov"
        return object()

    asset = replace_endcard_upload(
        upload_name="fresh.mov",
        upload_bytes=b"new-content",
        managed_dir=managed_dir,
        probe_video_fn=fake_probe,
    )

    assert asset.path == managed_dir / "current-endcard.mov"
    assert asset.path.read_bytes() == b"new-content"
    assert not old_file.exists()


def test_replace_endcard_upload_rejects_invalid_extension_without_touching_current_file(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    current_file = managed_dir / "current-endcard.mp4"
    current_file.write_bytes(b"current")

    with pytest.raises(EndcardUploadError, match="仅支持上传 mp4 或 mov"):
        replace_endcard_upload(
            upload_name="fresh.avi",
            upload_bytes=b"bad",
            managed_dir=managed_dir,
            probe_video_fn=lambda _: object(),
        )

    assert current_file.read_bytes() == b"current"


def test_replace_endcard_upload_keeps_previous_file_when_probe_fails(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    current_file = managed_dir / "current-endcard.mp4"
    current_file.write_bytes(b"current")

    def broken_probe(_: Path) -> object:
        raise RuntimeError("boom")

    with pytest.raises(EndcardUploadError, match="无法识别该落版视频"):
        replace_endcard_upload(
            upload_name="fresh.mp4",
            upload_bytes=b"new",
            managed_dir=managed_dir,
            probe_video_fn=broken_probe,
        )

    assert current_file.read_bytes() == b"current"
