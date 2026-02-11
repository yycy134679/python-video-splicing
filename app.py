from __future__ import annotations

import shutil
from datetime import datetime

import pandas as pd
import streamlit as st

from video_splicer.artifact import build_download_artifact, collect_work_dirs
from video_splicer.config import load_config, validate_runtime
from video_splicer.input_parser import (
    assign_output_filenames,
    parse_split_inputs_with_errors,
)
from video_splicer.models import ParseFailure, TaskResult
from video_splicer.runner import process_batch


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


st.set_page_config(page_title="视频拼接工具", layout="wide")
st.title("Python + Streamlit 视频拼接工具")

config = load_config()

st.caption(
    "当前配置: "
    f"endcard={config.endcard_path} | "
    f"max_video_mb={config.max_video_mb} | "
    f"max_workers={config.max_workers} | "
    f"task_timeout_sec={config.task_timeout_sec} | "
    f"download_retries={config.download_retries}"
)

runtime_errors = validate_runtime(config)
if runtime_errors:
    st.error("运行前置检查未通过：\n- " + "\n- ".join(runtime_errors))

with st.expander("输入说明", expanded=False):
    st.markdown(
        "\n".join(
            [
                "- 左侧输入 `pid`，右侧输入 `video_url`，按行一一对应",
                "- 任一文本框存在非空行时，会忽略上传文件",
                "- 上传 Excel 时自动读取列：`商品id`、`视频链接`（空链接行自动忽略）",
                "- 仅支持公开 `http/https` 链接",
                "- 输出文件按输入顺序命名为 `1.mp4`、`2.mp4`、`3.mp4`...",
            ]
        )
    )

pid_col, url_col = st.columns(2)
with pid_col:
    pid_input = st.text_area(
        "PID（每行一条）",
        height=220,
        placeholder="demo001\ndemo001\ndemo002",
    )

with url_col:
    video_url_input = st.text_area(
        "视频链接（每行一条）",
        height=220,
        placeholder=(
            "https://example.com/video1.mp4\n"
            "https://example.com/video2.mp4\n"
            "https://example.com/video3.mp4"
        ),
    )

uploaded_file = st.file_uploader(
    "可选文件上传（CSV: pid,video_url；Excel: 商品id,视频链接）",
    type=["csv", "xlsx", "xlsm"],
)

if "sp_results" not in st.session_state:
    st.session_state["sp_results"] = None
if "sp_logs" not in st.session_state:
    st.session_state["sp_logs"] = []
if "sp_download" not in st.session_state:
    st.session_state["sp_download"] = None


start_clicked = st.button("开始处理", type="primary")

if start_clicked:
    st.session_state["sp_results"] = None
    st.session_state["sp_logs"] = []
    st.session_state["sp_download"] = None

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
    rows, parse_failures = parse_split_inputs_with_errors(
        pid_text=pid_input,
        video_url_text=video_url_input,
        upload_file_name=upload_name,
        upload_bytes=upload_bytes,
    )

    if not rows and not parse_failures:
        st.warning("请输入至少一条有效数据。")
    else:
        failure_results = [_failure_to_result(item) for item in parse_failures]

        processed_results: list[TaskResult] = []
        if rows:
            if runtime_errors:
                file_map = assign_output_filenames(rows)
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
                processed_results = process_batch(
                    rows=rows,
                    config=config,
                    log_cb=log_cb,
                    progress_cb=progress_cb,
                )
        else:
            progress_cb(1, 1)

        all_results = sorted(failure_results + processed_results, key=lambda item: item.index)
        mime, file_name, payload = build_download_artifact(all_results)

        for work_dir in collect_work_dirs(processed_results):
            shutil.rmtree(work_dir, ignore_errors=True)

        st.session_state["sp_results"] = all_results
        st.session_state["sp_logs"] = logs
        st.session_state["sp_download"] = {
            "mime": mime,
            "file_name": file_name,
            "data": payload,
        }

if st.session_state.get("sp_results") is not None:
    results: list[TaskResult] = st.session_state["sp_results"]
    logs = st.session_state.get("sp_logs", [])
    download_obj = st.session_state.get("sp_download")

    st.subheader("结果表")
    table_rows = [
        {
            "pid": item.pid,
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
            file_name=download_obj["file_name"],
            mime=download_obj["mime"],
        )
