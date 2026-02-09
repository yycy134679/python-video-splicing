from __future__ import annotations

import codecs

from video_splicer.artifact import build_result_csv
from video_splicer.models import TaskResult


def test_result_csv_uses_utf8_bom_and_fixed_columns() -> None:
    results = [
        TaskResult(
            index=1,
            pid="b",
            output_filename="b.mp4",
            status="SUCCESS",
            error="",
            duration_sec=2.3456,
            output_path=None,
        ),
        TaskResult(
            index=0,
            pid="a",
            output_filename="",
            status="FAILED",
            error="bad url",
            duration_sec=0.0,
            output_path=None,
        ),
    ]

    payload = build_result_csv(results)

    assert payload.startswith(codecs.BOM_UTF8)

    text = payload.decode("utf-8-sig").strip().splitlines()
    assert text[0] == "pid,output_filename,status,error,duration_sec"
    assert text[1].startswith("a,,FAILED,bad url,")
    assert text[2].startswith("b,b.mp4,SUCCESS,,")
