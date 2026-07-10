# Version Audit

This package was assembled from the latest usable local pipeline state.

## Product installation baseline

The public product surface is now `skills/whiteboard-video/SKILL.md`. `scripts/install.py` installs a complete copy to the current official user Skill locations for Codex (`$HOME/.agents/skills`) and Claude Code (`~/.claude/skills`). The installed runtime contains B/C/Creator/D/E/orchestrator, so it remains usable after the source clone is removed.

`scripts/doctor.py` distinguishes installation readiness, render readiness, output writability, and image automation. The default image status is intentionally `WARN` in `interactive` mode; a valid OpenAI or command provider reports `PASS` in `auto` mode.

Clean installation regression coverage includes Codex, Claude Code, both targets, same-version idempotence, explicit upgrade, unmanaged-directory refusal, controlled missing dependencies, paths with spaces/non-ASCII characters, and scans for developer absolute paths or generated media.

## Automatic image provider baseline (0.2.0)

`whiteboard-infographic-pipeline-orchestrator/scripts/generate_board_images.py` now provides three explicit routes:

- `interactive`: writes exact manual targets and exits with handoff-required status.
- `openai`: calls `/v1/images/generations`, defaults to `gpt-image-2`, decodes `b64_json`, validates PNGs, and never persists the API key.
- `command`: invokes one executable without a shell using a fixed prompt/output/board argument contract.

Automatic runs write `image_generation_report.json`, atomically persist validated PNGs, reuse existing valid images on resume, and automatically continue into `board_asset_manifest.json`. API-key presence alone does not select a paid provider. The implementation is covered with a local mock HTTP server and command fixture, not a live billable API call.

## Latest Code Baseline

| Area | Latest source used | Reason |
| --- | --- | --- |
| Orchestrator | `whiteboard-infographic-pipeline-orchestrator/SKILL.md`, `references/runbook.md` | Includes automatic/interactive image handoff, calibration, word timing, action timing, and identity checks. |
| D board control | `hand-drawn-infographic-video-board/scripts/generate_board_package.py` and `create_calibration_tool.py` | Supports `calibration/<boardId>.element_bboxes.json` and fixes duplicate-title behavior after calibration. |
| E renderer | `whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs` and `validate_action_camera_qa.mjs` | Generates `audio/word_timing.json`, `sync/action_timing.json`, renderer action rhythm metadata, `sync/camera_plan.json`, and action/camera QA reports, with a fast regression check. |
| Integration proof | `docs/REAL_E2E_SAMPLE.md` | Latest local real end-to-end sample after action rhythm, camera strategy, and action/camera QA optimization. |
| Natural-language orchestration proof | `orchestrator-runs/20260619-1125-ai-tools-overload/integration_report.md` | Useful earlier one-command orchestrator run proof, but it predates the current renderer QA and camera strategy layer. |

## Excluded Old Versions

Do not publish these as the active implementation:

- `whiteboard-infographic-prototype-v0.1` through `whiteboard-infographic-prototype-v0.5`: early HyperFrames prototypes.
- `whiteboard-board-package-v0.1`: single-board proof of concept.
- `integration-smoke-test-ai-tools-overload`: useful smoke-test history, not the final public package.
- `integration-full-run-from-topic-input`: important full-run evidence, but superseded by the later sync/calibration optimization.
- Raw media such as `.mp4`, `.mov`, `.mp3`, `.wav`, `.aiff`, generated PNGs, contact sheets, and reference-video frames.

## Current Acceptance Snapshot

The latest real end-to-end local sample is recorded in `docs/REAL_E2E_SAMPLE.md`. Its generated media remains in ignored local run output:

```text
orchestrator-runs/20260705-action-camera-real-e2e
```

The final sample passed with:

- 2 boards.
- 6 voiceover segments.
- 9 annotation actions.
- Real model-generated board PNGs copied into `images/`.
- Manual calibration JSON consumed by D for both boards.
- `audio/word_timing.json` with cue-tokenized timing.
- `sync/action_timing.json` with 9 matched actions, 0 fallbacks, average confidence 0.9.
- `sync/camera_plan.json` with overview, emphasis, and recovery segment strategies, plus region focus inside overview/recovery planning.
- `sync/action_camera_qa_report.json` status `pass`: 0 rhythm compressions, 0 bbox issues, 0 camera warnings, 0 keyframe issues.
- Rendered duration 42.581333s, timing duration 42.536s, delta 0.045s.
- HyperFrames validate and inspect passing.
- Keyframe manifest and start/done contact sheets present.
- Asset identity passing from `images/` to D `board.png` to HyperFrames assets.

The remaining non-blocking warnings are font mapping and large generated composition size.

## Current Optimization Delta

The current multi-board renderer line adds these post-baseline controls:

- `sync/action_timing.json` now records renderer action rhythm fields such as early cursor arrival, draw start, hold-after, stagger, and compression-to-fit status.
- The timing-updated `board/combined_motion_plan.json` carries the same rhythm metadata on each action.
- `sync/camera_plan.json` records overview, region, emphasis, and recovery camera strategies. Bbox coordinates remain references; E dampens zoom rather than treating every bbox as the final frame.
- `sync/action_camera_qa_report.md` and `.json` summarize sync source/fallbacks, rhythm compression, bbox boundary checks, camera zoom thresholds, and keyframe artifact completeness.
- `npm run check` includes `check:renderer-qa`, which builds a temporary healthy fixture and asserts the action rhythm, camera plan, renderer report, and QA contract without committing generated media.
- `npm run check` also includes `check:renderer-adversarial`, which builds a temporary bad fixture and asserts QA detects sync fallback, bbox failures, camera zoom warnings, and skipped keyframes.
- `npm run check` includes `check:install`, which builds and diagnoses self-contained Codex and Claude Code installations in system temporary directories.
- `npm run check` includes `check:image-provider`, which validates interactive, OpenAI-mock, command, resume, malformed-response, secret, PNG, and manifest behavior.
- `npm run check:renderer-real` is available as a slower optional regression for deterministic fixture audio, HyperFrames lint/validate/inspect, MP4 render, keyframe extraction, contact sheets, and QA artifact completeness.

This delta is implemented in the multi-board E path. The legacy single-board renderer remains a compatibility path and is not the acceptance target for this optimization.
