from video_splicer.input_parser import parse_inputs_with_errors


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
