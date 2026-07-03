# Whiteboard Infographic Pipeline Orchestrator

This Codex Skill orchestrates the AI whiteboard infographic explainer video pipeline.

It coordinates:

- B: `ip-cognition-script-polisher`
- C: `ip-hand-drawn-infographic-planner`
- Creator: `hand-drawn-infographic-creator`
- D: `hand-drawn-infographic-video-board`
- E: `whiteboard-infographic-video-renderer`

The latest public-ready baseline is the post-optimization pipeline: manual model-image handoff, D bbox calibration, measured audio timing, tokenized spoken-anchor sync, editable HyperFrames output, keyframes, and asset identity checks.

## Natural Language Usage

Example request:

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

The orchestrator should extract the topic and duration, create:

```text
orchestrator-runs/YYYYMMDD-HHMM-<topic-slug>/topic_input.txt
```

and run the normal B -> C -> creator -> image handoff -> D -> E pipeline from there.

## Required Files

```text
whiteboard-infographic-pipeline-orchestrator/
├── SKILL.md
├── README.md
├── references/
│   ├── contracts.md
│   └── runbook.md
├── scripts/
│   ├── validate_orchestrator_inputs.py
│   ├── write_board_asset_manifest.py
│   └── check_asset_identity.py
└── examples/
    ├── minimal-topic-input.txt
    ├── expected-output-tree.md
    └── natural-language-invocation.md
```

## Quick Validation

From the repository root:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace . \
  --topic-input whiteboard-infographic-pipeline-orchestrator/examples/minimal-topic-input.txt \
  --project-dir runs/example-output
```

After generated PNGs are manually saved into `runs/example-output/images/`:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/write_board_asset_manifest.py \
  --project-dir runs/example-output \
  --dry-run
```

After D/E have run:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/check_asset_identity.py \
  --project-dir runs/example-output
```

## Latest-Version Requirements

Do not treat older prototype folders or smoke-test runs as the current pipeline. A current run should include:

- `calibration/*.element_bboxes.json` when model PNG layout needs manual alignment.
- `audio/word_timing.json`.
- `sync/action_timing.json`.
- `sync/camera_plan.json`.
- `sync/action_camera_qa_report.md`.
- `board/combined_motion_plan.json` updated with `anchorRatioSource=sync/action_timing.json` where anchors match.
- `video/hyperframes/` plus `video/preview.mp4`, not MP4 only.
- `video/keyframes/` for start/done visual QA.
