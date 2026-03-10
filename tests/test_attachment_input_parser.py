from __future__ import annotations

from io import BytesIO

import pandas as pd

from video_splicer.input_parser import build_attachment_input_preview, parse_attachment_inputs_with_errors


def test_attachment_text_input_has_priority_over_csv() -> None:
    csv_bytes = b"item_id,video_url\ncsv_item,https://example.com/csv.mp4\n"

    rows, failures = parse_attachment_inputs_with_errors(
        item_id_text="text_item\n",
        video_url_text="https://example.com/text.mp4\n",
        upload_file_name="input.csv",
        upload_bytes=csv_bytes,
    )

    assert failures == []
    assert [item.pid_raw for item in rows] == ["text_item"]


def test_attachment_csv_accepts_item_id_header() -> None:
    csv_bytes = b"item_id,video_url\nitem_1,https://example.com/a.mp4\n"

    rows, failures = parse_attachment_inputs_with_errors(
        item_id_text="",
        video_url_text="",
        upload_file_name="input.csv",
        upload_bytes=csv_bytes,
    )

    assert failures == []
    assert [item.pid_raw for item in rows] == ["item_1"]


def test_attachment_csv_accepts_legacy_pid_header() -> None:
    csv_bytes = b"pid,video_url\nlegacy_1,https://example.com/a.mp4\n"

    rows, failures = parse_attachment_inputs_with_errors(
        item_id_text="",
        video_url_text="",
        upload_file_name="legacy.csv",
        upload_bytes=csv_bytes,
    )

    assert failures == []
    assert [item.pid_raw for item in rows] == ["legacy_1"]


def test_attachment_split_inputs_use_item_id_error_message() -> None:
    rows, failures = parse_attachment_inputs_with_errors(
        item_id_text="\n",
        video_url_text="https://example.com/a.mp4\n",
        upload_file_name=None,
        upload_bytes=None,
    )

    assert rows == []
    assert len(failures) == 1
    assert failures[0].error == "item_id 不能为空"


def test_attachment_excel_reads_product_id_and_video_link() -> None:
    df = pd.DataFrame(
        [
            {"商品id": "item_1", "视频链接": "https://example.com/a.mp4"},
            {"商品id": "item_2", "视频链接": None},
            {"商品id": "item_3", "视频链接": "https://example.com/b.mp4"},
        ]
    )
    buffer = BytesIO()
    df.to_excel(buffer, index=False)

    rows, failures = parse_attachment_inputs_with_errors(
        item_id_text="",
        video_url_text="",
        upload_file_name="items.xlsx",
        upload_bytes=buffer.getvalue(),
    )

    assert failures == []
    assert [item.pid_raw for item in rows] == ["item_1", "item_3"]


def test_attachment_preview_accepts_legacy_pid_header() -> None:
    csv_bytes = b"pid,video_url\nlegacy_1,https://example.com/a.mp4\n"

    preview = build_attachment_input_preview(
        item_id_text="",
        video_url_text="",
        upload_file_name="legacy.csv",
        upload_bytes=csv_bytes,
    )

    assert preview.blocking_errors == []
    assert [item.pid_raw for item in preview.rows] == ["legacy_1"]


def test_attachment_preview_uses_item_id_label_for_mismatch_error() -> None:
    preview = build_attachment_input_preview(
        item_id_text="item_1\nitem_2\n",
        video_url_text="https://example.com/a.mp4\n",
        upload_file_name=None,
        upload_bytes=None,
    )

    assert preview.rows == []
    assert preview.blocking_errors == ["输入框行数不一致：item_id 共 2 条，视频链接共 1 条。请调整一致后再继续。"]
