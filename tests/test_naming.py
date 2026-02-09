from video_splicer.input_parser import assign_output_filenames
from video_splicer.models import InputRow


def test_assign_output_filenames_for_duplicate_pid() -> None:
    rows = [
        InputRow(index=0, pid_raw="a", pid_sanitized="a", video_url="https://example.com/1.mp4"),
        InputRow(index=1, pid_raw="a", pid_sanitized="a", video_url="https://example.com/2.mp4"),
        InputRow(index=2, pid_raw="a", pid_sanitized="a", video_url="https://example.com/3.mp4"),
    ]

    names = assign_output_filenames(rows)

    assert names == {0: "a.mp4", 1: "a__2.mp4", 2: "a__3.mp4"}


def test_assign_output_filenames_uses_sanitized_pid() -> None:
    rows = [
        InputRow(index=10, pid_raw="a/b", pid_sanitized="a_b", video_url="https://example.com/1.mp4"),
        InputRow(index=11, pid_raw="a:b", pid_sanitized="a_b", video_url="https://example.com/2.mp4"),
    ]

    names = assign_output_filenames(rows)

    assert names[10] == "a_b.mp4"
    assert names[11] == "a_b__2.mp4"
