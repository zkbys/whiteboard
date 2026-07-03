# Version Audit

This package was assembled from the latest usable local pipeline state.

## Latest Code Baseline

| Area | Latest source used | Reason |
| --- | --- | --- |
| Orchestrator | `whiteboard-infographic-pipeline-orchestrator/SKILL.md`, `references/runbook.md` | Includes manual image handoff, calibration, word timing, action timing, and identity checks. |
| D board control | `hand-drawn-infographic-video-board/scripts/generate_board_package.py` and `create_calibration_tool.py` | Supports `calibration/<boardId>.element_bboxes.json` and fixes duplicate-title behavior after calibration. |
| E renderer | `whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs` and `validate_action_camera_qa.mjs` | Generates `audio/word_timing.json`, `sync/action_timing.json`, renderer action rhythm metadata, `sync/camera_plan.json`, and action/camera QA reports, with a fast regression check. |
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

## Current Optimization Delta

The current multi-board renderer line adds these post-baseline controls:

- `sync/action_timing.json` now records renderer action rhythm fields such as early cursor arrival, draw start, hold-after, stagger, and compression-to-fit status.
- The timing-updated `board/combined_motion_plan.json` carries the same rhythm metadata on each action.
- `sync/camera_plan.json` records overview, region, emphasis, and recovery camera strategies. Bbox coordinates remain references; E dampens zoom rather than treating every bbox as the final frame.
- `sync/action_camera_qa_report.md` and `.json` summarize sync source/fallbacks, rhythm compression, bbox boundary checks, camera zoom thresholds, and keyframe artifact completeness.
- `npm run check` now includes `check:renderer-qa`, which builds a temporary fixture and asserts the action rhythm, camera plan, renderer report, and QA contract without committing generated media.

This delta is implemented in the multi-board E path. The legacy single-board renderer remains a compatibility path and is not the acceptance target for this optimization.
