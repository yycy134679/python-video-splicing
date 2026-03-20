from __future__ import annotations

from pathlib import Path

from video_splicer.endcard_store import resolve_active_endcard


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
