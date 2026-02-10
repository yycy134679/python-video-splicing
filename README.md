# Python 视频拼接工具

基于 **Streamlit + FFmpeg** 的批量视频拼接工具，用于将源视频与落版片尾（endcard）自动拼接，并输出为统一规格的 MP4 文件。适用于内容运营团队高效批量处理商品视频。

## 功能特性

- **批量拼接** — 多条视频并发下载 & 拼接，支持数十条任务同时处理
- **多种输入方式** — 文本框分列输入 PID / 视频链接，或上传 Excel（`.xlsx`/`.xlsm`）/ CSV 文件
- **智能编码** — 自动探测源视频码率并匹配输出码率，保证画质一致性
- **无音轨兼容** — 源视频或落版无音轨时自动补静默音轨，避免拼接失败
- **分辨率适配** — 落版自动缩放至源视频分辨率，保持画面比例
- **重复 PID 去重命名** — 相同 PID 自动追加后缀 `pid__2.mp4`、`pid__3.mp4`
- **一键下载** — 单条结果直接下载 MP4，多条结果打包为 ZIP（含 `result.csv`）
- **实时进度 & 日志** — 进度条 + 滚动日志面板，处理过程一目了然

## 项目结构

```
├── app.py                   # Streamlit 主入口
├── requirements.txt         # Python 依赖
├── pytest.ini               # 测试配置
├── assets/video/            # 落版片尾视频（endcard.mp4）
├── video_splicer/           # 核心模块
│   ├── models.py            #   数据模型（Config / InputRow / TaskResult）
│   ├── config.py            #   配置加载 & 运行环境校验
│   ├── input_parser.py      #   输入解析（文本 / CSV / Excel）
│   ├── downloader.py        #   视频下载（支持重试 & 超时 & 大小限制）
│   ├── ffmpeg_pipeline.py   #   FFmpeg 探测 & 拼接流水线
│   ├── runner.py            #   批量并发调度
│   └── artifact.py          #   结果打包（CSV / ZIP）
└── tests/                   # 单元测试
    ├── test_input_parser.py
    ├── test_naming.py
    ├── test_bitrate_policy.py
    ├── test_artifact_decision.py
    └── test_result_csv.py
```

## 前置依赖

| 依赖                 | 说明           |
| -------------------- | -------------- |
| **Python 3.11+**     | 运行环境       |
| **FFmpeg / FFprobe** | 视频探测与拼接 |

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

浏览器访问 `http://localhost:8501` 即可使用。

## 环境变量配置

所有配置项均可通过环境变量覆盖，无需修改代码：

| 环境变量              | 默认值                     | 说明                     |
| --------------------- | -------------------------- | ------------------------ |
| `SP_ENDCARD_PATH`     | `assets/video/endcard.mp4` | 落版片尾视频路径         |
| `SP_MAX_VIDEO_MB`     | `50`                       | 单条源视频最大体积（MB） |
| `SP_MAX_WORKERS`      | `6`                        | 最大并发线程数           |
| `SP_TASK_TIMEOUT_SEC` | `180`                      | 单任务超时时间（秒）     |
| `SP_DOWNLOAD_RETRIES` | `2`                        | 下载最大重试次数         |

## 使用方式

### 文本输入

左侧输入框填写 **PID**（每行一条），右侧输入框填写对应的**视频链接**（每行一条，按行一一对应），点击「开始处理」。

### 文件上传

上传 Excel 文件（需包含 `商品id` 和 `视频链接` 两列）或 CSV 文件（需包含 `pid` 和 `video_url` 两列）。

> 注意：当文本框存在非空行时，将忽略上传文件。

## 运行测试

```bash
pytest
```

## 技术栈

- [Streamlit](https://streamlit.io/) — Web UI 框架
- [FFmpeg](https://ffmpeg.org/) — 视频处理
- [Requests](https://docs.python-requests.org/) — HTTP 下载
- [Pandas](https://pandas.pydata.org/) — Excel / CSV 解析

