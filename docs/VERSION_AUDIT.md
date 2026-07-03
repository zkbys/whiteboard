# Version Audit

This package was assembled from the latest usable local pipeline state.

## Latest Code Baseline

| Area | Latest source used | Reason |
| --- | --- | --- |
| Orchestrator | `whiteboard-infographic-pipeline-orchestrator/SKILL.md`, `references/runbook.md` | Includes manual image handoff, calibration, word timing, action timing, and identity checks. |
| D board control | `hand-drawn-infographic-video-board/scripts/generate_board_package.py` and `create_calibration_tool.py` | Supports `calibration/<boardId>.element_bboxes.json` and fixes duplicate-title behavior after calibration. |
| E renderer | `whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs` | Generates `audio/word_timing.json`, `sync/action_timing.json`, and action sync metadata. |
| Integration proof | `optimization-sync-calibration-test/CALIBRATED_RERENDER_REPORT.md` | Latest acceptance checkpoint after manual calibration JSON was supplied. |
| Natural-language orchestration proof | `orchestrator-runs/20260619-1125-ai-tools-overload/integration_report.md` | Latest one-command orchestrator run proof, but it predates the full calibration polish. |

## Excluded Old Versions

Do not publish these as the active implementation:

- `whiteboard-infographic-prototype-v0.1` through `whiteboard-infographic-prototype-v0.5`: early HyperFrames prototypes.
- `whiteboard-board-package-v0.1`: single-board proof of concept.
- `integration-smoke-test-ai-tools-overload`: useful smoke-test history, not the final public package.
- `integration-full-run-from-topic-input`: important full-run evidence, but superseded by the later sync/calibration optimization.
- Raw media such as `.mp4`, `.mov`, `.mp3`, `.wav`, `.aiff`, generated PNGs, contact sheets, and reference-video frames.

## Current Acceptance Snapshot

The latest calibrated rerender checkpoint passed with:

- 3 boards.
- 6 voiceover segments.
- 10 annotation actions.
- Manual calibration JSON consumed by D for all boards.
- `audio/word_timing.json` with cue-tokenized timing.
- `sync/action_timing.json` with 10 matched actions, 0 fallbacks, average confidence 0.9.
- Rendered duration 43.821s, timing duration 43.780s, delta 0.041s.
- HyperFrames validate and inspect passing.

The remaining non-blocking warnings are font mapping and large generated composition size.
