from __future__ import annotations

from io import BytesIO

import pandas as pd

from video_splicer.input_parser import (
    build_split_input_preview,
    parse_inputs_with_errors,
    parse_split_inputs_with_errors,
)


def test_text_input_has_priority_over_csv() -> None:
    text = "text_pid,https://example.com/text.mp4\n"
    csv_bytes = b"pid,video_url\ncsv_pid,https://example.com/csv.mp4\n"

    rows, failures = parse_inputs_with_errors(text=text, csv_bytes=csv_bytes)

    assert len(rows) == 1
    assert rows[0].pid_raw == "text_pid"
    assert failures == []


def test_invalid_rows_are_recorded_but_valid_rows_continue() -> None:
    text = "\n".join(
        [
            "ok_1,https://example.com/1.mp4",
            "bad_line_without_comma",
            ",https://example.com/2.mp4",
            "bad_url,ftp://example.com/3.mp4",
            "ok_2,https://example.com/4.mp4",
        ]
    )

    rows, failures = parse_inputs_with_errors(text=text, csv_bytes=None)

    assert [item.pid_raw for item in rows] == ["ok_1", "ok_2"]
    assert [item.index for item in rows] == [0, 4]

    assert len(failures) == 3
    assert [item.index for item in failures] == [1, 2, 3]


def test_csv_requires_pid_and_video_url_headers() -> None:
    csv_bytes = b"id,url\na,https://example.com/a.mp4\n"

    rows, failures = parse_inputs_with_errors(text="", csv_bytes=csv_bytes)

    assert rows == []
    assert len(failures) == 1
    assert "CSV 缺少必需表头" in failures[0].error


def test_split_inputs_have_priority_over_csv() -> None:
    pid_text = "p1\n"
    video_url_text = "https://example.com/1.mp4\n"
    csv_bytes = b"pid,video_url\ncsv_pid,https://example.com/csv.mp4\n"

    rows, failures = parse_split_inputs_with_errors(
        pid_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name="input.csv",
        upload_bytes=csv_bytes,
    )

    assert [item.pid_raw for item in rows] == ["p1"]
    assert failures == []


def test_split_inputs_ignore_blank_lines_before_pairing() -> None:
    pid_text = "\n".join(["ok_1", "", "ok_2"])
    video_url_text = "\n".join(["https://example.com/1.mp4", "https://example.com/2.mp4"])

    rows, failures = parse_split_inputs_with_errors(
        pid_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name=None,
        upload_bytes=None,
    )

    assert [item.pid_raw for item in rows] == ["ok_1", "ok_2"]
    assert [item.index for item in rows] == [0, 1]
    assert failures == []


def test_split_inputs_keep_duplicate_pid_rows() -> None:
    pid_text = "\n".join(["dup_pid", "dup_pid", "dup_pid"])
    video_url_text = "\n".join(
        [
            "https://example.com/1.mp4",
            "https://example.com/2.mp4",
            "https://example.com/3.mp4",
        ]
    )

    rows, failures = parse_split_inputs_with_errors(
        pid_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name=None,
        upload_bytes=None,
    )

    assert failures == []
    assert len(rows) == 3
    assert [item.pid_raw for item in rows] == ["dup_pid", "dup_pid", "dup_pid"]
    assert [item.index for item in rows] == [0, 1, 2]


def test_excel_parses_product_id_and_video_link_and_skips_empty_link() -> None:
    df = pd.DataFrame(
        [
            {"商品id": 1001, "视频链接": "https://example.com/a.mp4"},
            {"商品id": 1002, "视频链接": None},
            {"商品id": 1003, "视频链接": "   "},
            {"商品id": 1004, "视频链接": "https://example.com/d.mp4"},
        ]
    )
    buffer = BytesIO()
    df.to_excel(buffer, index=False)

    rows, failures = parse_split_inputs_with_errors(
        pid_text="",
        video_url_text="",
        upload_file_name="视频信息.xlsx",
        upload_bytes=buffer.getvalue(),
    )

    assert failures == []
    assert [item.pid_raw for item in rows] == ["1001", "1004"]
    assert [item.video_url for item in rows] == [
        "https://example.com/a.mp4",
        "https://example.com/d.mp4",
    ]


def test_excel_requires_product_id_and_video_link_columns() -> None:
    df = pd.DataFrame([{"id": 1, "url": "https://example.com/a.mp4"}])
    buffer = BytesIO()
    df.to_excel(buffer, index=False)

    rows, failures = parse_split_inputs_with_errors(
        pid_text="",
        video_url_text="",
        upload_file_name="bad.xlsx",
        upload_bytes=buffer.getvalue(),
    )

    assert rows == []
    assert len(failures) == 1
    assert failures[0].error == "Excel 缺少必需列: 商品id,视频链接"


def test_split_preview_blocks_when_non_empty_line_counts_are_mismatched() -> None:
    preview = build_split_input_preview(
        pid_text="p1\n\np2\n",
        video_url_text="https://example.com/1.mp4\n",
        upload_file_name=None,
        upload_bytes=None,
    )

    assert preview.identifier_count == 2
    assert preview.video_url_count == 1
    assert preview.rows == []
    assert preview.blocking_errors == ["输入框行数不一致：pid 共 2 条，视频链接共 1 条。请调整一致后再继续。"]


def test_split_preview_shows_fallback_rows_when_csv_headers_are_missing() -> None:
    csv_bytes = b"id,url\na,https://example.com/a.mp4\nb,https://example.com/b.mp4\n"

    preview = build_split_input_preview(
        pid_text="",
        video_url_text="",
        upload_file_name="bad.csv",
        upload_bytes=csv_bytes,
    )

    assert [item.pid_raw for item in preview.rows] == ["a", "b"]
    assert [item.video_url for item in preview.rows] == [
        "https://example.com/a.mp4",
        "https://example.com/b.mp4",
    ]
    assert preview.blocking_errors == ["CSV 缺少必需表头: pid,video_url"]
    assert preview.notices == ["当前仅预览 CSV 前两列原始数据，修正表头后才能开始处理。"]


def test_split_preview_keeps_invalid_excel_rows_for_preview_and_blocking() -> None:
    df = pd.DataFrame(
        [
            {"商品id": "item_1", "视频链接": "https://example.com/a.mp4"},
            {"商品id": "item_2", "视频链接": None},
        ]
    )
    buffer = BytesIO()
    df.to_excel(buffer, index=False)

    preview = build_split_input_preview(
        pid_text="",
        video_url_text="",
        upload_file_name="items.xlsx",
        upload_bytes=buffer.getvalue(),
    )

    assert [item.pid_raw for item in preview.rows] == ["item_1", "item_2"]
    assert preview.identifier_count == 2
    assert preview.video_url_count == 1
    assert preview.blocking_errors == ["第 2 条：video_url 不能为空"]
