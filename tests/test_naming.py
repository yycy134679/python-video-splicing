from video_splicer.input_parser import assign_output_filenames
from video_splicer.models import InputRow


def test_assign_output_filenames_use_input_order_sequence() -> None:
    rows = [
        InputRow(index=0, pid_raw="a", pid_sanitized="a", video_url="https://example.com/1.mp4"),
        InputRow(index=1, pid_raw="a", pid_sanitized="a", video_url="https://example.com/2.mp4"),
        InputRow(index=2, pid_raw="a", pid_sanitized="a", video_url="https://example.com/3.mp4"),
    ]

    names = assign_output_filenames(rows)

    assert names == {0: "1.mp4", 1: "2.mp4", 2: "3.mp4"}


def test_assign_output_filenames_sorted_by_row_index() -> None:
    rows = [
        InputRow(index=10, pid_raw="a/b", pid_sanitized="a_b", video_url="https://example.com/1.mp4"),
        InputRow(index=11, pid_raw="a:b", pid_sanitized="a_b", video_url="https://example.com/2.mp4"),
        InputRow(index=5, pid_raw="z", pid_sanitized="z", video_url="https://example.com/3.mp4"),
    ]

    names = assign_output_filenames(rows)

    assert names[5] == "1.mp4"
    assert names[10] == "2.mp4"
    assert names[11] == "3.mp4"
