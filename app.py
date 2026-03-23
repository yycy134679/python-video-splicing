from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st
import streamlit.runtime as st_runtime

from video_splicer.artifact import build_download_artifact, collect_work_dirs, save_results_directory
from video_splicer.config import (
    DEFAULT_ENDCARD_PATH,
    build_runtime_config,
    load_config,
    validate_attachment_runtime,
    validate_splice_runtime,
)
from video_splicer.endcard_store import EndcardAsset, resolve_active_endcard
from video_splicer.endcard_ui import (
    build_endcard_upload_trigger_html,
    build_endcard_upload_widget_key,
    save_endcard_upload,
)
from video_splicer.input_parser import (
    assign_attachment_output_filenames,
    assign_output_filenames,
    build_attachment_input_preview,
    build_split_input_preview,
    count_non_empty_lines,
    parse_attachment_inputs_with_errors,
    parse_split_inputs_with_errors,
)
from video_splicer.models import Config, InputPreview, InputRow, ParseFailure, TaskResult
from video_splicer.runner import process_attachment_batch, process_batch

PAGE_SPLICE = "视频拼接"
PAGE_ATTACHMENT = "视频链接转附件"
RUNTIME_SETTING_KEYS = {
    "max_video_mb": "sp_runtime_max_video_mb",
    "max_workers": "sp_runtime_max_workers",
    "task_timeout_sec": "sp_runtime_task_timeout_sec",
    "download_retries": "sp_runtime_download_retries",
}
PageParser = Callable[[str, str, str | None, bytes | None], tuple[list[InputRow], list[ParseFailure]]]
PageProcessor = Callable[
    [list[InputRow], Config, Callable[[str], None] | None, Callable[[int, int], None] | None],
    list[TaskResult],
]
FilenameAssigner = Callable[[list[InputRow]], dict[int, str]]
PreviewBuilder = Callable[[str, str, str | None, bytes | None], InputPreview]


def _state_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _build_input_signature(identifier_text: str, video_url_text: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(identifier_text.encode("utf-8"))
    hasher.update(b"\0")
    hasher.update(video_url_text.encode("utf-8"))
    return hasher.hexdigest()


def _ensure_page_state(prefix: str) -> None:
    for suffix, default_value in (
        ("results", None),
        ("logs", []),
        ("download", None),
        ("local_result_dir", None),
        ("local_result_error", ""),
        ("open_result_dir_error", ""),
        ("preview", None),
        ("preview_signature", ""),
    ):
        key = _state_key(prefix, suffix)
        if key not in st.session_state:
            st.session_state[key] = default_value


def _reset_page_state(prefix: str) -> None:
    st.session_state[_state_key(prefix, "results")] = None
    st.session_state[_state_key(prefix, "logs")] = []
    st.session_state[_state_key(prefix, "download")] = None
    st.session_state[_state_key(prefix, "local_result_dir")] = None
    st.session_state[_state_key(prefix, "local_result_error")] = ""
    st.session_state[_state_key(prefix, "open_result_dir_error")] = ""


def _ensure_endcard_state() -> None:
    if "sp_endcard_feedback" not in st.session_state:
        st.session_state["sp_endcard_feedback"] = ""
    if "sp_endcard_error" not in st.session_state:
        st.session_state["sp_endcard_error"] = ""
    if "sp_endcard_upload_widget_version" not in st.session_state:
        st.session_state["sp_endcard_upload_widget_version"] = 0


def _sync_preview_state(prefix: str, current_signature: str) -> None:
    preview_signature = str(st.session_state.get(_state_key(prefix, "preview_signature"), ""))
    if preview_signature and preview_signature != current_signature:
        _reset_page_state(prefix)
        st.session_state[_state_key(prefix, "preview")] = None
        st.session_state[_state_key(prefix, "preview_signature")] = ""


def _store_preview(prefix: str, preview: InputPreview, signature: str) -> None:
    st.session_state[_state_key(prefix, "preview")] = preview
    st.session_state[_state_key(prefix, "preview_signature")] = signature


def _get_current_preview(prefix: str, current_signature: str) -> InputPreview | None:
    preview_signature = str(st.session_state.get(_state_key(prefix, "preview_signature"), ""))
    if preview_signature != current_signature:
        return None
    return st.session_state.get(_state_key(prefix, "preview"))


def _summarize_messages(messages: list[str], limit: int = 8) -> list[str]:
    unique_messages: list[str] = []
    seen_messages: set[str] = set()
    for message in messages:
        if message in seen_messages:
            continue
        seen_messages.add(message)
        unique_messages.append(message)

    if len(unique_messages) <= limit:
        return unique_messages

    remaining_count = len(unique_messages) - limit
    return unique_messages[:limit] + [f"其余 {remaining_count} 条问题请先修正后再试。"]


def _format_preview_error_text(preview: InputPreview) -> str:
    messages = _summarize_messages(preview.blocking_errors)
    return "当前数据校验未通过：\n- " + "\n- ".join(messages)


def _format_parse_failure_messages(parse_failures: list[ParseFailure]) -> list[str]:
    messages: list[str] = []
    for failure in parse_failures:
        if failure.error.startswith(("CSV 缺少必需表头", "Excel 缺少必需列", "Excel 解析失败", "不支持的文件类型")):
            messages.append(failure.error)
        else:
            messages.append(f"第 {failure.index + 1} 条：{failure.error}")
    return _summarize_messages(messages)


def _render_preview_table(rows: list[dict[str, object]]) -> None:
    preview_frame = pd.DataFrame(rows)
    st.dataframe(
        preview_frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "视频链接": st.column_config.LinkColumn("视频链接"),
        },
    )


def _render_input_preview(preview: InputPreview, identifier_preview_label: str) -> None:
    st.subheader("数据预览")

    for notice in preview.notices:
        st.info(notice)

    if preview.blocking_errors:
        st.error(_format_preview_error_text(preview))

    if not preview.rows:
        return

    total_rows = len(preview.rows)
    st.caption(
        f"原始数据共 {total_rows} 条，{identifier_preview_label} {preview.identifier_count} 条，视频链接 {preview.video_url_count} 条。"
    )

    table_rows = [
        {
            "序号": row.index,
            identifier_preview_label: row.pid_raw,
            "视频链接": row.video_url,
        }
        for row in preview.rows
    ]
    if total_rows <= 10:
        _render_preview_table(table_rows)
        return

    st.markdown("**前 5 条**")
    _render_preview_table(table_rows[:5])
    st.markdown("**后 5 条**")
    _render_preview_table(table_rows[-5:])


def _render_results(prefix: str, identifier_label: str) -> None:
    results: list[TaskResult] | None = st.session_state.get(_state_key(prefix, "results"))
    if results is None:
        return

    logs: list[str] = st.session_state.get(_state_key(prefix, "logs"), [])
    download_obj: dict[str, bytes | str] | None = st.session_state.get(_state_key(prefix, "download"))
    local_result_dir = st.session_state.get(_state_key(prefix, "local_result_dir"))
    local_result_error = str(st.session_state.get(_state_key(prefix, "local_result_error"), ""))
    open_result_error = str(st.session_state.get(_state_key(prefix, "open_result_dir_error"), ""))

    st.subheader("结果表")
    table_rows = [
        {
            identifier_label: item.pid,
            "output_filename": item.output_filename,
            "status": item.status,
            "error": item.error,
            "duration_sec": round(item.duration_sec, 3),
        }
        for item in results
    ]
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True)

    st.subheader("实时日志")
    st.code("\n".join(logs[-500:]) if logs else "(无日志)")

    if download_obj:
        st.download_button(
            label=f"下载结果：{download_obj['file_name']}",
            data=download_obj["data"],
            file_name=str(download_obj["file_name"]),
            mime=str(download_obj["mime"]),
            key=_state_key(prefix, "download_button"),
        )

    if local_result_error:
        st.error(local_result_error)

    if local_result_dir:
        st.caption(f"本次结果已保存到：{local_result_dir}")
        if st.button("打开结果目录", key=_state_key(prefix, "open_result_dir_button")):
            open_result_error = _open_result_directory(Path(str(local_result_dir))) or ""
            st.session_state[_state_key(prefix, "open_result_dir_error")] = open_result_error

        if open_result_error:
            st.error(open_result_error)


def _open_result_directory(result_dir: Path) -> str | None:
    if not result_dir.is_dir():
        return f"结果目录不存在：{result_dir}"

    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(result_dir)], check=True)
        elif os.name == "nt":
            os.startfile(str(result_dir))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(result_dir)], check=True)
    except Exception as exc:  # noqa: BLE001
        return f"打开结果目录失败：{exc}"

    return None


def _format_file_size(size_bytes: int) -> str:
    if size_bytes >= 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.2f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def _format_last_modified(path: Path) -> str:
    if not path.is_file():
        return "未找到文件"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")


def _default_endcard_path() -> Path:
    return Path(os.getenv("SP_ENDCARD_PATH", str(DEFAULT_ENDCARD_PATH))).expanduser()


def _resolve_current_endcard_asset() -> EndcardAsset:
    return resolve_active_endcard(default_endcard=_default_endcard_path())


def _build_endcard_media_url(asset: EndcardAsset) -> str | None:
    if not asset.path.is_file():
        return None
    if not st_runtime.exists():
        return None

    return st_runtime.get_instance().media_file_mgr.add(
        str(asset.path),
        asset.mime_type,
        coordinates="endcard-preview-link",
        file_name=asset.file_name,
    )


def _render_hidden_endcard_uploader() -> None:
    widget_version = int(st.session_state.get("sp_endcard_upload_widget_version", 0))
    uploaded_endcard = st.file_uploader(
        "上传新的落版视频",
        type=["mp4", "mov"],
        key=build_endcard_upload_widget_key(widget_version),
        help="仅支持 mp4 和 mov，上传成功后会覆盖当前生效的落版视频。",
        label_visibility="collapsed",
    )

    if uploaded_endcard is None:
        return

    feedback_message, error_message = save_endcard_upload(
        upload_name=uploaded_endcard.name,
        upload_bytes=uploaded_endcard.getvalue(),
    )
    st.session_state["sp_endcard_feedback"] = feedback_message
    st.session_state["sp_endcard_error"] = error_message
    st.session_state["sp_endcard_upload_widget_version"] = widget_version + 1
    st.rerun()


def _render_endcard_manager() -> None:
    _ensure_endcard_state()
    feedback_message = str(st.session_state.get("sp_endcard_feedback", ""))
    error_message = str(st.session_state.get("sp_endcard_error", ""))
    asset = _resolve_current_endcard_asset()

    if feedback_message:
        st.success(feedback_message)
        st.session_state["sp_endcard_feedback"] = ""
    if error_message:
        st.error(error_message)
        st.session_state["sp_endcard_error"] = ""

    summary_col, preview_button_col, upload_button_col = st.columns([4.6, 1.1, 1.1])

    with summary_col:
        status_label = "已上传" if asset.source == "MANAGED" else "默认"
        st.markdown(
            f"**当前落版：** {status_label}  |  **文件：** `{asset.file_name}`  |  **更新：** {_format_last_modified(asset.path)}"
        )

    with preview_button_col:
        preview_url = _build_endcard_media_url(asset)
        st.link_button("预览落版", url=preview_url or "#", use_container_width=True, disabled=preview_url is None)

    with upload_button_col:
        st.html(build_endcard_upload_trigger_html(), unsafe_allow_javascript=True)

    _render_hidden_endcard_uploader()


def _initialize_runtime_setting_state(config: Config) -> None:
    defaults = {
        RUNTIME_SETTING_KEYS["max_video_mb"]: int(config.max_video_mb),
        RUNTIME_SETTING_KEYS["max_workers"]: int(config.max_workers),
        RUNTIME_SETTING_KEYS["task_timeout_sec"]: int(config.task_timeout_sec),
        RUNTIME_SETTING_KEYS["download_retries"]: int(config.download_retries),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def _reset_runtime_setting_state(config: Config) -> None:
    st.session_state[RUNTIME_SETTING_KEYS["max_video_mb"]] = int(config.max_video_mb)
    st.session_state[RUNTIME_SETTING_KEYS["max_workers"]] = int(config.max_workers)
    st.session_state[RUNTIME_SETTING_KEYS["task_timeout_sec"]] = int(config.task_timeout_sec)
    st.session_state[RUNTIME_SETTING_KEYS["download_retries"]] = int(config.download_retries)


def _build_runtime_summary(config: Config, include_endcard: bool = False, output_label: str | None = None) -> str:
    summary_parts = [
        f"单条视频上限 {config.max_video_mb} MB",
        f"同时处理 {config.max_workers} 条",
        f"单条最长等待 {config.task_timeout_sec} 秒",
        f"下载失败重试 {config.download_retries} 次",
    ]
    if include_endcard:
        summary_parts.append("已启用落版拼接")
    if output_label:
        summary_parts.append(output_label)
    return "当前处理设置：" + " | ".join(summary_parts)


def _render_runtime_settings(base_config: Config) -> Config:
    _initialize_runtime_setting_state(base_config)

    with st.expander("处理参数设置", expanded=False):
        st.caption("这里的调整只影响你接下来点击“开始处理”的任务，不需要改环境变量。")
        if st.button("恢复默认配置", use_container_width=True):
            _reset_runtime_setting_state(base_config)
            st.rerun()

        st.number_input(
            "单条视频大小上限（MB）",
            min_value=10,
            max_value=2048,
            step=10,
            key=RUNTIME_SETTING_KEYS["max_video_mb"],
            help="超过这个大小的视频会直接拦截，避免误下载超大文件。",
        )
        st.caption("业务建议：大多数常规商品视频保持默认即可；遇到高清视频或长视频时再调大。")

        st.number_input(
            "同时处理数量",
            min_value=1,
            max_value=16,
            step=1,
            key=RUNTIME_SETTING_KEYS["max_workers"],
            help="数字越大处理越快，但会更占电脑性能和网络带宽。",
        )
        st.caption("业务建议：电脑性能一般或网络不稳时，用 2 到 4 更稳；批量很多时再适当调高。")

        st.number_input(
            "单条任务最长等待时间（秒）",
            min_value=30,
            max_value=3600,
            step=30,
            key=RUNTIME_SETTING_KEYS["task_timeout_sec"],
            help="单条视频从下载到处理完成，最多允许等待多久。",
        )
        st.caption("业务建议：如果视频较长、网络较慢，或需要跨 VPN 下载，可以适当调高。")

        st.number_input(
            "下载失败自动重试次数",
            min_value=0,
            max_value=10,
            step=1,
            key=RUNTIME_SETTING_KEYS["download_retries"],
            help="下载偶发失败时，系统会自动再试几次。",
        )
        st.caption("业务建议：网络稳定时保持默认即可；网络偶尔超时或 VPN 波动时可调到 3 到 4。")

        with st.expander("这些参数怎么选？", expanded=False):
            st.markdown(
                "\n".join(
                    [
                        "- `单条视频大小上限`：防止误处理超大文件，越大越宽松。",
                        "- `同时处理数量`：一次并行处理多少条，越大越快，但更吃电脑和网络。",
                        "- `单条任务最长等待时间`：网络慢、视频长时建议调高，避免处理中途超时。",
                        "- `下载失败自动重试次数`：适合网络偶发不稳定的场景，数字越大越愿意多试几次。",
                    ]
                )
            )

    return build_runtime_config(
        base_config=base_config,
        max_video_mb=int(st.session_state[RUNTIME_SETTING_KEYS["max_video_mb"]]),
        max_workers=int(st.session_state[RUNTIME_SETTING_KEYS["max_workers"]]),
        task_timeout_sec=int(st.session_state[RUNTIME_SETTING_KEYS["task_timeout_sec"]]),
        download_retries=int(st.session_state[RUNTIME_SETTING_KEYS["download_retries"]]),
    )


def _process_page_request(
    prefix: str,
    identifier_text: str,
    video_url_text: str,
    parser: PageParser,
    processor: PageProcessor,
    filename_assigner: FilenameAssigner,
    runtime_errors: list[str],
    identifier_label: str,
    result_dir_prefix: str,
    config: Config,
) -> None:
    _reset_page_state(prefix)

    progress_box = st.progress(0)
    log_box = st.empty()
    logs: list[str] = []

    def log_cb(message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        logs.append(f"[{ts}] {message}")
        log_box.code("\n".join(logs[-200:]))

    def progress_cb(done: int, total: int) -> None:
        ratio = 1.0 if total == 0 else done / total
        progress_box.progress(min(max(ratio, 0.0), 1.0))

    rows, parse_failures = parser(identifier_text, video_url_text, None, None)

    if not rows and not parse_failures:
        st.warning("请输入至少一条有效数据。")
        return

    if parse_failures:
        st.error("数据校验未通过：\n- " + "\n- ".join(_format_parse_failure_messages(parse_failures)))
        return

    processed_results: list[TaskResult] = []
    if rows:
        if runtime_errors:
            file_map = filename_assigner(rows)
            error_message = "; ".join(runtime_errors)
            processed_results = [
                TaskResult(
                    index=row.index,
                    pid=row.pid_raw,
                    output_filename=file_map[row.index],
                    status="FAILED",
                    error=error_message,
                    duration_sec=0.0,
                    output_path=None,
                )
                for row in rows
            ]
            log_cb("运行前置检查失败，已跳过处理")
            progress_cb(len(rows), len(rows))
        else:
            processed_results = processor(rows, config, log_cb, progress_cb)
    else:
        progress_cb(1, 1)

    all_results = sorted(processed_results, key=lambda item: item.index)
    mime, file_name, payload = build_download_artifact(all_results, identifier_label=identifier_label)
    local_result_dir: Path | None = None
    local_result_error = ""

    try:
        local_result_dir = save_results_directory(
            all_results,
            results_root_dir=config.results_root_dir,
            result_dir_prefix=result_dir_prefix,
            identifier_label=identifier_label,
        )
        log_cb(f"结果已保存到本地目录: {local_result_dir}")
    except Exception as exc:  # noqa: BLE001
        local_result_error = f"本地结果保存失败：{exc}"
        log_cb(local_result_error)

    for work_dir in collect_work_dirs(processed_results):
        shutil.rmtree(work_dir, ignore_errors=True)

    st.session_state[_state_key(prefix, "results")] = all_results
    st.session_state[_state_key(prefix, "logs")] = logs
    st.session_state[_state_key(prefix, "download")] = {
        "mime": mime,
        "file_name": file_name,
        "data": payload,
    }
    st.session_state[_state_key(prefix, "local_result_dir")] = str(local_result_dir) if local_result_dir else None
    st.session_state[_state_key(prefix, "local_result_error")] = local_result_error
    st.session_state[_state_key(prefix, "open_result_dir_error")] = ""


def _render_processing_page(
    prefix: str,
    page_title: str,
    identifier_label: str,
    result_dir_prefix: str,
    identifier_input_label: str,
    identifier_placeholder: str,
    instruction_lines: list[str],
    parser: PageParser,
    processor: PageProcessor,
    filename_assigner: FilenameAssigner,
    preview_builder: PreviewBuilder,
    runtime_errors: list[str],
    config_caption: str,
    config: Config,
    header_renderer: Callable[[], None] | None = None,
) -> None:
    _ensure_page_state(prefix)

    st.subheader(page_title)
    st.caption(config_caption)
    if header_renderer:
        header_renderer()
    if runtime_errors:
        st.error("运行前置检查未通过：\n- " + "\n- ".join(runtime_errors))

    with st.expander("输入说明", expanded=False):
        st.markdown("\n".join(instruction_lines))

    identifier_col, url_col = st.columns(2)
    with identifier_col:
        identifier_text = st.text_area(
            identifier_input_label,
            height=220,
            placeholder=identifier_placeholder,
            key=_state_key(prefix, "identifier_input"),
        )
        st.caption(f"当前共 {count_non_empty_lines(identifier_text)} 条数据")

    with url_col:
        video_url_text = st.text_area(
            "视频链接（每行一条）",
            height=220,
            placeholder=(
                "https://example.com/video1.mp4\n"
                "https://example.com/video2.mp4\n"
                "https://example.com/video3.mp4"
            ),
            key=_state_key(prefix, "video_url_input"),
        )
        st.caption(f"当前共 {count_non_empty_lines(video_url_text)} 条数据")

    current_signature = _build_input_signature(identifier_text, video_url_text)
    _sync_preview_state(prefix, current_signature)

    preview = _get_current_preview(prefix, current_signature)
    button_col, start_col = st.columns(2)
    with button_col:
        preview_clicked = st.button("确认数据并预览", key=_state_key(prefix, "preview_button"))

    if preview_clicked:
        preview = preview_builder(identifier_text, video_url_text, None, None)
        _store_preview(prefix, preview, current_signature)

    can_start_processing = bool(preview and not preview.blocking_errors)
    with start_col:
        start_clicked = st.button(
            "开始处理",
            type="primary",
            key=_state_key(prefix, "start"),
            disabled=not can_start_processing,
        )

    if not can_start_processing:
        st.caption("请先点击“确认数据并预览”，并确保当前数据校验通过后再开始处理。")

    if start_clicked:
        preview = preview_builder(identifier_text, video_url_text, None, None)
        _store_preview(prefix, preview, current_signature)
        if preview.blocking_errors:
            _reset_page_state(prefix)
            _render_input_preview(preview, identifier_input_label.replace("（每行一条）", ""))
            return
        _process_page_request(
            prefix=prefix,
            identifier_text=identifier_text,
            video_url_text=video_url_text,
            parser=parser,
            processor=processor,
            filename_assigner=filename_assigner,
            runtime_errors=runtime_errors,
            identifier_label=identifier_label,
            result_dir_prefix=result_dir_prefix,
            config=config,
        )

    if preview:
        _render_input_preview(preview, identifier_input_label.replace("（每行一条）", ""))

    _render_results(prefix, identifier_label)


def _parse_splice_inputs(
    identifier_text: str,
    video_url_text: str,
    upload_name: str | None,
    upload_bytes: bytes | None,
) -> tuple[list[InputRow], list[ParseFailure]]:
    return parse_split_inputs_with_errors(
        pid_text=identifier_text,
        video_url_text=video_url_text,
        upload_file_name=upload_name,
        upload_bytes=upload_bytes,
    )


def _parse_attachment_inputs(
    identifier_text: str,
    video_url_text: str,
    upload_name: str | None,
    upload_bytes: bytes | None,
) -> tuple[list[InputRow], list[ParseFailure]]:
    return parse_attachment_inputs_with_errors(
        item_id_text=identifier_text,
        video_url_text=video_url_text,
        upload_file_name=upload_name,
        upload_bytes=upload_bytes,
    )


def _build_splice_preview(
    identifier_text: str,
    video_url_text: str,
    upload_name: str | None,
    upload_bytes: bytes | None,
) -> InputPreview:
    return build_split_input_preview(
        pid_text=identifier_text,
        video_url_text=video_url_text,
        upload_file_name=upload_name,
        upload_bytes=upload_bytes,
    )


def _build_attachment_preview(
    identifier_text: str,
    video_url_text: str,
    upload_name: str | None,
    upload_bytes: bytes | None,
) -> InputPreview:
    return build_attachment_input_preview(
        item_id_text=identifier_text,
        video_url_text=video_url_text,
        upload_file_name=upload_name,
        upload_bytes=upload_bytes,
    )


def _render_splice_page(config: Config) -> None:
    _render_processing_page(
        prefix="sp_splice",
        page_title="视频拼接",
        identifier_label="pid",
        result_dir_prefix="splice",
        identifier_input_label="PID（每行一条）",
        identifier_placeholder="demo001\ndemo001\ndemo002",
        instruction_lines=[
            "- 左侧输入 `pid`，右侧输入 `video_url`，按行一一对应",
            "- 输入后可先点击“确认数据并预览”，查看总条数及前 5 条/后 5 条原始数据",
            "- 手动输入两列条数不一致，或存在非法链接时，会阻止开始处理",
            "- 仅支持公开 `http/https` 链接",
            "- 输出文件按输入顺序命名为 `1.mp4`、`2.mp4`、`3.mp4`...",
            "- 处理完成后会同步保存到本机下载目录下的独立结果文件夹，并支持直接打开结果目录",
        ],
        parser=_parse_splice_inputs,
        processor=process_batch,
        filename_assigner=assign_output_filenames,
        preview_builder=_build_splice_preview,
        runtime_errors=validate_splice_runtime(config),
        config_caption=_build_runtime_summary(config, include_endcard=True),
        config=config,
        header_renderer=_render_endcard_manager,
    )


def _render_attachment_page(config: Config) -> None:
    _render_processing_page(
        prefix="sp_attachment",
        page_title="视频链接转附件",
        identifier_label="item_id",
        result_dir_prefix="attachment",
        identifier_input_label="Item ID（每行一条）",
        identifier_placeholder="item001\nitem001\nitem002",
        instruction_lines=[
            "- 左侧输入 `item_id`，右侧输入 `video_url`，按行一一对应",
            "- 输入后可先点击“确认数据并预览”，查看总条数及前 5 条/后 5 条原始数据",
            "- 手动输入两列条数不一致，或存在非法链接时，会阻止开始处理",
            "- 输出文件固定为 `item_id.mp4`，重复 `item_id` 自动追加 `__2`、`__3` 后缀",
            "- 下载能力取决于运行当前应用机器的网络环境；如目标链接需 VPN，则运行机器也必须可访问",
            "- 处理完成后会同步保存到本机下载目录下的独立结果文件夹，并支持直接打开结果目录",
        ],
        parser=_parse_attachment_inputs,
        processor=process_attachment_batch,
        filename_assigner=assign_attachment_output_filenames,
        preview_builder=_build_attachment_preview,
        runtime_errors=validate_attachment_runtime(),
        config_caption=_build_runtime_summary(config, output_label="输出格式 MP4"),
        config=config,
        header_renderer=None,
    )


st.set_page_config(page_title="视频拼接工具", layout="wide")

base_config = load_config()

with st.sidebar:
    selected_page = st.radio("功能页", [PAGE_SPLICE, PAGE_ATTACHMENT], label_visibility="visible")
    config = _render_runtime_settings(base_config)

if selected_page == PAGE_SPLICE:
    _render_splice_page(config)
else:
    _render_attachment_page(config)
