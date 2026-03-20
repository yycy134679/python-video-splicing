# 落版视频上传与持久化 Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让“视频拼接”页支持上传、持久化、预览和重新上传单一当前生效的落版视频，并在页面刷新与应用重启后继续生效。

**Architecture:** 新增一个受管落版存储模块，统一负责当前落版查找、元数据读取、上传校验和原子覆盖；`video_splicer.config` 只负责把 `Config.endcard_path` 解析为“受管落版优先、默认 `assets/video/endcard.mp4` 兜底”。`app.py` 仅在拼接页顶部新增“落版视频管理”区，调用存储模块展示当前文件信息、视频预览和上传结果。

**Tech Stack:** Python 3.11、Streamlit、FFmpeg/FFprobe、`pathlib`、`tempfile`、`pytest`

---

## 前置约束

- 实现前先从最新 `main` 创建隔离工作区，不要直接在当前 `main` 上写功能代码。
- 全程在 `.venv` 中安装依赖、运行测试和启动应用。
- 保持 KISS/YAGNI：首版只支持单一当前版本，不做历史版本、切换回滚、多用户隔离。
- 除非实现被现有代码阻塞，否则不要改 `video_splicer/runner.py`、`video_splicer/ffmpeg_pipeline.py`、`build_macos_app.sh`。
- UI 自动化测试当前不是仓库既有模式。本次以“存储层/配置层自动化测试 + Streamlit 手动冒烟”作为最小可靠验证组合。

## 参考文档

- Spec: `docs/superpowers/specs/2026-03-20-endcard-upload-design.md`

## 文件结构与职责

- Create: `video_splicer/endcard_store.py`
  负责受管落版目录定位、当前文件查找、元数据封装、上传校验、临时文件写入和原子替换。
- Modify: `video_splicer/config.py:11-38`
  将 `Config.endcard_path` 的来源改为“受管落版优先，默认落版兜底”。
- Modify: `app.py:1-40`
  增加 `endcard_store` 相关导入。
- Modify: `app.py:639-665`
  在拼接页渲染前插入“落版视频管理”区，接入当前文件信息、预览、上传与反馈。
- Create: `tests/test_endcard_store.py`
  覆盖落版发现、元数据、上传格式校验、探测失败保护、覆盖替换等核心行为。
- Modify: `tests/test_config_runtime.py:1-48`
  增加 `load_config()` 对“受管落版优先/默认落版兜底”的断言。
- Modify: `README.md`
  更新功能特性、项目结构、拼接页使用方式和重大说明。

## 工作区准备

- [ ] **Step 1: 创建隔离 worktree 和功能分支**

```bash
git fetch origin
git worktree add ../python-video-splicing-endcard-upload -b feature/落版视频上传 origin/main
cd ../python-video-splicing-endcard-upload
```

Expected: 新目录创建成功，分支名为 `feature/落版视频上传`。

- [ ] **Step 2: 准备虚拟环境**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Expected: `.venv` 可用，依赖安装成功。

- [ ] **Step 3: 运行基线测试**

```bash
source .venv/bin/activate
pytest tests/test_config_runtime.py -v
```

Expected: 现有配置测试全部通过，作为后续回归基线。

### Task 1: 建立当前落版解析与元数据模型

**Files:**
- Create: `video_splicer/endcard_store.py`
- Modify: `video_splicer/config.py:11-38`
- Test: `tests/test_endcard_store.py`
- Test: `tests/test_config_runtime.py:1-48`

- [ ] **Step 1: 在 `tests/test_endcard_store.py` 写失败测试，覆盖“受管落版优先、默认落版兜底”**

```python
from pathlib import Path

from video_splicer.endcard_store import resolve_active_endcard


def test_resolve_active_endcard_prefers_managed_file(tmp_path: Path) -> None:
    default_endcard = tmp_path / "assets" / "video" / "endcard.mp4"
    managed_dir = tmp_path / "managed-endcard"
    managed_file = managed_dir / "current-endcard.mov"
    default_endcard.parent.mkdir(parents=True)
    managed_dir.mkdir(parents=True)
    default_endcard.write_bytes(b"default")
    managed_file.write_bytes(b"managed")

    asset = resolve_active_endcard(default_endcard=default_endcard, managed_dir=managed_dir)

    assert asset.path == managed_file
    assert asset.source == "MANAGED"


def test_resolve_active_endcard_falls_back_to_default_file(tmp_path: Path) -> None:
    default_endcard = tmp_path / "assets" / "video" / "endcard.mp4"
    default_endcard.parent.mkdir(parents=True)
    default_endcard.write_bytes(b"default")

    asset = resolve_active_endcard(default_endcard=default_endcard, managed_dir=tmp_path / "managed-endcard")

    assert asset.path == default_endcard
    assert asset.source == "DEFAULT"
```

- [ ] **Step 2: 在 `tests/test_config_runtime.py` 补失败测试，锁定 `load_config()` 行为**

```python
def test_load_config_prefers_managed_endcard(monkeypatch, tmp_path: Path) -> None:
    default_endcard = tmp_path / "assets" / "video" / "endcard.mp4"
    managed_dir = tmp_path / "managed-endcard"
    managed_file = managed_dir / "current-endcard.mp4"
    default_endcard.parent.mkdir(parents=True)
    managed_dir.mkdir(parents=True)
    default_endcard.write_bytes(b"default")
    managed_file.write_bytes(b"managed")

    monkeypatch.setattr("video_splicer.config.DEFAULT_ENDCARD_PATH", default_endcard)
    monkeypatch.setattr("video_splicer.endcard_store.DEFAULT_MANAGED_ENDCARD_DIR", managed_dir)

    config = load_config()

    assert config.endcard_path == managed_file
```

- [ ] **Step 3: 运行测试，确认它们先失败**

Run:

```bash
source .venv/bin/activate
pytest tests/test_endcard_store.py tests/test_config_runtime.py -v
```

Expected: 因 `video_splicer.endcard_store` 不存在，或 `load_config()` 仍返回默认路径而失败。

- [ ] **Step 4: 在 `video_splicer/endcard_store.py` 写最小实现**

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


EndcardSource = Literal["DEFAULT", "MANAGED"]
DEFAULT_MANAGED_ENDCARD_DIR = Path.home() / ".video-splicer" / "endcard"


@dataclass(frozen=True)
class EndcardAsset:
    path: Path
    source: EndcardSource
    file_name: str
    suffix: str
    size_bytes: int
    mime_type: str


def resolve_active_endcard(default_endcard: Path, managed_dir: Path = DEFAULT_MANAGED_ENDCARD_DIR) -> EndcardAsset:
    managed_file = find_managed_endcard(managed_dir)
    active_path = managed_file if managed_file is not None else default_endcard
    source: EndcardSource = "MANAGED" if managed_file is not None else "DEFAULT"
    return build_endcard_asset(active_path, source=source)
```

实现要求：

- `find_managed_endcard()` 仅接受 `current-endcard.mp4` / `current-endcard.mov`。
- `build_endcard_asset()` 统一计算文件名、扩展名、大小和 MIME（`mp4 -> video/mp4`，`mov -> video/quicktime`）。
- 如果默认文件不存在，也应返回一个指向默认路径的 `EndcardAsset`，由现有运行时校验负责报错。

- [ ] **Step 5: 修改 `video_splicer/config.py` 接入新解析逻辑**

```python
from .endcard_store import resolve_active_endcard


def load_config() -> Config:
    endcard_asset = resolve_active_endcard(default_endcard=Path(os.getenv("SP_ENDCARD_PATH", str(DEFAULT_ENDCARD_PATH))).expanduser())
    results_root_dir = Path(os.getenv("SP_RESULTS_ROOT_DIR", str(DEFAULT_RESULTS_ROOT_DIR))).expanduser()
    return Config(
        endcard_path=endcard_asset.path,
        results_root_dir=results_root_dir,
        max_video_mb=_read_positive_int("SP_MAX_VIDEO_MB", 50),
        max_workers=_read_positive_int("SP_MAX_WORKERS", 4),
        task_timeout_sec=_read_positive_int("SP_TASK_TIMEOUT_SEC", 180),
        download_retries=_read_positive_int("SP_DOWNLOAD_RETRIES", 2),
    )
```

- [ ] **Step 6: 重新运行测试，确认解析逻辑通过**

Run:

```bash
source .venv/bin/activate
pytest tests/test_endcard_store.py tests/test_config_runtime.py -v
```

Expected: 新增测试通过，现有 `tests/test_config_runtime.py` 保持通过。

- [ ] **Step 7: 提交这一批最小可用改动**

```bash
git add tests/test_endcard_store.py tests/test_config_runtime.py video_splicer/endcard_store.py video_splicer/config.py
git commit -m "feat: 新增当前落版解析能力"
```

### Task 2: 实现安全上传、格式校验与覆盖替换

**Files:**
- Modify: `video_splicer/endcard_store.py`
- Test: `tests/test_endcard_store.py`

- [ ] **Step 1: 在 `tests/test_endcard_store.py` 写失败测试，锁定上传校验与覆盖保护**

```python
import pytest

from video_splicer.endcard_store import EndcardUploadError, replace_endcard_upload


def test_replace_endcard_upload_overwrites_previous_file(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    old_file = managed_dir / "current-endcard.mp4"
    old_file.write_bytes(b"old")

    def fake_probe(video_path: Path) -> object:
        assert video_path.suffix == ".mov"
        return object()

    asset = replace_endcard_upload(
        upload_name="fresh.mov",
        upload_bytes=b"new-content",
        managed_dir=managed_dir,
        probe_video_fn=fake_probe,
    )

    assert asset.path == managed_dir / "current-endcard.mov"
    assert asset.path.read_bytes() == b"new-content"
    assert not old_file.exists()


def test_replace_endcard_upload_rejects_invalid_extension_without_touching_current_file(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    current_file = managed_dir / "current-endcard.mp4"
    current_file.write_bytes(b"current")

    with pytest.raises(EndcardUploadError, match="仅支持上传 mp4 或 mov"):
        replace_endcard_upload(
            upload_name="fresh.avi",
            upload_bytes=b"bad",
            managed_dir=managed_dir,
            probe_video_fn=lambda _: object(),
        )

    assert current_file.read_bytes() == b"current"
```

- [ ] **Step 2: 再补一个“探测失败不覆盖旧文件”的失败测试**

```python
def test_replace_endcard_upload_keeps_previous_file_when_probe_fails(tmp_path: Path) -> None:
    managed_dir = tmp_path / "managed-endcard"
    managed_dir.mkdir(parents=True)
    current_file = managed_dir / "current-endcard.mp4"
    current_file.write_bytes(b"current")

    def broken_probe(_: Path) -> object:
        raise RuntimeError("boom")

    with pytest.raises(EndcardUploadError, match="无法识别该落版视频"):
        replace_endcard_upload(
            upload_name="fresh.mp4",
            upload_bytes=b"new",
            managed_dir=managed_dir,
            probe_video_fn=broken_probe,
        )

    assert current_file.read_bytes() == b"current"
```

- [ ] **Step 3: 运行测试，确认上传能力尚未实现**

Run:

```bash
source .venv/bin/activate
pytest tests/test_endcard_store.py -v
```

Expected: `replace_endcard_upload` / `EndcardUploadError` 不存在，或行为与断言不符而失败。

- [ ] **Step 4: 在 `video_splicer/endcard_store.py` 实现最小上传链路**

```python
from tempfile import NamedTemporaryFile


class EndcardUploadError(RuntimeError):
    pass


def replace_endcard_upload(
    upload_name: str,
    upload_bytes: bytes,
    managed_dir: Path = DEFAULT_MANAGED_ENDCARD_DIR,
    probe_video_fn: Callable[[Path], object] = probe_video,
) -> EndcardAsset:
    suffix = validate_endcard_extension(upload_name)
    managed_dir.mkdir(parents=True, exist_ok=True)
    temp_path = _write_temp_upload(managed_dir=managed_dir, suffix=suffix, upload_bytes=upload_bytes)

    try:
        probe_video_fn(temp_path)
        target_path = managed_dir / f"current-endcard{suffix}"
        _remove_existing_managed_files(managed_dir)
        temp_path.replace(target_path)
        return build_endcard_asset(target_path, source="MANAGED")
    except Exception as exc:  # noqa: BLE001
        temp_path.unlink(missing_ok=True)
        raise EndcardUploadError("无法识别该落版视频，请确认文件未损坏") from exc
```

实现要求：

- 空文件也要拒绝，错误文案单独写清楚。
- 先写临时文件，再探测，再覆盖当前文件；不要先删旧文件。
- 只有校验通过后，才删除旧的 `current-endcard.*`。
- `EndcardUploadError` 的文案应直接给 UI 使用，不需要 UI 再拼接技术细节。

- [ ] **Step 5: 运行测试，确认上传与覆盖逻辑通过**

Run:

```bash
source .venv/bin/activate
pytest tests/test_endcard_store.py -v
```

Expected: 新增上传测试全部通过。

- [ ] **Step 6: 提交上传能力**

```bash
git add tests/test_endcard_store.py video_splicer/endcard_store.py
git commit -m "feat: 新增落版上传与覆盖校验"
```

### Task 3: 在拼接页接入落版视频管理区

**Files:**
- Modify: `app.py:1-40`
- Modify: `app.py:639-665`
- Modify: `video_splicer/endcard_store.py`（仅当 UI 需要额外展示字段时）

- [ ] **Step 1: 在 `app.py` 增加落版管理所需导入和状态键**

```python
from video_splicer.endcard_store import EndcardUploadError, replace_endcard_upload, resolve_active_endcard


def _ensure_endcard_state() -> None:
    if "sp_endcard_feedback" not in st.session_state:
        st.session_state["sp_endcard_feedback"] = ""
    if "sp_endcard_error" not in st.session_state:
        st.session_state["sp_endcard_error"] = ""
```

- [ ] **Step 2: 新增 `_render_endcard_manager()`，只负责渲染拼接页顶部区块**

```python
def _render_endcard_manager() -> None:
    _ensure_endcard_state()
    default_endcard_path = Path(os.getenv("SP_ENDCARD_PATH", str(DEFAULT_ENDCARD_PATH))).expanduser()
    asset = resolve_active_endcard(default_endcard=default_endcard_path)
    st.subheader("落版视频管理")
    st.caption("上传成功后会立即影响后续新发起的拼接任务，正在处理的批次不会切换。")
    st.markdown(f"- 当前文件：`{asset.file_name}`")
    st.markdown(f"- 当前来源：{'已上传落版视频' if asset.source == 'MANAGED' else '默认落版视频'}")
    st.markdown(f"- 文件大小：`{asset.size_bytes}` bytes")
    st.video(str(asset.path), format=asset.mime_type)
```

实现要求：

- 将字节大小转换成更适合业务阅读的 MB/KB 文案，不要直接展示裸字节。
- 上传控件仅允许 `type=["mp4", "mov"]`。
- 上传成功后调用 `st.success()` 并 `st.rerun()`，确保页面重新读取 `load_config()`。
- 上传失败时展示 `EndcardUploadError` 文案，并继续显示旧落版信息和预览。

- [ ] **Step 3: 在 `_render_splice_page()` 调用新管理区，再进入原有处理页**

```python
def _render_splice_page(config: Config) -> None:
    _render_endcard_manager()
    _render_processing_page(
        prefix="sp_splice",
        ...
    )
```

注意：

- 不要改动附件页。
- 不要让落版上传状态污染现有拼接输入预览状态。
- 管理区读取默认落版路径时，必须与 `load_config()` 保持一致，不能写死另一个路径来源。

- [ ] **Step 4: 手动冒烟验证 UI**

Run:

```bash
source .venv/bin/activate
streamlit run app.py
```

Manual checks:

- 首次打开拼接页时，顶部能看到“当前使用默认落版视频”。
- 页面能预览当前默认落版。
- 上传一个合法 `mp4` 后，页面刷新并显示“已上传落版视频”。
- 重新上传一个合法 `mov` 后，预览切换到新文件。
- 上传失败时，旧落版仍可继续预览。
- 上传成功后再点击“开始处理”的新任务，会使用新落版。

- [ ] **Step 5: 提交 UI 接入**

```bash
git add app.py video_splicer/endcard_store.py
git commit -m "feat: 拼接页支持落版上传与预览"
```

### Task 4: 更新 README 并完成回归

**Files:**
- Modify: `README.md`
- Test: `tests/test_endcard_store.py`
- Test: `tests/test_config_runtime.py`

- [ ] **Step 1: 更新 `README.md` 的功能说明与项目结构**

至少覆盖以下内容：

- 功能特性中新增“拼接页支持上传/持久化/预览落版视频”。
- 项目结构中新增 `video_splicer/endcard_store.py`。
- “视频拼接页”使用方式中写明：
  - 顶部可上传 `mp4/mov` 落版视频。
  - 上传成功后立即对后续新任务生效。
  - 页面刷新和应用重启后仍保持生效。
  - 正在处理的批次不会中途切换新落版。

- [ ] **Step 2: 运行针对性回归**

Run:

```bash
source .venv/bin/activate
pytest tests/test_endcard_store.py tests/test_config_runtime.py -v
```

Expected: 新增受管落版相关测试全部通过。

- [ ] **Step 3: 运行完整测试集**

Run:

```bash
source .venv/bin/activate
pytest
```

Expected: 全量测试通过，无新增回归。

- [ ] **Step 4: 记录剩余风险并整理交付说明**

交付说明必须包含：

- 代码变更摘要（1-2 段）。
- 潜在风险：
  - 浏览器对某些 `mov` 编码的播放兼容性可能不一致。
  - 当前仅支持单一当前版本，不支持历史回退。
- 已执行测试列表：
  - `tests/test_endcard_store.py`
  - `tests/test_config_runtime.py`
  - `pytest`
  - `streamlit run app.py` 手动冒烟

- [ ] **Step 5: 提交文档与最终收口**

```bash
git add README.md tests/test_endcard_store.py tests/test_config_runtime.py video_splicer/endcard_store.py video_splicer/config.py app.py
git commit -m "chore: 完成落版视频上传功能回归"
```

## 完成定义

满足以下条件后，才可宣布该需求完成：

- 拼接页顶部可以看到“落版视频管理”区。
- 业务同学可以上传 `mp4` / `mov` 落版视频并立即生效。
- 当前生效落版在页面中可预览、可识别来源、可重复上传覆盖。
- 页面刷新和应用重启后仍能继续使用最近一次上传的落版。
- 上传非法文件或损坏文件时，旧落版不会被覆盖。
- `pytest` 全量通过，README 已同步更新。
