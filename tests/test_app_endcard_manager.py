from __future__ import annotations

import os
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

import video_splicer.endcard_store as endcard_store_module


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = PROJECT_ROOT / "app.py"
SOURCE_ENDCARD_PATH = PROJECT_ROOT / "assets" / "video" / "endcard.mp4"


def _build_app_test(monkeypatch, tmp_path: Path) -> AppTest:
    default_endcard = tmp_path / "default-endcard.mp4"
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    shutil.copyfile(SOURCE_ENDCARD_PATH, default_endcard)
    timestamp = 1774019123
    os.utime(default_endcard, (timestamp, timestamp))

    monkeypatch.setenv("SP_ENDCARD_PATH", str(default_endcard))
    monkeypatch.setattr(endcard_store_module, "DEFAULT_MANAGED_ENDCARD_DIR", managed_dir)
    return AppTest.from_file(str(APP_PATH))


def _button_labels(app_test: AppTest) -> list[str]:
    return [button.label for button in app_test.button]


def _uploader_labels(app_test: AppTest) -> list[str]:
    return [item.proto.label for item in app_test.get("file_uploader")]


def _link_button_labels(app_test: AppTest) -> list[str]:
    return [item.proto.label for item in app_test.get("link_button")]


def _markdown_values(app_test: AppTest) -> list[str]:
    return [item.value for item in app_test.markdown]


def test_splice_page_shows_compact_endcard_summary_by_default(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)

    assert [item.value for item in app_test.subheader] == ["视频拼接"]
    assert "预览落版" in _link_button_labels(app_test)
    assert "更换落版" in _button_labels(app_test)
    assert "上传并立即生效" not in _button_labels(app_test)
    assert "上传新的落版视频" not in _uploader_labels(app_test)
    assert len(app_test.get("video")) == 0
    preview_link = next(item for item in app_test.get("link_button") if item.proto.label == "预览落版")
    assert preview_link.proto.url == "?endcard_preview=1"
    assert any("**当前落版：** 默认" in value for value in _markdown_values(app_test))
    assert any("**更新：** 2026-03-20" in value for value in _markdown_values(app_test))
    assert all("15:05:23" not in value for value in _markdown_values(app_test))


def test_preview_page_renders_video_in_separate_view(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)
    app_test.query_params["endcard_preview"] = "1"

    app_test.run(timeout=10)

    assert len(app_test.get("video")) == 1
    assert "上传新的落版视频" not in _uploader_labels(app_test)
    assert "上传并立即生效" not in _button_labels(app_test)
    assert "更换落版" not in _button_labels(app_test)
    assert any(item.value == "落版预览" for item in app_test.title)


def test_replace_button_expands_uploader_only(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)
    app_test = next(button for button in app_test.button if button.label == "更换落版").click().run(timeout=10)

    assert len(app_test.get("video")) == 0
    assert "上传新的落版视频" in _uploader_labels(app_test)
    assert "上传并立即生效" in _button_labels(app_test)
