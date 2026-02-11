from io import BytesIO

import pandas as pd

from video_splicer.input_parser import (
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


def test_split_inputs_pair_lines_and_keep_processing_on_bad_rows() -> None:
    pid_text = "\n".join(["ok_1", "bad_missing_url", "ok_2", ""])
    video_url_text = "\n".join(
        ["https://example.com/1.mp4", "", "https://example.com/2.mp4", "https://example.com/4.mp4"]
    )

    rows, failures = parse_split_inputs_with_errors(
        pid_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name=None,
        upload_bytes=None,
    )

    assert [item.pid_raw for item in rows] == ["ok_1", "ok_2"]
    assert [item.index for item in rows] == [0, 2]
    assert len(failures) == 2
    assert failures[0].index == 1
    assert failures[0].error == "video_url 不能为空"
    assert failures[1].index == 3
    assert failures[1].error == "pid 不能为空"


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
