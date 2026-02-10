from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .models import InputRow, ParseFailure


REQUIRED_COLUMNS = {"pid", "video_url"}
REQUIRED_EXCEL_COLUMNS = {"商品id", "视频链接"}
INVALID_FILENAME_CHARS = set('<>:"/\\|?*')


def sanitize_pid(pid_raw: str) -> str:
    pid = pid_raw.strip()
    cleaned_chars: list[str] = []
    for char in pid:
        code = ord(char)
        if char in INVALID_FILENAME_CHARS or code < 32 or code == 127:
            cleaned_chars.append("_")
        else:
            cleaned_chars.append(char)
    cleaned = "".join(cleaned_chars).rstrip(" .")
    return cleaned if cleaned else "pid"


def is_valid_public_video_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def parse_inputs(text: str, csv_bytes: bytes | None) -> list[InputRow]:
    rows, _ = parse_inputs_with_errors(text=text, csv_bytes=csv_bytes)
    return rows


def parse_split_inputs_with_errors(
    pid_text: str,
    video_url_text: str,
    upload_file_name: str | None = None,
    upload_bytes: bytes | None = None,
) -> tuple[list[InputRow], list[ParseFailure]]:
    # 分列输入优先：任一输入框有内容就忽略 CSV
    has_pid_text = any(line.strip() for line in pid_text.splitlines())
    has_url_text = any(line.strip() for line in video_url_text.splitlines())
    if has_pid_text or has_url_text:
        return _parse_split_text_rows(pid_text=pid_text, video_url_text=video_url_text)
    if upload_bytes:
        return _parse_uploaded_rows(
            upload_file_name=upload_file_name,
            upload_bytes=upload_bytes,
        )
    return [], []


def parse_inputs_with_errors(
    text: str, csv_bytes: bytes | None
) -> tuple[list[InputRow], list[ParseFailure]]:
    # 文本框优先：只要有至少一条非空行，就忽略 CSV
    if any(line.strip() for line in text.splitlines()):
        return _parse_text_rows(text)
    if csv_bytes:
        return _parse_csv_rows(csv_bytes)
    return [], []


def _parse_text_rows(text: str) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []
    index = 0

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "," not in line:
            failures.append(
                ParseFailure(
                    index=index,
                    pid_raw=line,
                    error="输入格式错误：需为 pid,video_url",
                )
            )
            index += 1
            continue

        pid_raw, video_url = line.split(",", 1)
        pid_raw = pid_raw.strip()
        video_url = video_url.strip()

        error = _validate_row(pid_raw=pid_raw, video_url=video_url)
        if error:
            failures.append(ParseFailure(index=index, pid_raw=pid_raw, error=error))
        else:
            rows.append(
                InputRow(
                    index=index,
                    pid_raw=pid_raw,
                    pid_sanitized=sanitize_pid(pid_raw),
                    video_url=video_url,
                )
            )
        index += 1

    return rows, failures


def _parse_split_text_rows(
    pid_text: str,
    video_url_text: str,
) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []

    pid_lines = [line.strip() for line in pid_text.splitlines()]
    url_lines = [line.strip() for line in video_url_text.splitlines()]

    row_index = 0
    for i in range(max(len(pid_lines), len(url_lines))):
        pid_raw = pid_lines[i] if i < len(pid_lines) else ""
        video_url = url_lines[i] if i < len(url_lines) else ""

        # 两列同一行都为空则忽略
        if not pid_raw and not video_url:
            continue

        error = _validate_row(pid_raw=pid_raw, video_url=video_url)
        if error:
            failures.append(ParseFailure(index=row_index, pid_raw=pid_raw, error=error))
        else:
            rows.append(
                InputRow(
                    index=row_index,
                    pid_raw=pid_raw,
                    pid_sanitized=sanitize_pid(pid_raw),
                    video_url=video_url,
                )
            )
        row_index += 1

    return rows, failures


def _decode_csv(csv_bytes: bytes) -> str:
    try:
        return csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return csv_bytes.decode("utf-8", errors="replace")


def _normalize_header(value: object) -> str:
    return "".join(str(value).strip().lower().split())


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_uploaded_rows(
    upload_file_name: str | None,
    upload_bytes: bytes,
) -> tuple[list[InputRow], list[ParseFailure]]:
    suffix = Path(upload_file_name or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_excel_rows(upload_bytes)
    if suffix in {"", ".csv"}:
        return _parse_csv_rows(upload_bytes)

    return [], [
        ParseFailure(
            index=0,
            pid_raw="",
            error=f"不支持的文件类型: {upload_file_name or 'unknown'}",
        )
    ]


def _parse_excel_rows(excel_bytes: bytes) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []

    try:
        df = pd.read_excel(BytesIO(excel_bytes), dtype=object)
    except Exception as exc:  # noqa: BLE001
        return [], [ParseFailure(index=0, pid_raw="", error=f"Excel 解析失败: {exc}")]

    normalized_headers = {_normalize_header(col): col for col in df.columns}
    normalized_required = {_normalize_header(col) for col in REQUIRED_EXCEL_COLUMNS}
    if not normalized_required.issubset(set(normalized_headers.keys())):
        return [], [ParseFailure(index=0, pid_raw="", error="Excel 缺少必需列: 商品id,视频链接")]

    pid_col = normalized_headers[_normalize_header("商品id")]
    url_col = normalized_headers[_normalize_header("视频链接")]

    index = 0
    for row in df[[pid_col, url_col]].itertuples(index=False, name=None):
        pid_raw = _to_text(row[0])
        video_url = _to_text(row[1])

        # 需求：链接为空时直接忽略，不作为失败项
        if not video_url:
            continue

        error = _validate_row(pid_raw=pid_raw, video_url=video_url)
        if error:
            failures.append(ParseFailure(index=index, pid_raw=pid_raw, error=error))
        else:
            rows.append(
                InputRow(
                    index=index,
                    pid_raw=pid_raw,
                    pid_sanitized=sanitize_pid(pid_raw),
                    video_url=video_url,
                )
            )
        index += 1

    return rows, failures


def _parse_csv_rows(csv_bytes: bytes) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []

    content = _decode_csv(csv_bytes)
    table = list(csv.reader(StringIO(content)))
    if not table:
        return rows, failures

    normalized_headers = [col.strip().lower() for col in table[0]]
    has_required_headers = REQUIRED_COLUMNS.issubset(set(normalized_headers))

    if not has_required_headers:
        index = 0
        for raw in table[1:]:
            if not any(cell.strip() for cell in raw):
                continue
            pid_raw = raw[0].strip() if raw else ""
            failures.append(
                ParseFailure(
                    index=index,
                    pid_raw=pid_raw,
                    error="CSV 缺少必需表头: pid,video_url",
                )
            )
            index += 1

        if index == 0 and any(cell.strip() for cell in table[0]):
            pid_raw = table[0][0].strip() if table[0] else ""
            failures.append(
                ParseFailure(
                    index=0,
                    pid_raw=pid_raw,
                    error="CSV 缺少必需表头: pid,video_url",
                )
            )
        return rows, failures

    pid_col = normalized_headers.index("pid")
    url_col = normalized_headers.index("video_url")

    index = 0
    for raw in table[1:]:
        if not any(cell.strip() for cell in raw):
            continue

        pid_raw = raw[pid_col].strip() if pid_col < len(raw) else ""
        video_url = raw[url_col].strip() if url_col < len(raw) else ""

        error = _validate_row(pid_raw=pid_raw, video_url=video_url)
        if error:
            failures.append(ParseFailure(index=index, pid_raw=pid_raw, error=error))
        else:
            rows.append(
                InputRow(
                    index=index,
                    pid_raw=pid_raw,
                    pid_sanitized=sanitize_pid(pid_raw),
                    video_url=video_url,
                )
            )
        index += 1

    return rows, failures


def _validate_row(pid_raw: str, video_url: str) -> str:
    if not pid_raw:
        return "pid 不能为空"
    if not video_url:
        return "video_url 不能为空"
    if not is_valid_public_video_url(video_url):
        return "video_url 非法：仅支持公开 http/https 链接"
    return ""


def assign_output_filenames(rows: list[InputRow]) -> dict[int, str]:
    counts: dict[str, int] = {}
    assigned: dict[int, str] = {}

    for row in sorted(rows, key=lambda item: item.index):
        base_name = row.pid_sanitized or "pid"
        counts[base_name] = counts.get(base_name, 0) + 1
        duplicate_index = counts[base_name]

        if duplicate_index == 1:
            filename = f"{base_name}.mp4"
        else:
            filename = f"{base_name}__{duplicate_index}.mp4"

        assigned[row.index] = filename

    return assigned
