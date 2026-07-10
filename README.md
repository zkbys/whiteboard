# Whiteboard Video

中文 | [English](README.en.md)

把一个主题、观点或粗稿，变成 30-60 秒的 AI 白板信息图讲解视频：同时保留可编辑 HyperFrames 工程、真实音频 timing、鼠标动作/镜头 QA、关键帧和最终验收报告。

> 对外只有一个 Skill：`whiteboard-video`。B / C / Creator / D / E 依然作为内部流水线模块，用户无需分别安装或理解它们。

## 已有的真实验收证据

最新本地端到端样例完成了 2 张白板、6 段口播、9 个批注动作，实际视频时长 42.58 秒；音频 timing 偏差 0.045 秒，action/camera QA 为 `pass`，9 个动作全部匹配，资产一致性验证通过。仓库不提交生成的视频、音频或模型图片，详细验收记录见 [真实端到端样例](docs/REAL_E2E_SAMPLE.md)。

## 让 Codex 安装

把下面这段话原样发给 Codex：

```text
请安装这个项目：https://github.com/zkbys/whiteboard.git

请克隆到临时目录，阅读根 README，然后运行：
python3 scripts/install.py --target codex

安装后请运行：
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json

请根据 doctor 的 install / render / output / image 分层结果，明确告诉我安装是否成功、渲染依赖是否齐全、是否需要重启 Codex，以及当前是 interactive 还是 auto 图片模式。不要使用 sudo。
```

Codex 的默认用户安装位置是：

```text
$HOME/.agents/skills/whiteboard-video/
```

Codex 通常会自动发现新 Skill；如果 `$whiteboard-video` 没有出现，再重启 Codex 或新建任务。安装位置和发现行为依据 [OpenAI Codex Skills 官方文档](https://learn.chatgpt.com/docs/build-skills)。

## 让 Claude Code 安装

把下面这段话原样发给 Claude Code：

```text
请安装这个项目：https://github.com/zkbys/whiteboard.git

请克隆到临时目录，阅读根 README，然后运行：
python3 scripts/install.py --target claude

安装后请运行：
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json

请根据 doctor 的 install / render / output / image 分层结果，明确告诉我安装是否成功、渲染依赖是否齐全、是否需要重启 Claude Code，以及当前是 interactive 还是 auto 图片模式。不要使用 sudo。
```

Claude Code 的默认用户安装位置是：

```text
~/.claude/skills/whiteboard-video/
```

如果 `~/.claude/skills` 在当前会话启动时已存在，Claude Code 可以热加载新 Skill；如果这个顶层目录是安装时才首次创建，需重启 Claude Code。详见 [Anthropic Claude Code Skills 官方文档](https://code.claude.com/docs/en/skills)。

## 命令行直接安装

Codex：

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard
python3 scripts/install.py --target codex
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json
```

Claude Code：

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard
python3 scripts/install.py --target claude
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json
```

同时安装到两端：

```bash
python3 scripts/install.py --target both
```

预览而不写入：

```bash
python3 scripts/install.py --target both --dry-run
```

重复安装同一版本会安全返回 `already current`。当 Git 仓库内容变化后，安装器会要求显式升级：

```bash
git pull --ff-only
python3 scripts/install.py --target codex --upgrade
```

安装器不使用 sudo，不依赖 symlink，不覆盖没有本项目 `installation.json` 标记的同名目录。安装包内含完整内部 runtime，删除原始 Git clone 后仍可用。

## 生成第一个视频

Codex 中直接说：

```text
请使用 whiteboard-video skill 帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在 30-60 秒左右。
```

Claude Code 中可以说同样的自然语言，或显式调用：

```text
/whiteboard-video 主题为“AI 工具越多，普通人反而越低效”，时长 30-60 秒。
```

Skill 默认把项目写到当前工作目录的 `whiteboard-runs/` 中，而不是写入受管理的 Skill 安装目录。

## 最终会得到什么

一次通过验收的运行至少包含：

```text
whiteboard-runs/<run-id>/
├── script/
├── infographic/
├── images/*.model-generated.png
├── board_asset_manifest.json
├── board_source_for_e/
├── audio/
├── sync/
│   ├── action_timing.json
│   ├── camera_plan.json
│   ├── action_camera_qa_report.md
│   └── action_camera_qa_report.json
├── video/
│   ├── preview.mp4
│   ├── hyperframes/
│   ├── keyframes/
│   └── renderer_report.json
└── integration_report.md
```

## 一次性环境要求和 doctor

- Python 3.10+
- Node.js 20+
- `ffmpeg`
- `ffprobe`
- `edge-tts`
- `npx`
- 可下载或已缓存的 `hyperframes@0.6.99`

运行：

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --json
```

doctor 分层报告：

| 分类 | 含义 |
| --- | --- |
| `install` | 公共 Skill 和内部 B/C/Creator/D/E/orchestrator 是否完整 |
| `render` | Python、Node、ffmpeg、ffprobe、edge-tts、npx 和 HyperFrames 是否可用 |
| `output` | 视频项目输出目录是否可写 |
| `image` | 当前图片模式是 `interactive` 还是 `auto` |

`install=PASS` 但 `render=FAIL` 表示 Skill 已正确安装，但尚不能完成真实渲染。`image=WARN` 是当前 interactive 版本的预期状态，不代表安装失败。

## 当前已知限制

当前发布的是可安装的 `interactive` 版本。如果图片工具只返回预览图，Agent 会生成所有白板图后暂停一次，要求用户将 PNG 保存到它列出的确切路径。图片齐全后，流水线继续 D/E、渲染、关键帧和 QA。

当前不会：

- 搜索隐藏预览缓存。
- 伪造图片 URL。
- 用占位图或 D 生成的 SVG 冒充模型 PNG。
- 声称从主题到视频已经实现零人工介入。

`auto` 模式需要未来增加稳定 image provider/API、API key 配置和自动 PNG 落盘。

## 开发者：内部流水线

```text
用户主题或粗稿
  -> B 口播打磨
  -> C 语义信息图规划
  -> Creator 生图提示词
  -> interactive 模型 PNG 交接
  -> D 白板控制层与校准
  -> E 真实 timing、HyperFrames、MP4、关键帧与 QA
  -> integration_report.md
```

开发和贡献前请阅读 [AGENTS.md](AGENTS.md)、[项目结构](docs/PROJECT_STRUCTURE.md)、[架构契约](docs/ARCHITECTURE.md)和 [版本审计](docs/VERSION_AUDIT.md)。所有改动必须运行：

```bash
npm run check
```

较慢的真实渲染回归：

```bash
npm run check:renderer-real
```

## License

MIT。
