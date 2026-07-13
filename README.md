# Whiteboard Video

[English](README.en.md)

**输入一个主题，输出 30–60 秒的 AI 白板信息图讲解视频。**

<p align="center">
  <img src="https://raw.githubusercontent.com/zkbys/whiteboard/main/assets/demo.gif" width="720" alt="示例视频：主题「AI 工具越多，普通人反而越低效」（已加速 1.25×）">
  <br>
</p>

## 🚀 快速开始

**复制下面的话，直接发给你的 AI 编程助手：**

```
请安装这个项目：https://github.com/zkbys/whiteboard.git

阅读 README 后运行：
python3 scripts/install.py --target codex   # Codex
python3 scripts/install.py --target claude  # Claude Code

安装完成后运行：
python3 scripts/doctor.py --json

然后帮我做一个视频，主题是「AI 工具越多，普通人反而越低效」，时长 30-60 秒。
```

视频会生成在当前目录的 `whiteboard-runs/<run-id>/video/preview.mp4`。

## 命令行安装

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard

# Codex
python3 scripts/install.py --target codex
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json

# Claude Code
python3 scripts/install.py --target claude
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json
```

同时安装到两端：`--target both`。预览不写入：`--dry-run`。升级：`--upgrade`。

## 一次运行会得到什么

```text
whiteboard-runs/<run-id>/
├── script/                    # 口播文案与视觉节拍
├── infographic/               # 信息图规划
├── images/*.model-generated.png   # 模型生成的白板图
├── board_source_for_e/        # 动画控制层
├── audio/                     # 配音、字幕、时间轴
├── sync/                      # 动作/镜头 QA 报告
├── video/
│   ├── preview.mp4            # 最终视频
│   ├── hyperframes/           # 可编辑工程
│   └── keyframes/             # 关键帧
└── integration_report.md      # 验收报告
```

渲染完成后可运行 v1 验收器：

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /absolute/path/to/whiteboard-run
```

## 环境要求

- Python 3.10+
- Node.js 20+
- `ffmpeg`、`ffprobe`
- `edge-tts`、`npx`
- `hyperframes@0.6.99`

```bash
python3 scripts/doctor.py        # 文本报告
python3 scripts/doctor.py --json # JSON 报告
```

doctor 检查四层状态：

| 分类 | 含义 |
|------|------|
| `install` | Skill 本体及内部模块是否完整 |
| `render` | Python/Node/ffmpeg/edge-tts/HyperFrames 是否就绪 |
| `output` | 输出目录是否可写 |
| `image` | 图片模式是 `interactive`（默认，无密钥）还是 `auto` |

## 图片模式

默认 `interactive`：AI 助手在生图后暂停一次，等待你确认图片已保存到指定路径，然后自动继续后续流程。

自动模式（需要 OpenAI API Key）：

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=openai
export OPENAI_API_KEY="..."
```

仅配置 key 不会触发计费，必须同时设置 `WHITEBOARD_IMAGE_PROVIDER=openai`。

## 已知限制

- 不搜索隐藏缓存，不伪造图片 URL，不用占位图冒充模型输出
- OCR/视觉 bbox 精确定位不在 v1.0 范围内；低置信度时采用保守镜头

## 开发者

内部流水线：Topic → B 口播 → C 规划 → Creator 生图 → D 控制层 → E 渲染/QA

开发前请阅读 [AGENTS.md](AGENTS.md)、[项目结构](docs/PROJECT_STRUCTURE.md)、[架构契约](docs/ARCHITECTURE.md)。提交前运行：

```bash
npm run check
```

## License

MIT。
