# 项目指南 — Python 视频拼接工具

## 代码风格

- **Python 3.11+**，每个模块首行 `from __future__ import annotations`
- 函数签名 **100% 类型注解**，使用 `X | None` 而非 `Optional[X]`，`list[str]` 而非 `List[str]`
- 类型别名用 `PascalCase`：`Status = Literal["SUCCESS", "FAILED"]`，`LogCallback = Callable[[str], None]`
- 私有函数用单下划线前缀：`_parse_text_rows()`、`_select_video_bitrate()`
- **不写 docstring**，用行内中文注释 (`#`) 解释关键业务决策
- 面向用户的所有文案（错误信息、UI 文本）使用**简体中文**
- 使用 `# noqa: BLE001` 抑制 `except Exception` 的 lint 警告（ruff/flake8）
- Import 分组：`__future__` → 标准库 → 第三方 → 本地模块（包内用相对导入 `from .models import Config`）

## 架构

核心数据流：用户输入 → `input_parser` 解析为 `InputRow` → `runner.process_batch()` 并发下载+拼接 → `TaskResult` → `artifact` 打包输出。

```
app.py                          # Streamlit UI 入口，绝对导入
├── video_splicer/config.py     # 环境变量(SP_前缀)→ frozen Config dataclass
├── video_splicer/input_parser.py  # 文本框/CSV/Excel → InputRow + ParseFailure
├── video_splicer/runner.py     # ThreadPoolExecutor 并发调度，回调解耦 UI
│   ├── downloader.py           # HTTP 流式下载，重试+超时+大小限制
│   └── ffmpeg_pipeline.py      # FFprobe 探测 → FFmpeg filter_complex 拼接
└── video_splicer/artifact.py   # 结果打包：单成功→MP4，单失败→CSV，多条→ZIP
```

**关键设计**：

- 所有 dataclass 除 `TaskResult` 外均为 `frozen=True`（不可变值对象）
- UI 与后端通过 `LogCallback` / `ProgressCallback` 回调类型解耦
- 自定义异常 `DownloadError` / `FFmpegError` 继承 `RuntimeError`，在 runner 层统一捕获转为 `TaskResult`
- 每个任务有独立超时预算，通过 `_remaining_seconds()` 贯穿下载和 FFmpeg 阶段
- 临时目录 `tempfile.mkdtemp(prefix="video_splice_")`，内含 `downloads/` 和 `outputs/`

## 构建与测试

```bash
# 安装依赖
pip install -r requirements.txt

# 启动应用
streamlit run app.py

# 运行测试（pytest.ini 设置 pythonpath = .）
pytest

# macOS 打包
bash build_macos_app.sh
```

## 项目约定

- **双输入优先级**：文本框有内容时忽略上传文件（参考 [input_parser.py](video_splicer/input_parser.py) `parse_split_inputs_with_errors()`）
- **PID 去重命名**：重复 PID 用双下划线后缀 `pid__2.mp4`、`pid__3.mp4`（参考 `assign_output_filenames()`）
- **"落版视频"（endcard）**：固定片尾拼接到每条源视频后，自动匹配分辨率（scale+pad）、音频格式（48kHz stereo），缺音轨补静音
- **配置全部通过环境变量**，前缀 `SP_`，辅助函数 `_read_positive_int()` 做安全解析

## 测试约定

- **纯函数/纯数据测试**，不使用 mock，不涉及 I/O
- 仅使用 pytest 内建 fixture（`tmp_path`），无 `conftest.py`
- 测试命名：`test_<被测行为的自然语言描述>()`，如 `test_text_input_has_priority_over_csv`
- 用工厂函数快速构造测试数据（参考 [test_bitrate_policy.py](tests/test_bitrate_policy.py) 中的 `_probe()`）
- 所有测试函数带 `-> None` 返回类型注解

## 集成要点

- **FFmpeg/FFprobe** 为外部系统依赖，macOS 下 `brew install ffmpeg`
- HTTP 下载使用 `requests`，支持流式传输、重试、超时控制
- PyInstaller 打包入口为 [launcher.py](launcher.py)，通过 `sys.frozen` / `sys._MEIPASS` 检测打包环境
- Streamlit session state 键：`sp_results`、`sp_logs`、`sp_download`
