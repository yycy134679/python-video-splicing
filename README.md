<p align="center">
  <img src="assets/logo.png" alt="视频拼接工具 Logo" width="120" />
</p>

<h1 align="center">Python 视频工具</h1>

<p align="center">基于 Streamlit + FFmpeg 的批量视频处理工具，聚焦 macOS 场景。</p>

当前提供两个功能页：

- **视频拼接**：下载源视频后自动拼接落版片尾，输出 MP4
- **视频链接转附件**：批量下载公开视频链接，并规范化输出为以 `item_id` 命名的 MP4 附件

这个项目的目标很直接：让业务同学在网页里粘贴数据、预览校验、批量处理，再一键下载或打开本地结果目录，不需要关心 FFmpeg 命令和中间文件。

## 功能概览

- **双页面工作流**：同一应用内切换“视频拼接”和“视频链接转附件”
- **先预览后处理**：必须先点击“确认数据并预览”，校验通过后才能开始处理
- **支持文本 / CSV / Excel**：两页都支持双列文本输入，也支持 `.csv`、`.xlsx`、`.xlsm`
- **文本优先级更高**：只要任一文本框存在非空行，就会忽略上传文件
- **批量并发执行**：支持多条任务同时下载和处理，并实时展示日志与进度
- **结果自动打包**：单条成功时直接下载 MP4，多条结果下载 ZIP，并附带 `result.csv`
- **结果自动落地**：每次处理都会保存到 `~/Downloads/video-splicer-results/` 下的独立目录
- **附件统一输出 MP4**：优先无损封装，失败时自动回退到 H.264/AAC 转码
- **拼接链路更稳**：会探测码率、补齐缺失音轨，并将落版视频缩放到源视频分辨率
- **支持打开结果目录**：处理完成后可直接从页面打开本地结果文件夹
- **网页内可调参数**：支持修改单条视频大小上限、并发数、单任务超时和下载重试次数

## 适用场景

- 批量给商品视频统一拼接落版片尾
- 批量把公开视频链接整理成可交付的 MP4 附件
- 需要非技术同学在浏览器里完成批量视频处理
- 需要在本机保留结果归档、失败明细和导出记录

## 快速开始

### 1. 准备环境

- 克隆仓库并进入目录
- macOS
- Python 3.11+
- `ffmpeg` / `ffprobe`
- 项目虚拟环境 `.venv`

```bash
git clone https://github.com/yycy134679/python-video-splicing.git
cd python-video-splicing
```

安装 FFmpeg：

```bash
brew install ffmpeg
```

创建虚拟环境并安装依赖：

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

如果你使用 fish shell，可以改用：

```fish
source .venv/bin/activate.fish
```

### 2. 配置落版视频

> [!IMPORTANT]
> 当前仓库中未包含 `assets/video/endcard.mp4`。如果你要使用“视频拼接”页面，必须先准备落版视频，并通过环境变量显式指定路径；如果只使用“视频链接转附件”，则不需要落版视频。

示例：

```bash
export SP_ENDCARD_PATH="/绝对路径/endcard.mp4"
```

### 3. 启动应用

```bash
streamlit run app.py
```

默认访问地址为 [http://localhost:8501](http://localhost:8501)。

## 使用说明

### 视频拼接

- 左侧输入 `pid`，右侧输入 `video_url`，按行一一对应
- 支持文本输入，或上传带有 `pid,video_url` 表头的 CSV
- Excel 需包含 `商品id`、`视频链接` 两列
- 仅支持公开的 `http/https` 视频链接
- 输出文件按输入顺序命名为 `1.mp4`、`2.mp4`、`3.mp4`...
- 拼接前会校验运行环境，包括 `ffmpeg`、`ffprobe` 和落版视频路径

### 视频链接转附件

- 左侧输入 `item_id`，右侧输入 `video_url`，按行一一对应
- 支持文本输入，或上传带有 `item_id,video_url` 表头的 CSV
- 同时兼容旧格式 CSV：`pid,video_url`
- Excel 同样读取 `商品id`、`视频链接`
- 输出文件固定为 `item_id.mp4`
- 当 `item_id` 重复时，自动追加 `__2`、`__3` 等后缀避免覆盖
- 该页面不依赖落版视频，只要求运行机器本身能访问目标链接

### 预览与校验规则

- 未点击“确认数据并预览”前，“开始处理”按钮不可点击
- 文本框中间的空行会被自动忽略，再按非空行进行配对
- 两列行数不一致时会直接阻止处理
- 文件缺少必需表头或列名时，页面仍会先展示原始数据预览，并提示修正
- Excel 中视频链接为空的行会在正式处理时自动跳过
- 视频链接不合法、标识符为空时会在预览阶段直接拦截

### 导出与落盘规则

- 单条成功结果：直接下载对应的 `.mp4`
- 单条失败结果：下载 `result.csv`
- 多条结果：下载 `results-时间戳.zip`
- ZIP 内只包含成功产出的 MP4 和 `result.csv`
- 本地结果目录默认保存到 `~/Downloads/video-splicer-results/`
- 每次处理都会生成独立目录，例如 `splice-20260318-120000/`、`attachment-20260318-120000/`

## 处理参数

侧边栏提供四个运行时参数，修改后仅影响当前网页里后续发起的任务：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `单条视频大小上限` | `50 MB` | 超过后直接拦截，避免误下载超大文件 |
| `同时处理数量` | `4` | 并行任务数，越大越快，也越占用本机资源 |
| `单条任务最长等待时间` | `180 秒` | 从下载到处理完成的总超时 |
| `下载失败自动重试次数` | `2` | 下载偶发失败时的自动重试次数 |

## 环境变量

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SP_ENDCARD_PATH` | 本地开发路径（不建议依赖） | 拼接页使用的落版视频路径，源码运行时建议显式设置 |
| `SP_RESULTS_ROOT_DIR` | `~/Downloads/video-splicer-results` | 本地结果保存根目录 |
| `SP_MAX_VIDEO_MB` | `50` | 单条源视频最大体积（MB） |
| `SP_MAX_WORKERS` | `4` | 最大并发线程数 |
| `SP_TASK_TIMEOUT_SEC` | `180` | 单任务超时时间（秒） |
| `SP_DOWNLOAD_RETRIES` | `2` | 下载最大重试次数 |
| `SP_APP_PORT` | `8501` | 通过 `launcher.py` 启动时使用的端口 |

## 技术实现

### 视频拼接链路

1. 下载源视频
2. 使用 `ffprobe` 探测分辨率、时长、码率和音轨信息
3. 当源视频无音轨时自动补静音轨
4. 将落版视频缩放并补边到与源视频一致的分辨率
5. 使用 `ffmpeg` 拼接为最终 MP4

### 附件生成链路

1. 下载源视频
2. 优先尝试直接封装为 MP4
3. 若封装失败，则回退为 H.264/AAC 转码
4. 输出统一为可交付的 `.mp4`

## macOS 打包

项目包含完整的 macOS 打包脚本，会先用 PyInstaller 生成 `COLLECT` 产物，再手动组装 `.app`，避免中文应用名和图标处理不稳定的问题。

执行打包：

```bash
bash build_macos_app.sh
```

默认产物：

- `dist/视频拼接工具.app`
- `dist/视频拼接工具-v2.1.zip`

如需额外生成 DMG：

```bash
BUILD_DMG=1 bash build_macos_app.sh
```

> [!NOTE]
> 打包脚本要求在 `.venv` 中执行，并且本机已安装 Homebrew 版 `ffmpeg` / `ffprobe`。打包后的 `.app` 会携带运行所需依赖，交付同事后通常无需再安装 Python 或 FFmpeg。

## 运行测试

请在虚拟环境中执行：

```bash
pytest
```

当前测试覆盖的重点包括：

- 输入解析与校验
- 附件命名与重名处理
- 结果打包与落盘策略
- 运行时配置覆盖
- `launcher.py` 的单实例与端口复用逻辑

## 项目结构

```text
.
├── app.py
├── launcher.py
├── build_macos_app.sh
├── video_splicing.spec
├── requirements.txt
├── assets/
│   └── logo.png
├── video_splicer/
│   ├── artifact.py
│   ├── config.py
│   ├── downloader.py
│   ├── ffmpeg_pipeline.py
│   ├── input_parser.py
│   ├── models.py
│   └── runner.py
└── tests/
```

## 开发说明

- 文档和注释默认使用简体中文
- 新依赖、打包流程或核心交互有变化时，应同步更新本 README
- 如果改动影响业务逻辑、公共接口、数据结构或构建过程，优先在工作分支完成开发后再合并
