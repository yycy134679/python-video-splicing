from __future__ import annotations

import ast
import os
import shutil
from pathlib import Path

from streamlit.testing.v1 import AppTest

from video_splicer.endcard_ui import (
    ENDCARD_UPLOAD_SUCCESS_MESSAGE,
    build_endcard_upload_trigger_html,
    build_endcard_upload_widget_key,
    save_endcard_upload,
)
import video_splicer.endcard_store as endcard_store_module
from video_splicer.endcard_store import EndcardUploadError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = PROJECT_ROOT / "app.py"
SOURCE_ENDCARD_PATH = PROJECT_ROOT / "assets" / "video" / "endcard.mp4"


def _build_app_test(monkeypatch, tmp_path: Path) -> AppTest:
    default_endcard = tmp_path / "default-endcard.mp4"
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True, exist_ok=True)
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


def _caption_values(app_test: AppTest) -> list[str]:
    return [item.value for item in app_test.caption]


def test_splice_page_shows_compact_endcard_summary_by_default(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)

    assert len(app_test.get("title")) == 0
    assert [item.value for item in app_test.subheader] == ["视频拼接"]
    assert "预览落版" in _link_button_labels(app_test)
    assert "上传并立即生效" not in _button_labels(app_test)
    assert "上传新的落版视频" in _uploader_labels(app_test)
    assert len(app_test.get("video")) == 0
    preview_link = next(item for item in app_test.get("link_button") if item.proto.label == "预览落版")
    assert "/media/" in preview_link.proto.url
    assert preview_link.proto.url.endswith(".mp4")
    assert any("**当前落版：** 默认" in value for value in _markdown_values(app_test))
    assert any("**更新：** 2026-03-20" in value for value in _markdown_values(app_test))
    assert all("15:05:23" not in value for value in _markdown_values(app_test))


def test_preview_link_switches_to_mov_media_url_after_reupload(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)
    default_link = next(item for item in app_test.get("link_button") if item.proto.label == "预览落版")

    managed_dir = endcard_store_module.DEFAULT_MANAGED_ENDCARD_DIR
    mov_bytes = (tmp_path / "managed.mov")
    shutil.copyfile(SOURCE_ENDCARD_PATH, mov_bytes)
    endcard_store_module.replace_endcard_upload(
        upload_name="fresh.mov",
        upload_bytes=mov_bytes.read_bytes(),
        managed_dir=managed_dir,
        probe_video_fn=lambda _: object(),
    )

    app_test = _build_app_test(monkeypatch, tmp_path)
    app_test.run(timeout=10)
    managed_link = next(item for item in app_test.get("link_button") if item.proto.label == "预览落版")

    assert "/media/" in managed_link.proto.url
    assert managed_link.proto.url.endswith(".mov")
    assert managed_link.proto.url != default_link.proto.url


def test_hidden_endcard_uploader_is_mounted_without_extra_confirm_step(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)
    endcard_uploaders = [item for item in app_test.get("file_uploader") if item.proto.label == "上传新的落版视频"]

    assert len(app_test.get("video")) == 0
    assert len(endcard_uploaders) == 1
    assert build_endcard_upload_widget_key(0) in endcard_uploaders[0].proto.id
    assert "上传并立即生效" not in _button_labels(app_test)


def test_processing_pages_do_not_show_data_upload_entry_or_version_caption(monkeypatch, tmp_path: Path) -> None:
    app_test = _build_app_test(monkeypatch, tmp_path)

    app_test.run(timeout=10)

    assert _uploader_labels(app_test) == ["上传新的落版视频"]
    assert all("App Version" not in value for value in _caption_values(app_test))

    app_test.radio[0].set_value("视频链接转附件")
    app_test.run(timeout=10)

    assert _uploader_labels(app_test) == []
    assert all("App Version" not in value for value in _caption_values(app_test))


def test_page_config_uses_title_without_version_suffix() -> None:
    module = ast.parse(APP_PATH.read_text(encoding="utf-8"))

    for node in ast.walk(module):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if not isinstance(node.func.value, ast.Name) or node.func.value.id != "st":
            continue
        if node.func.attr != "set_page_config":
            continue

        for keyword in node.keywords:
            if keyword.arg == "page_title":
                assert isinstance(keyword.value, ast.Constant)
                assert keyword.value.value == "视频拼接工具"
                return

    raise AssertionError("未找到 st.set_page_config 的 page_title 配置")


def test_build_endcard_upload_trigger_html_contains_picker_script() -> None:
    html = build_endcard_upload_trigger_html()

    assert "更换落版" in html
    assert "MutationObserver" in html
    assert "uploaderInput.click()" in html
    assert "input[type=\"file\"][accept*=\".mov\"]" in html


def test_save_endcard_upload_returns_success_message() -> None:
    recorded: dict[str, object] = {}

    def fake_replace(*, upload_name: str, upload_bytes: bytes) -> None:
        recorded["upload_name"] = upload_name
        recorded["upload_bytes"] = upload_bytes

    feedback, error = save_endcard_upload("fresh.mov", b"mov-bytes", replace_upload_fn=fake_replace)

    assert feedback == ENDCARD_UPLOAD_SUCCESS_MESSAGE
    assert error == ""
    assert recorded == {"upload_name": "fresh.mov", "upload_bytes": b"mov-bytes"}


def test_save_endcard_upload_returns_domain_error() -> None:
    def fake_replace(*, upload_name: str, upload_bytes: bytes) -> None:
        raise EndcardUploadError("文件格式无效")

    feedback, error = save_endcard_upload("broken.mov", b"broken", replace_upload_fn=fake_replace)

    assert feedback == ""
    assert error == "文件格式无效"
