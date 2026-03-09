from __future__ import annotations

from video_splicer.input_parser import assign_attachment_output_filenames
from video_splicer.models import InputRow


def test_attachment_output_filenames_use_item_id_and_suffix_duplicates() -> None:
    rows = [
        InputRow(index=0, pid_raw="item/a", pid_sanitized="item_a", video_url="https://example.com/1.mp4"),
        InputRow(index=1, pid_raw="item:a", pid_sanitized="item_a", video_url="https://example.com/2.mp4"),
        InputRow(index=2, pid_raw="item b", pid_sanitized="item b", video_url="https://example.com/3.mp4"),
    ]

    names = assign_attachment_output_filenames(rows)

    assert names == {
        0: "item_a.mp4",
        1: "item_a__2.mp4",
        2: "item b.mp4",
    }
