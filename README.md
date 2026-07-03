# AI Whiteboard Infographic Pipeline

A modular Codex Skill pipeline for generating reviewable AI whiteboard infographic explainer videos.

The pipeline is designed for staged, human-reviewable production rather than one-shot MP4 generation. It keeps script, semantic board planning, image prompts, model PNG assets, board-control coordinates, measured audio timing, editable HyperFrames output, keyframes, and final acceptance reports as separate artifacts.

## Latest Baseline

This repository is based on the latest local pipeline state, not the older prototype folders.

Latest code baseline:

- `whiteboard-infographic-pipeline-orchestrator/SKILL.md` updated with calibration and token sync requirements.
- `hand-drawn-infographic-video-board/scripts/create_calibration_tool.py` for browser-based bbox calibration.
- `hand-drawn-infographic-video-board/scripts/generate_board_package.py` with calibration-file support.
- `whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs` with `audio/word_timing.json` and `sync/action_timing.json`.

Do not publish old folders such as `whiteboard-infographic-prototype-v0.*`, `integration-smoke-test-*`, raw audio, raw videos, or generated run outputs as the main package.

## Pipeline Stages

```text
Topic or rough script
  -> B ip-cognition-script-polisher
  -> C ip-hand-drawn-infographic-planner
  -> hand-drawn-infographic-creator
  -> manual model PNG handoff
  -> D hand-drawn-infographic-video-board
  -> E whiteboard-infographic-video-renderer
  -> integration_report.md
```

## Modules

| Module | Responsibility | Key outputs |
| --- | --- | --- |
| `ip-cognition-script-polisher` | Preserve the user's stance and produce a 30-60s six-part voiceover package. | `polished_voiceover.md`, `voiceover_segments.json`, `visual_beats.json` |
| `ip-hand-drawn-infographic-planner` | Convert script beats into semantic board plans and image prompts. | `infographic_plan.json`, `board_specs/*.json`, `image_prompts/*.prompt.md` |
| `hand-drawn-infographic-creator` | Turn board prompts into final model-ready image prompts and review notes. | `creator_outputs/*.md`, `imagegen_prompts/*.txt` |
| `hand-drawn-infographic-video-board` | Convert board PNGs and specs into exact control-layer manifests. | `board_manifest.json`, `annotation_manifest.json`, `motion_plan.json`, `combined_motion_plan.json` |
| `whiteboard-infographic-video-renderer` | Generate narration, measured timing, HyperFrames, MP4 preview, and keyframes. | `audio/`, `sync/`, `video/hyperframes/`, `video/preview.mp4` |
| `whiteboard-infographic-pipeline-orchestrator` | Enforce the full run order and acceptance checks. | `integration_report.md` |

## Requirements

- Python 3.10+.
- Node.js 20+.
- `ffmpeg` and `ffprobe` on `PATH`.
- `edge-tts` CLI for narration generation.
- Network access for `npx --yes hyperframes@0.6.99` unless HyperFrames is already cached.
- An image generation tool that can produce or export PNG files.

## Quick Start

Validate the local layout:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace . \
  --topic-input whiteboard-infographic-pipeline-orchestrator/examples/minimal-topic-input.txt \
  --project-dir runs/example-output
```

Run the pipeline through Codex using the orchestrator skill:

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

The image-generation step has a required pause if the tool only exposes preview images. Save each generated PNG as:

```text
runs/example-output/images/board-01.model-generated.png
runs/example-output/images/board-02.model-generated.png
```

Then continue with manifest writing, optional calibration, D package generation, E rendering, keyframe inspection, and asset identity checks.

## Current Acceptance Bar

A current run is complete only when it produces:

- Valid B and C outputs.
- `board_asset_manifest.json` with local `file` PNG assets.
- Optional `calibration/*.element_bboxes.json` when PNG layout needs manual alignment.
- D output under `board_source_for_e/`.
- E output with `audio/voiceover_timing.json`, `audio/word_timing.json`, `sync/action_timing.json`, `video/hyperframes/`, `video/preview.mp4`, `video/keyframes/`, and `video/renderer_report.json`.
- Passing HyperFrames `lint`, `validate`, and `inspect` checks, allowing only documented non-blocking warnings.
- Passing model-PNG identity check from `images/` to D `board.png` to HyperFrames board assets.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Version Audit](docs/VERSION_AUDIT.md)
- [Open Source Checklist](docs/OPEN_SOURCE_CHECKLIST.md)
- [Orchestrator Runbook](whiteboard-infographic-pipeline-orchestrator/references/runbook.md)
- [Pipeline Contracts](whiteboard-infographic-pipeline-orchestrator/references/contracts.md)

## License

MIT. Change `LICENSE` before publishing if you need a different license or copyright holder.
