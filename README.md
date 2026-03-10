# Python 视频工具

基于 **Streamlit + FFmpeg** 的批量视频处理工具，当前包含两个功能页：
- **视频拼接**：将源视频与落版片尾（endcard）拼接后输出 MP4
- **视频链接转附件**：批量下载视频链接并规范化输出为以 `item_id` 命名的 MP4 附件

## 功能特性

- **双功能页**：同一应用内可切换“视频拼接”和“视频链接转附件”
- **多种输入方式**：两页都支持双列文本输入，也支持 Excel（`.xlsx`/`.xlsm`）和 CSV
- **确认预览**：支持先确认数据，再查看总条数与前 5 条 / 后 5 条原始数据预览，视频链接可直接点击打开
- **先预览后处理**：未点击“确认数据并预览”前，“开始处理”按钮保持灰色不可点击
- **批量并发处理**：支持多条任务并发下载，带实时进度与日志
- **拼接链路稳定**：自动探测码率、适配分辨率、补齐缺失音轨
- **附件统一输出 MP4**：优先无损封装为 MP4，失败时回退 H.264/AAC 转码
- **页面级命名规则**：拼接页输出 `1.mp4`、`2.mp4`；附件页输出 `item_id.mp4`，重复值自动追加 `__2`
- **一键下载**：单条成功直接下载 MP4，多条结果打包为 ZIP，并附带 `result.csv`
- **结果自动落地保存**：每次处理都会同步保存到 `~/Downloads/video-splicer-results/` 下的独立结果文件夹
- **打开结果目录**：处理完成后页面会显示本地保存路径，并支持一键打开结果目录
- **VPN 场景兼容**：只要运行应用的机器本身能访问目标链接，附件页即可下载处理
- **网页可调处理参数**：支持在侧边栏直接调整视频大小上限、并发数、超时时间和下载重试次数，并附中文说明

## 项目结构

```text
├── app.py                   # Streamlit 主入口（双功能页）
├── requirements.txt         # Python 依赖
├── pytest.ini               # 测试配置
├── assets/video/            # 落版片尾视频（endcard.mp4）
├── video_splicer/           # 核心模块
│   ├── models.py            #   数据模型（Config / InputRow / TaskResult）
│   ├── config.py            #   配置加载 & 运行环境校验
│   ├── input_parser.py      #   输入解析（文本 / CSV / Excel）
│   ├── downloader.py        #   视频下载（支持重试 & 超时 & 大小限制）
│   ├── ffmpeg_pipeline.py   #   FFmpeg 探测 / 拼接 / MP4 规范化
│   ├── runner.py            #   批量并发调度（拼接 / 转附件）
│   └── artifact.py          #   结果打包与本地落地保存
└── tests/                   # 单元测试
    ├── test_attachment_artifact.py
    ├── test_attachment_input_parser.py
    ├── test_attachment_naming.py
    ├── test_artifact_decision.py
    ├── test_bitrate_policy.py
    ├── test_config_runtime.py
    ├── test_input_parser.py
    ├── test_naming.py
    ├── test_result_csv.py
    └── test_saved_result_directory.py
```

## 前置依赖

| 依赖 | 说明 |
| --- | --- |
| **Python 3.11+** | 运行环境 |
| **FFmpeg / FFprobe** | 视频探测、拼接与 MP4 规范化 |

安装 FFmpeg（macOS）：

```bash
brew install ffmpeg
```

## 快速开始

```bash
# 1. 克隆项目
git clone https://github.com/yycy134679/python-video-splicing.git
cd python-video-splicing

# 2. 创建虚拟环境并安装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. 启动应用
streamlit run app.py
```

浏览器访问 `http://localhost:8501` 即可使用。应用标题会显示 `v2.1`，侧边栏可切换两个功能页。

侧边栏还提供“处理参数设置”，业务同学可以直接修改：
- `单条视频大小上限`
- `同时处理数量`
- `单条任务最长等待时间`
- `下载失败自动重试次数`

这些设置只影响当前网页里后续发起的任务，不需要改环境变量。

## 环境变量配置

所有配置项均可通过环境变量覆盖，无需修改代码：

| 环境变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SP_ENDCARD_PATH` | `assets/video/endcard.mp4` | 落版片尾视频路径，仅拼接页使用 |
| `SP_MAX_VIDEO_MB` | `50` | 单条源视频最大体积（MB） |
| `SP_MAX_WORKERS` | `4` | 最大并发线程数 |
| `SP_TASK_TIMEOUT_SEC` | `180` | 单任务超时时间（秒） |
| `SP_DOWNLOAD_RETRIES` | `2` | 下载最大重试次数 |
| `SP_RESULTS_ROOT_DIR` | `~/Downloads/video-splicer-results` | 本地结果保存根目录 |

## 使用方式

### 视频拼接页

- 左侧输入 **PID**，右侧输入 **视频链接**，按行一一对应
- 两个输入框下方会实时显示各自的非空数据条数
- 点击“确认数据并预览”后，可查看总条数；超过 10 条时展示前 5 条和后 5 条，视频链接支持直接点击
- 未点击“确认数据并预览”前，“开始处理”按钮保持灰色不可点击
- 如果手动输入两列条数不一致，或存在非法链接，会阻止开始处理
- 也可上传 Excel（`商品id`、`视频链接`）或 CSV（`pid`、`video_url`）
- 上传 CSV / Excel 后也可先预览原始数据；即使文件缺列或某些行非法，也会先展示可读的原始数据并阻止开始处理
- 输出文件按输入顺序命名为 `1.mp4`、`2.mp4`、`3.mp4`...
- 处理完成后，结果会同步保存到 `~/Downloads/video-splicer-results/splice-时间戳/`，并可直接点击“打开结果目录”

### 视频链接转附件页

- 左侧输入 **item_id**，右侧输入 **视频链接**，按行一一对应
- 两个输入框下方会实时显示各自的非空数据条数
- 点击“确认数据并预览”后，可查看总条数；超过 10 条时展示前 5 条和后 5 条，视频链接支持直接点击
- 未点击“确认数据并预览”前，“开始处理”按钮保持灰色不可点击
- 如果手动输入两列条数不一致，或文件里存在非法数据，会阻止开始处理
- 也可上传 Excel（`商品id`、`视频链接`）或 CSV（`item_id`、`video_url`），同时兼容旧 CSV 表头 `pid`、`video_url`
- 输出文件固定命名为 `item_id.mp4`，重复值自动变为 `item_id__2.mp4`、`item_id__3.mp4`
- 如目标链接需要 VPN，则必须由运行当前应用的机器本身具备访问能力
- 处理完成后，结果会同步保存到 `~/Downloads/video-splicer-results/attachment-时间戳/`，并可直接点击“打开结果目录”

> 注意：当文本框存在非空行时，将忽略上传文件。

## macOS 打包

```bash
bash build_macos_app.sh
```

默认产物：
- `dist/视频拼接工具.app`
- `dist/视频拼接工具-v2.1.zip`

如需额外生成 DMG，可执行：

```bash
BUILD_DMG=1 bash build_macos_app.sh
```

## 运行测试

```bash
pytest
```

## 技术栈

- [Streamlit](https://streamlit.io/) — Web UI 框架
- [FFmpeg](https://ffmpeg.org/) — 视频处理
- [Requests](https://docs.python-requests.org/) — HTTP 下载
- [Pandas](https://pandas.pydata.org/) — Excel / CSV 解析
