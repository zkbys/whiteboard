# Agent Instructions

This file is the first thing a new Codex/agent thread should read before editing this repository.

## Canonical Workspace

Work only in this repository:

```text
/Users/yanzhengkai/Documents/AI剪辑skill/ai-whiteboard-infographic-pipeline
```

Remote:

```text
https://github.com/zkbys/whiteboard.git
```

Do not edit or publish files from the parent experimental workspace unless the user explicitly asks for historical reference work. In particular, do not treat these old folders as the active source:

- `../whiteboard-infographic-prototype-v0.*`
- `../integration-smoke-test-*`
- `../integration-full-run-*`
- `../optimization-sync-calibration-test/`
- `../orchestrator-runs/`
- `../reference-video-analysis/`
- `../visual-hammer-v0.1/`

## Start Every New Thread With

```bash
cd "/Users/yanzhengkai/Documents/AI剪辑skill/ai-whiteboard-infographic-pipeline"
git status --short --branch
git pull --ff-only
```

Then read, as needed:

- `README.zh-CN.md` or `README.md`
- `docs/PROJECT_STRUCTURE.md`
- `docs/ARCHITECTURE.md`
- `docs/VERSION_AUDIT.md`
- the `SKILL.md` for the module being changed
- the matching `references/contracts.md` when changing JSON contracts or paths

## Current Pipeline Boundary

Keep the module responsibilities separated:

- B `ip-cognition-script-polisher`: script shaping only.
- C `ip-hand-drawn-infographic-planner`: semantic board planning only; no bbox, camera, cursor, or animation coordinates.
- Creator `hand-drawn-infographic-creator`: image-generation prompts and review notes only.
- D `hand-drawn-infographic-video-board`: board PNG control layer, bbox calibration, annotation manifests, and motion plans.
- E `whiteboard-infographic-video-renderer`: narration, measured timing, tokenized action sync, HyperFrames, preview MP4, and keyframes.
- Orchestrator `whiteboard-infographic-pipeline-orchestrator`: full run order, handoff rules, validation, and acceptance reporting.

## Latest-Version Guardrails

Do not regress to old prototype behavior. Current functionality must preserve:

- D project mode with `board_asset_manifest.json`, `board_index.json`, and `combined_motion_plan.json`.
- D `--calibration-dir` support and `scripts/create_calibration_tool.py`.
- E measured audio timing through `ffprobe`.
- E `audio/word_timing.json`.
- E `sync/action_timing.json`.
- Editable `video/hyperframes/` output, not MP4-only output.
- Keyframe extraction for action-level visual QA.
- Asset identity checks from `images/*.model-generated.png` to D `board.png` to HyperFrames board assets.

## Git Workflow

For feature work, prefer a branch:

```bash
git checkout -b codex/<short-feature-name>
```

Use direct `main` commits only for small documentation fixes or when the user explicitly requests it.

Before committing:

```bash
npm run check
find . -name ".DS_Store" -delete
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
git status --short
```

Commit and push:

```bash
git add <changed-files>
git commit -m "<concise change summary>"
git push -u origin <branch-name>
```

If committing directly to `main`:

```bash
git push origin main
```

## What Not To Commit

Do not commit generated run outputs or private media:

- `runs/`
- `orchestrator-runs/`
- generated `integration-*` or `optimization-*` folders
- `*.mp4`, `*.mov`, `*.mp3`, `*.wav`, `*.aiff`
- generated model PNGs, contact sheets, and keyframes unless deliberately curated as tiny public fixtures
- `.DS_Store`, `__pycache__/`, `node_modules/`, `.playwright-cli/`

The only current allowed PNG fixture is:

```text
whiteboard-infographic-video-renderer/examples/input/board/board.png
```

## Documentation Rules

When changing behavior or contracts, update the docs in the same commit:

- root `README.md`
- root `README.zh-CN.md`
- `docs/ARCHITECTURE.md`
- `docs/VERSION_AUDIT.md` when changing baseline/version assumptions
- relevant module `SKILL.md`
- relevant `references/contracts.md`

## Validation Scope

Always run:

```bash
npm run check
```

For module-specific changes, also run the closest validator or dry run:

- B: `python3 ip-cognition-script-polisher/scripts/validate_script_package.py --package-dir ip-cognition-script-polisher/examples/output`
- C: `python3 ip-hand-drawn-infographic-planner/scripts/validate_infographic_plan.py ip-hand-drawn-infographic-planner/examples/ai-cognition-example`
- D: `python3 hand-drawn-infographic-video-board/scripts/generate_board_package.py --help`
- E: `node whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs --help`
- E action/camera QA regression: `npm run check:renderer-qa`
- E optional real render regression: `npm run check:renderer-real`

Do not report a pipeline run as successful unless the relevant acceptance artifacts exist and the validation results are recorded.
