from __future__ import annotations

import shutil
from datetime import datetime
from typing import Callable

import pandas as pd
import streamlit as st

from video_splicer.artifact import build_download_artifact, collect_work_dirs
from video_splicer.config import (
    build_runtime_config,
    load_config,
    validate_attachment_runtime,
    validate_splice_runtime,
)
from video_splicer.input_parser import (
    assign_attachment_output_filenames,
    assign_output_filenames,
    parse_attachment_inputs_with_errors,
    parse_split_inputs_with_errors,
)
from video_splicer.models import Config, InputRow, ParseFailure, TaskResult
from video_splicer.runner import process_attachment_batch, process_batch

APP_VERSION = "2.0"
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


def _failure_to_result(failure: ParseFailure) -> TaskResult:
    return TaskResult(
        index=failure.index,
        pid=failure.pid_raw,
        output_filename="",
        status="FAILED",
        error=failure.error,
        duration_sec=0.0,
        output_path=None,
    )


def _state_key(prefix: str, suffix: str) -> str:
    return f"{prefix}_{suffix}"


def _ensure_page_state(prefix: str) -> None:
    for suffix, default_value in (
        ("results", None),
        ("logs", []),
        ("download", None),
    ):
        key = _state_key(prefix, suffix)
        if key not in st.session_state:
            st.session_state[key] = default_value


def _reset_page_state(prefix: str) -> None:
    st.session_state[_state_key(prefix, "results")] = None
    st.session_state[_state_key(prefix, "logs")] = []
    st.session_state[_state_key(prefix, "download")] = None


def _render_results(prefix: str, identifier_label: str) -> None:
    results: list[TaskResult] | None = st.session_state.get(_state_key(prefix, "results"))
    if results is None:
        return

    logs: list[str] = st.session_state.get(_state_key(prefix, "logs"), [])
    download_obj: dict[str, bytes | str] | None = st.session_state.get(_state_key(prefix, "download"))

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
    uploaded_file: object,
    parser: PageParser,
    processor: PageProcessor,
    filename_assigner: FilenameAssigner,
    runtime_errors: list[str],
    identifier_label: str,
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

    upload_bytes = uploaded_file.getvalue() if uploaded_file else None
    upload_name = uploaded_file.name if uploaded_file else None
    rows, parse_failures = parser(identifier_text, video_url_text, upload_name, upload_bytes)

    if not rows and not parse_failures:
        st.warning("请输入至少一条有效数据。")
        return

    failure_results = [_failure_to_result(item) for item in parse_failures]

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
            processed_results = processor(
                rows=rows,
                config=config,
                log_cb=log_cb,
                progress_cb=progress_cb,
            )
    else:
        progress_cb(1, 1)

    all_results = sorted(failure_results + processed_results, key=lambda item: item.index)
    mime, file_name, payload = build_download_artifact(all_results, identifier_label=identifier_label)

    for work_dir in collect_work_dirs(processed_results):
        shutil.rmtree(work_dir, ignore_errors=True)

    st.session_state[_state_key(prefix, "results")] = all_results
    st.session_state[_state_key(prefix, "logs")] = logs
    st.session_state[_state_key(prefix, "download")] = {
        "mime": mime,
        "file_name": file_name,
        "data": payload,
    }


def _render_processing_page(
    prefix: str,
    page_title: str,
    identifier_label: str,
    identifier_input_label: str,
    identifier_placeholder: str,
    upload_label: str,
    instruction_lines: list[str],
    parser: PageParser,
    processor: PageProcessor,
    filename_assigner: FilenameAssigner,
    runtime_errors: list[str],
    config_caption: str,
    config: Config,
) -> None:
    _ensure_page_state(prefix)

    st.subheader(page_title)
    st.caption(config_caption)
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

    uploaded_file = st.file_uploader(
        upload_label,
        type=["csv", "xlsx", "xlsm"],
        key=_state_key(prefix, "uploaded_file"),
    )

    start_clicked = st.button("开始处理", type="primary", key=_state_key(prefix, "start"))
    if start_clicked:
        _process_page_request(
            prefix=prefix,
            identifier_text=identifier_text,
            video_url_text=video_url_text,
            uploaded_file=uploaded_file,
            parser=parser,
            processor=processor,
            filename_assigner=filename_assigner,
            runtime_errors=runtime_errors,
            identifier_label=identifier_label,
            config=config,
        )

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


def _render_splice_page(config: Config) -> None:
    _render_processing_page(
        prefix="sp_splice",
        page_title="视频拼接",
        identifier_label="pid",
        identifier_input_label="PID（每行一条）",
        identifier_placeholder="demo001\ndemo001\ndemo002",
        upload_label="可选文件上传（CSV: pid,video_url；Excel: 商品id,视频链接）",
        instruction_lines=[
            "- 左侧输入 `pid`，右侧输入 `video_url`，按行一一对应",
            "- 任一文本框存在非空行时，会忽略上传文件",
            "- 上传 Excel 时自动读取列：`商品id`、`视频链接`（空链接行自动忽略）",
            "- 仅支持公开 `http/https` 链接",
            "- 输出文件按输入顺序命名为 `1.mp4`、`2.mp4`、`3.mp4`...",
        ],
        parser=_parse_splice_inputs,
        processor=process_batch,
        filename_assigner=assign_output_filenames,
        runtime_errors=validate_splice_runtime(config),
        config_caption=_build_runtime_summary(config, include_endcard=True),
        config=config,
    )


def _render_attachment_page(config: Config) -> None:
    _render_processing_page(
        prefix="sp_attachment",
        page_title="视频链接转附件",
        identifier_label="item_id",
        identifier_input_label="Item ID（每行一条）",
        identifier_placeholder="item001\nitem001\nitem002",
        upload_label="可选文件上传（CSV: item_id,video_url；兼容 pid,video_url；Excel: 商品id,视频链接）",
        instruction_lines=[
            "- 左侧输入 `item_id`，右侧输入 `video_url`，按行一一对应",
            "- 任一文本框存在非空行时，会忽略上传文件",
            "- 上传 CSV 时支持列：`item_id`、`video_url`，也兼容旧格式 `pid`、`video_url`",
            "- 上传 Excel 时自动读取列：`商品id`、`视频链接`（空链接行自动忽略）",
            "- 输出文件固定为 `item_id.mp4`，重复 `item_id` 自动追加 `__2`、`__3` 后缀",
            "- 下载能力取决于运行当前应用机器的网络环境；如目标链接需 VPN，则运行机器也必须可访问",
        ],
        parser=_parse_attachment_inputs,
        processor=process_attachment_batch,
        filename_assigner=assign_attachment_output_filenames,
        runtime_errors=validate_attachment_runtime(),
        config_caption=_build_runtime_summary(config, output_label="输出格式 MP4"),
        config=config,
    )


st.set_page_config(page_title=f"视频拼接工具 v{APP_VERSION}", layout="wide")
st.title(f"Python + Streamlit 视频工具 v{APP_VERSION}")

base_config = load_config()

with st.sidebar:
    st.caption(f"App Version {APP_VERSION}")
    selected_page = st.radio("功能页", [PAGE_SPLICE, PAGE_ATTACHMENT], label_visibility="visible")
    config = _render_runtime_settings(base_config)

if selected_page == PAGE_SPLICE:
    _render_splice_page(config)
else:
    _render_attachment_page(config)
