from __future__ import annotations

import csv
from io import BytesIO, StringIO
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from .models import InputPreview, InputRow, ParseFailure, PreviewRow


REQUIRED_EXCEL_COLUMNS = {"商品id", "视频链接"}
INVALID_FILENAME_CHARS = set('<>:"/\\|?*')
DEFAULT_CSV_IDENTIFIER_HEADERS = ("pid",)
ATTACHMENT_CSV_IDENTIFIER_HEADERS = ("item_id", "pid")


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


def count_non_empty_lines(text: str) -> int:
    return len(_collect_non_empty_lines(text))


def build_split_input_preview(
    pid_text: str,
    video_url_text: str,
    upload_file_name: str | None = None,
    upload_bytes: bytes | None = None,
) -> InputPreview:
    return _build_split_identifier_input_preview(
        identifier_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name=upload_file_name,
        upload_bytes=upload_bytes,
        csv_identifier_headers=DEFAULT_CSV_IDENTIFIER_HEADERS,
        csv_header_hint="pid,video_url",
        identifier_label="pid",
    )


def build_attachment_input_preview(
    item_id_text: str,
    video_url_text: str,
    upload_file_name: str | None = None,
    upload_bytes: bytes | None = None,
) -> InputPreview:
    return _build_split_identifier_input_preview(
        identifier_text=item_id_text,
        video_url_text=video_url_text,
        upload_file_name=upload_file_name,
        upload_bytes=upload_bytes,
        csv_identifier_headers=ATTACHMENT_CSV_IDENTIFIER_HEADERS,
        csv_header_hint="item_id,video_url（兼容 pid,video_url）",
        identifier_label="item_id",
    )


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
    return _parse_split_identifier_inputs_with_errors(
        identifier_text=pid_text,
        video_url_text=video_url_text,
        upload_file_name=upload_file_name,
        upload_bytes=upload_bytes,
        csv_identifier_headers=DEFAULT_CSV_IDENTIFIER_HEADERS,
        csv_header_hint="pid,video_url",
        identifier_label="pid",
    )


def parse_attachment_inputs_with_errors(
    item_id_text: str,
    video_url_text: str,
    upload_file_name: str | None = None,
    upload_bytes: bytes | None = None,
) -> tuple[list[InputRow], list[ParseFailure]]:
    return _parse_split_identifier_inputs_with_errors(
        identifier_text=item_id_text,
        video_url_text=video_url_text,
        upload_file_name=upload_file_name,
        upload_bytes=upload_bytes,
        csv_identifier_headers=ATTACHMENT_CSV_IDENTIFIER_HEADERS,
        csv_header_hint="item_id,video_url（兼容 pid,video_url）",
        identifier_label="item_id",
    )


def parse_inputs_with_errors(
    text: str, csv_bytes: bytes | None
) -> tuple[list[InputRow], list[ParseFailure]]:
    # 文本框优先：只要有至少一条非空行，就忽略 CSV
    if any(line.strip() for line in text.splitlines()):
        return _parse_text_rows(text)
    if csv_bytes:
        return _parse_csv_rows(
            csv_bytes=csv_bytes,
            identifier_headers=DEFAULT_CSV_IDENTIFIER_HEADERS,
            csv_header_hint="pid,video_url",
            identifier_label="pid",
        )
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

        error = _validate_row(identifier_raw=pid_raw, video_url=video_url, identifier_label="pid")
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


def _parse_split_identifier_inputs_with_errors(
    identifier_text: str,
    video_url_text: str,
    upload_file_name: str | None,
    upload_bytes: bytes | None,
    csv_identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> tuple[list[InputRow], list[ParseFailure]]:
    has_identifier_text = any(line.strip() for line in identifier_text.splitlines())
    has_url_text = any(line.strip() for line in video_url_text.splitlines())
    if has_identifier_text or has_url_text:
        return _parse_split_text_rows(
            pid_text=identifier_text,
            video_url_text=video_url_text,
            identifier_label=identifier_label,
        )
    if upload_bytes:
        return _parse_uploaded_rows(
            upload_file_name=upload_file_name,
            upload_bytes=upload_bytes,
            csv_identifier_headers=csv_identifier_headers,
            csv_header_hint=csv_header_hint,
            identifier_label=identifier_label,
        )
    return [], []


def _build_split_identifier_input_preview(
    identifier_text: str,
    video_url_text: str,
    upload_file_name: str | None,
    upload_bytes: bytes | None,
    csv_identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> InputPreview:
    identifier_lines = _collect_non_empty_lines(identifier_text)
    video_url_lines = _collect_non_empty_lines(video_url_text)
    notices: list[str] = []

    if identifier_lines or video_url_lines:
        if upload_bytes:
            notices.append("已检测到文本输入，当前预览与处理会忽略上传文件。")
        return _build_text_preview(
            identifier_lines=identifier_lines,
            video_url_lines=video_url_lines,
            identifier_label=identifier_label,
            notices=notices,
        )

    if upload_bytes:
        return _build_uploaded_preview(
            upload_file_name=upload_file_name,
            upload_bytes=upload_bytes,
            csv_identifier_headers=csv_identifier_headers,
            csv_header_hint=csv_header_hint,
            identifier_label=identifier_label,
        )

    return InputPreview(
        source="EMPTY",
        identifier_count=0,
        video_url_count=0,
        rows=[],
        blocking_errors=[],
        notices=[],
    )


def _parse_split_text_rows(
    pid_text: str,
    video_url_text: str,
    identifier_label: str = "pid",
) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []

    # 预览和正式处理统一按非空行配对，避免中间空行导致错位
    pid_lines = _collect_non_empty_lines(pid_text)
    url_lines = _collect_non_empty_lines(video_url_text)

    row_index = 0
    for i in range(max(len(pid_lines), len(url_lines))):
        pid_raw = pid_lines[i] if i < len(pid_lines) else ""
        video_url = url_lines[i] if i < len(url_lines) else ""

        error = _validate_row(
            identifier_raw=pid_raw,
            video_url=video_url,
            identifier_label=identifier_label,
        )
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


def _collect_non_empty_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _build_text_preview(
    identifier_lines: list[str],
    video_url_lines: list[str],
    identifier_label: str,
    notices: list[str],
) -> InputPreview:
    identifier_count = len(identifier_lines)
    video_url_count = len(video_url_lines)
    if identifier_count != video_url_count:
        return InputPreview(
            source="TEXT",
            identifier_count=identifier_count,
            video_url_count=video_url_count,
            rows=[],
            blocking_errors=[
                f"输入框行数不一致：{identifier_label} 共 {identifier_count} 条，视频链接共 {video_url_count} 条。请调整一致后再继续。"
            ],
            notices=notices,
        )

    rows = [
        PreviewRow(index=index, pid_raw=identifier_raw, video_url=video_url)
        for index, (identifier_raw, video_url) in enumerate(zip(identifier_lines, video_url_lines), start=1)
    ]
    return InputPreview(
        source="TEXT",
        identifier_count=identifier_count,
        video_url_count=video_url_count,
        rows=rows,
        blocking_errors=_collect_preview_row_errors(rows, identifier_label=identifier_label),
        notices=notices,
    )


def _decode_csv(csv_bytes: bytes) -> str:
    try:
        return csv_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        return csv_bytes.decode("utf-8", errors="replace")


def _normalize_header(value: object) -> str:
    return "".join(str(value).strip().lower().replace("_", " ").split())


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _build_uploaded_preview(
    upload_file_name: str | None,
    upload_bytes: bytes,
    csv_identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> InputPreview:
    suffix = Path(upload_file_name or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return _build_excel_preview(upload_bytes, identifier_label=identifier_label)
    if suffix in {"", ".csv"}:
        return _build_csv_preview(
            csv_bytes=upload_bytes,
            identifier_headers=csv_identifier_headers,
            csv_header_hint=csv_header_hint,
            identifier_label=identifier_label,
        )

    return InputPreview(
        source="UPLOAD",
        identifier_count=0,
        video_url_count=0,
        rows=[],
        blocking_errors=[f"不支持的文件类型: {upload_file_name or 'unknown'}"],
        notices=[],
    )


def _build_excel_preview(excel_bytes: bytes, identifier_label: str) -> InputPreview:
    try:
        df = pd.read_excel(BytesIO(excel_bytes), dtype=object)
    except Exception as exc:  # noqa: BLE001
        return InputPreview(
            source="UPLOAD",
            identifier_count=0,
            video_url_count=0,
            rows=[],
            blocking_errors=[f"Excel 解析失败: {exc}"],
            notices=[],
        )

    normalized_headers = {_normalize_header(col): col for col in df.columns}
    normalized_required = {_normalize_header(col) for col in REQUIRED_EXCEL_COLUMNS}
    has_required_headers = normalized_required.issubset(set(normalized_headers.keys()))

    if has_required_headers:
        identifier_col = normalized_headers[_normalize_header("商品id")]
        url_col = normalized_headers[_normalize_header("视频链接")]
        rows = _extract_preview_rows_from_dataframe(df, identifier_col=identifier_col, url_col=url_col)
        blocking_errors = _collect_preview_row_errors(rows, identifier_label=identifier_label)
        notices: list[str] = []
    else:
        rows = _extract_preview_rows_from_dataframe(df, identifier_col=None, url_col=None)
        blocking_errors = ["Excel 缺少必需列: 商品id,视频链接"]
        notices = []
        if rows:
            notices.append("当前仅预览 Excel 前两列原始数据，修正列名后才能开始处理。")

    identifier_count, video_url_count = _count_preview_values(rows)
    return InputPreview(
        source="UPLOAD",
        identifier_count=identifier_count,
        video_url_count=video_url_count,
        rows=rows,
        blocking_errors=blocking_errors,
        notices=notices,
    )


def _build_csv_preview(
    csv_bytes: bytes,
    identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> InputPreview:
    content = _decode_csv(csv_bytes)
    table = list(csv.reader(StringIO(content)))
    if not table:
        return InputPreview(
            source="UPLOAD",
            identifier_count=0,
            video_url_count=0,
            rows=[],
            blocking_errors=[],
            notices=[],
        )

    data_rows = table[1:]
    normalized_headers = [_normalize_header(col) for col in table[0]]
    normalized_identifier_headers = {_normalize_header(item) for item in identifier_headers}
    identifier_col = next(
        (index for index, header in enumerate(normalized_headers) if header in normalized_identifier_headers),
        None,
    )
    url_header = _normalize_header("video_url")
    url_col = normalized_headers.index(url_header) if url_header in normalized_headers else None

    if identifier_col is not None and url_col is not None:
        rows = _extract_preview_rows_from_table(data_rows, identifier_col=identifier_col, url_col=url_col)
        blocking_errors = _collect_preview_row_errors(rows, identifier_label=identifier_label)
        notices: list[str] = []
    else:
        rows = _extract_preview_rows_from_table(data_rows, identifier_col=0, url_col=1) if _has_two_columns(table) else []
        blocking_errors = [f"CSV 缺少必需表头: {csv_header_hint}"]
        notices = []
        if rows:
            notices.append("当前仅预览 CSV 前两列原始数据，修正表头后才能开始处理。")

    identifier_count, video_url_count = _count_preview_values(rows)
    return InputPreview(
        source="UPLOAD",
        identifier_count=identifier_count,
        video_url_count=video_url_count,
        rows=rows,
        blocking_errors=blocking_errors,
        notices=notices,
    )


def _parse_uploaded_rows(
    upload_file_name: str | None,
    upload_bytes: bytes,
    csv_identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> tuple[list[InputRow], list[ParseFailure]]:
    suffix = Path(upload_file_name or "").suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        return _parse_excel_rows(upload_bytes, identifier_label=identifier_label)
    if suffix in {"", ".csv"}:
        return _parse_csv_rows(
            csv_bytes=upload_bytes,
            identifier_headers=csv_identifier_headers,
            csv_header_hint=csv_header_hint,
            identifier_label=identifier_label,
        )

    return [], [
        ParseFailure(
            index=0,
            pid_raw="",
            error=f"不支持的文件类型: {upload_file_name or 'unknown'}",
        )
    ]


def _parse_excel_rows(
    excel_bytes: bytes,
    identifier_label: str = "pid",
) -> tuple[list[InputRow], list[ParseFailure]]:
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

        error = _validate_row(
            identifier_raw=pid_raw,
            video_url=video_url,
            identifier_label=identifier_label,
        )
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


def _parse_csv_rows(
    csv_bytes: bytes,
    identifier_headers: tuple[str, ...],
    csv_header_hint: str,
    identifier_label: str,
) -> tuple[list[InputRow], list[ParseFailure]]:
    rows: list[InputRow] = []
    failures: list[ParseFailure] = []

    content = _decode_csv(csv_bytes)
    table = list(csv.reader(StringIO(content)))
    if not table:
        return rows, failures

    normalized_headers = [_normalize_header(col) for col in table[0]]
    normalized_identifier_headers = {_normalize_header(item) for item in identifier_headers}
    identifier_col = next(
        (index for index, header in enumerate(normalized_headers) if header in normalized_identifier_headers),
        None,
    )
    url_header = _normalize_header("video_url")
    url_col = normalized_headers.index(url_header) if url_header in normalized_headers else None
    has_required_headers = identifier_col is not None and url_col is not None

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
                    error=f"CSV 缺少必需表头: {csv_header_hint}",
                )
            )
            index += 1

        if index == 0 and any(cell.strip() for cell in table[0]):
            pid_raw = table[0][0].strip() if table[0] else ""
            failures.append(
                ParseFailure(
                    index=0,
                    pid_raw=pid_raw,
                    error=f"CSV 缺少必需表头: {csv_header_hint}",
                )
            )
        return rows, failures

    index = 0
    for raw in table[1:]:
        if not any(cell.strip() for cell in raw):
            continue

        pid_raw = raw[identifier_col].strip() if identifier_col < len(raw) else ""
        video_url = raw[url_col].strip() if url_col < len(raw) else ""

        error = _validate_row(
            identifier_raw=pid_raw,
            video_url=video_url,
            identifier_label=identifier_label,
        )
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


def _extract_preview_rows_from_dataframe(
    df: pd.DataFrame, identifier_col: object | None, url_col: object | None
) -> list[PreviewRow]:
    if identifier_col is None or url_col is None:
        if len(df.columns) < 2:
            return []
        identifier_col = df.columns[0]
        url_col = df.columns[1]

    rows: list[PreviewRow] = []
    for index, row in enumerate(df[[identifier_col, url_col]].itertuples(index=False, name=None), start=1):
        pid_raw = _to_text(row[0])
        video_url = _to_text(row[1])
        if not pid_raw and not video_url:
            continue
        rows.append(PreviewRow(index=index, pid_raw=pid_raw, video_url=video_url))
    return rows


def _extract_preview_rows_from_table(
    table: list[list[str]], identifier_col: int, url_col: int
) -> list[PreviewRow]:
    rows: list[PreviewRow] = []
    for index, raw in enumerate(table, start=1):
        if not any(cell.strip() for cell in raw):
            continue

        pid_raw = raw[identifier_col].strip() if identifier_col < len(raw) else ""
        video_url = raw[url_col].strip() if url_col < len(raw) else ""
        if not pid_raw and not video_url:
            continue
        rows.append(PreviewRow(index=index, pid_raw=pid_raw, video_url=video_url))
    return rows


def _has_two_columns(table: list[list[str]]) -> bool:
    return any(len(row) >= 2 for row in table)


def _count_preview_values(rows: list[PreviewRow]) -> tuple[int, int]:
    identifier_count = sum(1 for row in rows if row.pid_raw)
    video_url_count = sum(1 for row in rows if row.video_url)
    return identifier_count, video_url_count


def _collect_preview_row_errors(rows: list[PreviewRow], identifier_label: str) -> list[str]:
    errors: list[str] = []
    for row in rows:
        error = _validate_row(
            identifier_raw=row.pid_raw,
            video_url=row.video_url,
            identifier_label=identifier_label,
        )
        if error:
            errors.append(f"第 {row.index} 条：{error}")
    return errors


def _validate_row(identifier_raw: str, video_url: str, identifier_label: str = "pid") -> str:
    if not identifier_raw:
        return f"{identifier_label} 不能为空"
    if not video_url:
        return "video_url 不能为空"
    if not is_valid_public_video_url(video_url):
        return "video_url 非法：仅支持公开 http/https 链接"
    return ""


def assign_output_filenames(rows: list[InputRow]) -> dict[int, str]:
    assigned: dict[int, str] = {}

    for order, row in enumerate(sorted(rows, key=lambda item: item.index), start=1):
        assigned[row.index] = f"{order}.mp4"

    return assigned


def assign_attachment_output_filenames(rows: list[InputRow]) -> dict[int, str]:
    assigned: dict[int, str] = {}
    name_counts: dict[str, int] = {}

    for row in sorted(rows, key=lambda item: item.index):
        base_name = row.pid_sanitized
        current_count = name_counts.get(base_name, 0) + 1
        name_counts[base_name] = current_count

        suffix = "" if current_count == 1 else f"__{current_count}"
        assigned[row.index] = f"{base_name}{suffix}.mp4"

    return assigned
