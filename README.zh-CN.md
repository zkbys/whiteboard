# AI 白板信息图讲解视频流水线

中文 | [English](README.md)

这是一套模块化的 Codex Skill 流水线，用来生成可审查、可迭代、可继续编辑的 AI 白板信息图讲解视频。

它不是“一次性生成 MP4”的脚本，而是一套分阶段生产流程：脚本、语义信息图规划、生图提示词、模型 PNG 资产、白板控制层坐标、真实音频时长、可编辑 HyperFrames 工程、关键帧和最终验收报告都会作为独立产物保留下来。

## 最新基线

这个仓库基于当前最新的本地流水线整理，不包含旧实验目录。

最新代码基线包括：

- `whiteboard-infographic-pipeline-orchestrator/SKILL.md`：总编排 Skill，包含生图交接、校准、同步和验收要求。
- `hand-drawn-infographic-video-board/scripts/create_calibration_tool.py`：浏览器拖框校准工具，用于生成 bbox 校准 JSON。
- `hand-drawn-infographic-video-board/scripts/generate_board_package.py`：D 阶段控制层生成脚本，支持读取校准文件。
- `whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs`：E 阶段渲染器，支持 `audio/word_timing.json`、`sync/action_timing.json`、渲染器动作节奏层、`sync/camera_plan.json` 和 action/camera QA 报告。

不要把旧目录作为当前主线发布，例如 `whiteboard-infographic-prototype-v0.*`、`integration-smoke-test-*`、原始音频、原始视频或生成运行结果。

## 流水线阶段

```text
主题或粗稿
  -> B ip-cognition-script-polisher
  -> C ip-hand-drawn-infographic-planner
  -> hand-drawn-infographic-creator
  -> 手动保存模型 PNG
  -> D hand-drawn-infographic-video-board
  -> E whiteboard-infographic-video-renderer
  -> integration_report.md
```

## 模块说明

| 模块 | 职责 | 关键输出 |
| --- | --- | --- |
| `ip-cognition-script-polisher` | 保留用户核心立场，生成 30-60 秒、六段式口播包。 | `polished_voiceover.md`, `voiceover_segments.json`, `visual_beats.json` |
| `ip-hand-drawn-infographic-planner` | 把口播和视觉节奏转成语义白板规划和生图提示词。 | `infographic_plan.json`, `board_specs/*.json`, `image_prompts/*.prompt.md` |
| `hand-drawn-infographic-creator` | 把白板语义 prompt 转成最终可用于生图模型的提示词和审查说明。 | `creator_outputs/*.md`, `imagegen_prompts/*.txt` |
| `hand-drawn-infographic-video-board` | 把 board PNG 和 board spec 转成精确控制层。 | `board_manifest.json`, `annotation_manifest.json`, `motion_plan.json`, `combined_motion_plan.json` |
| `whiteboard-infographic-video-renderer` | 生成配音、真实 timing、动作节奏、镜头策略、HyperFrames 工程、MP4 预览、关键帧和 QA 报告。 | `audio/`, `sync/`, `video/hyperframes/`, `video/preview.mp4` |
| `whiteboard-infographic-pipeline-orchestrator` | 固定完整执行顺序，并输出最终验收报告。 | `integration_report.md` |

## 环境要求

- Python 3.10+。
- Node.js 20+。
- `ffmpeg` 和 `ffprobe` 已加入 `PATH`。
- `edge-tts` CLI，用于生成中文配音。
- 可访问 `npx --yes hyperframes@0.6.99`，除非 HyperFrames 已经在本地缓存。
- 一个可以生成或导出 PNG 的图像生成工具。

## 快速开始

先验证本地目录结构：

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace . \
  --topic-input whiteboard-infographic-pipeline-orchestrator/examples/minimal-topic-input.txt \
  --project-dir runs/example-output
```

在 Codex 中使用总编排 Skill 运行：

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

如果图像生成工具只返回预览图，没有稳定 URL 或本地文件路径，流水线必须暂停。请把每张生成图手动保存为：

```text
runs/example-output/images/board-01.model-generated.png
runs/example-output/images/board-02.model-generated.png
```

之后继续执行 manifest 写入、可选校准、D 控制层生成、E 渲染、关键帧检查和资产一致性校验。

## 当前验收标准

一次当前版本的完整运行至少要产出：

- B 和 C 阶段验证通过。
- `board_asset_manifest.json`，其中本地模型 PNG 使用 `asset.kind=file`。
- 如果模型 PNG 和控制层初稿不对齐，提供 `calibration/*.element_bboxes.json`。
- D 阶段输出 `board_source_for_e/`。
- E 阶段输出 `audio/voiceover_timing.json`、`audio/word_timing.json`、`sync/action_timing.json`、`sync/camera_plan.json`、`sync/action_camera_qa_report.md`、`video/hyperframes/`、`video/preview.mp4`、`video/keyframes/` 和 `video/renderer_report.json`。
- HyperFrames `lint`、`validate`、`inspect` 没有阻断错误；非阻断 warning 必须记录。
- 模型 PNG 从 `images/` 到 D `board.png` 再到 HyperFrames 资产的文件一致性校验通过。

## 文档

- [新线程/Agent 规则](AGENTS.md)
- [贡献与推送流程](CONTRIBUTING.md)
- [项目结构](docs/PROJECT_STRUCTURE.md)
- [架构说明](docs/ARCHITECTURE.md)
- [版本判定](docs/VERSION_AUDIT.md)
- [开源检查清单](docs/OPEN_SOURCE_CHECKLIST.md)
- [总编排运行手册](whiteboard-infographic-pipeline-orchestrator/references/runbook.md)
- [流水线契约](whiteboard-infographic-pipeline-orchestrator/references/contracts.md)

## License

MIT。版权主体为 `yanzhengkai`。
