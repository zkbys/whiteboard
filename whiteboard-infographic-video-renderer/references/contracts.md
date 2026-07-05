# Renderer Contracts

## Input Layout

Default project package layout:

```text
project-output/
├── script/voiceover_segments.json
├── board/board-01.board_manifest.json
├── board/board-01.motion_plan.json
└── infographic/images/board-01.png
```

The renderer also accepts the v0.5 prototype layout:

```text
project-output/
├── script/voiceover_segments.json
└── assets/board/
    ├── board_manifest.json
    ├── motion_plan.json
    └── board.png
```

Use explicit CLI flags when a package has multiple boards or nonstandard names.

Multi-board D-thread package layout:

```text
board/
├── board_index.json
├── combined_motion_plan.json
├── board-01/
│   ├── board_manifest.json
│   ├── annotation_manifest.json
│   ├── motion_plan.json
│   └── board.png            # optional when asset.kind=url
├── board-02/
│   └── ...
└── board-03/
    └── ...
```

Use `scripts/render_multi_board_project.mjs` for this layout. The renderer must read both `board_index.json` and `combined_motion_plan.json`.
Each board must provide a consumable visual asset through either a local `board.png`/`asset.localPath` or `asset.kind=url`.

## Required Fields

`voiceover_segments.json`:

- `segments[]` with `id`, `text` or `caption`, optional `pauseAfter`, optional `target`, optional `camera`, and optional `actions[]`.
- `voice.name`, `voice.rate`, `voice.pitch`, and `voice.volume` are optional. Missing values default to `zh-CN-YunxiNeural`, `+14%`, `+0Hz`, and `+0%`.
- `actions[].anchorRatio` is optional but preferred for recalculating action offsets after real TTS duration is known.

`board_manifest.json`:

- `canvas.width` and `canvas.height`.
- `elements[]` with stable `id`, optional `camera`, and `annotations`.
- Supported annotations: `underline`, `circle`, `box`, `check`, `strike`.

`motion_plan.json`:

- `composition.width`, `composition.height`, and `composition.duration`.
- `overview_camera`.
- `segments[]` with `id`, `target`, `camera`, `caption`, and `actions[]`.
- Each action must include `type`, `element`, `annotation`, `spokenAnchor`, and `duration`.

`board_index.json` for multi-board mode:

- `boards[]` with stable `boardId`, `path`, and optional `asset`.
- `asset.kind=file` or `svg_preview` should resolve to a local image, usually copied by D as `board.png`.
- `asset.kind=url` is a valid renderer input. The renderer passes the URL into the HyperFrames `<img>` visual layer instead of requiring a local copy.
- Each `boards[].path` must point to a directory with `board_manifest.json`, `annotation_manifest.json`, and `motion_plan.json`.

`combined_motion_plan.json` for multi-board mode:

- `composition.width`, `composition.height`, and `composition.duration`.
- `segments[]` with global `start`, `speechEnd`, and `end`.
- Each segment must include `boardId`, `target`, `camera`, `caption`, and `actions[]`.
- Each action must include `type`, `element`, `annotation`, `spokenAnchor`, `offset`, and `duration`.
- This file is the full-video timeline. Per-board `motion_plan.json` files are local control packages and their local `start=0` values must not be treated as full-video time.

## Output Layout

```text
project-output/
├── audio/
│   ├── narration.wav
│   ├── captions.srt
│   ├── voiceover_timing.json
│   ├── word_timing.json
│   └── segments/
├── sync/
│   ├── action_timing.json
│   ├── camera_plan.json
│   ├── action_camera_qa_report.md
│   └── action_camera_qa_report.json
├── video/
│   ├── hyperframes/
│   │   ├── index.html
│   │   ├── DESIGN.md
│   │   ├── hyperframes.json
│   │   ├── package.json
│   │   ├── assets/
│   │   └── scripts/extract_action_keyframes.mjs
│   ├── preview.mp4
│   ├── keyframes/
│   └── renderer_report.json
└── board or assets/board/
    ├── *.motion_plan.json
    └── *.before-renderer-timing.json
```

The source motion plan is updated in place after a one-time backup. The generated HyperFrames project also receives the updated plan under `assets/board/motion_plan.json`.

In multi-board mode, the input D package is not modified. The output package receives:

```text
project-output/
├── board/
│   ├── board_index.json
│   ├── combined_motion_plan.json
│   └── board-xx/
├── audio/
└── video/
```

The output `board/combined_motion_plan.json` and `video/hyperframes/assets/board/motion_plan.json` are timing-updated from measured TTS duration.
In multi-board mode, renderer action rhythm fields and camera strategy fields are also written into the output `board/combined_motion_plan.json` and the HyperFrames asset copy.

## Timing Behavior

1. Generate one edge-tts media file per segment.
2. Convert each segment to 48 kHz mono WAV.
3. Measure each WAV with `ffprobe`.
4. Append segment-level silence from `pauseAfter`.
5. Concatenate into `audio/narration.wav`.
6. Write `audio/voiceover_timing.json`.
7. Write `audio/word_timing.json` from subtitle cue token spans when subtitle timing is available.
8. Write `sync/action_timing.json` by matching action `spokenAnchor` values against token spans.
9. Recalculate motion plan segment `start`, `speechEnd`, and `end`.
10. Recalculate action `offset` from `sync/action_timing.json` when possible, then `anchorRatio`, then a bounded fallback.
11. Apply renderer action rhythm in multi-board mode: cursor pre-arrival, draw start, hold-after, light staggering, minimum gap, and compression-to-fit status.
12. Apply renderer camera strategy in multi-board mode and write `sync/camera_plan.json`.
13. After render or skipped-render validation, write action/camera QA reports under `sync/`.

For multi-board mode, match voiceover action `anchorRatio` by segment id and action order, but keep boardId, target, element, annotation, and action type from `combined_motion_plan.json`.

The current token sync is not true TTS WordBoundary data. It is a practical cue-tokenized layer that records confidence and source for every matched action. Low-confidence or fallback actions must be reported instead of hidden.

## Action Rhythm Contract

In multi-board mode, each `sync/action_timing.json` action may include:

```json
{
  "rhythm": {
    "source": "renderer-action-rhythm-v0.1",
    "preArrivalSec": 0.16,
    "cursorMoveLeadSec": 1.18,
    "drawStartLeadSec": 0,
    "holdAfterSec": 0.42,
    "minGapSec": 0.12,
    "staggerSec": 0.07,
    "cursorMoveStartOffset": 0,
    "cursorArrivalOffset": 0.84,
    "drawStartOffset": 1,
    "drawDoneOffset": 1.72,
    "holdDoneOffset": 2.14,
    "compressedToFit": false
  }
}
```

The timing-updated `board/combined_motion_plan.json` copies this rhythm object onto each corresponding action. `compressedToFit=true` means the requested rhythm could not fully fit inside the measured segment span and must be visible in QA.

## Camera Strategy Contract

In multi-board mode, E writes:

```text
sync/camera_plan.json
```

It contains one row per segment with:

- `strategy`: one of `overview`, `region`, `emphasis`, or `recovery`.
- `focusStrategy`: the zoom class used for the segment focus camera.
- `targetBbox`: the segment target/action bbox union used as a reference.
- `entryCamera`, `focusCamera`, and `exitCamera` where applicable.
- `zoomThresholds.warnAbove` and `zoomThresholds.maxAllowed`.

`combined_motion_plan.segments[]` receives `cameraStrategy` and `cameraPlan`. Bbox and D camera values remain control-layer references; E is allowed to dampen zoom and add overview/recovery phases.

## Action / Camera QA Contract

After multi-board render, E writes:

```text
sync/action_camera_qa_report.md
sync/action_camera_qa_report.json
```

The report must cover:

- action sync source and fallback status.
- rhythm compression status.
- bbox missing/out-of-bounds/near-edge status.
- camera strategy and zoom threshold status.
- keyframe manifest and contact-sheet completeness.

## Action / Camera QA Regression

Use this fast regression check after changing multi-board timing, camera, or QA behavior:

```bash
node whiteboard-infographic-video-renderer/scripts/validate_action_camera_qa.mjs
```

The script builds a temporary fixture outside the repository, reuses the public `examples/input/board/board.png` fixture, runs `render_multi_board_project.mjs` with `--skip-tts --skip-checks --skip-render`, and asserts the action rhythm, camera plan, renderer report, and action/camera QA fields. A `warn` QA status is acceptable in this smoke path because keyframe extraction is intentionally skipped.

For adversarial QA regression:

```bash
node whiteboard-infographic-video-renderer/scripts/validate_action_camera_qa.mjs --adversarial
```

This mode builds a temporary bad fixture with an unmatched spoken anchor, out-of-bounds bbox, camera zoom pressure, and intentionally skipped keyframes. It expects the renderer to complete but the QA report to return `status=fail`, with nonzero fallback, bbox, camera, and keyframe issue counts. Use this before adversarial review so the reviewer can trust that the QA gate is not only checking happy-path artifact existence.

For slower real-render regression:

```bash
node whiteboard-infographic-video-renderer/scripts/validate_action_camera_qa.mjs --real-render --quality draft --fps 8
```

This mode uses the same temporary fixture with deterministic fixture timing/audio, then runs HyperFrames lint/validate/inspect, MP4 rendering, and action keyframe extraction. It additionally asserts `video/preview.mp4`, `video/keyframes/keyframe_manifest.json`, `contact_sheet_start.jpg`, `contact_sheet_done.jpg`, and zero QA keyframe issues. Generated media stays in the temp directory only when `--keep-temp` is passed or the run fails.

## HyperFrames Requirements

- Generate a real editable HyperFrames project, not only a rendered MP4.
- Keep the board PNG as the visual layer and use `board_manifest.json` plus `motion_plan.json` as the control layer.
- In multi-board mode, switch the active board by `segment.boardId` and keep all boards in one continuous composition.
- Register `window.__timelines.main`.
- Keep audio as a separate `<audio>` clip.
- Do not use random or clock-driven animation.
- Run `lint`, `validate`, and `inspect` before render unless explicitly skipped for debugging.

## Blocking Checks

- Missing board image, manifest, plan, or voiceover segments.
- Missing target element for a motion segment.
- Missing element or annotation referenced by an action.
- Unsupported action type.
- HyperFrames `validate` failure.
- HyperFrames `inspect` failure.
- MP4 duration differs from `voiceover_timing.json.totalDuration` by more than 0.1 seconds.
- In multi-board mode, keyframe action count mismatch or missing `boardId`, `segment`, `annotation`, `type`, `element`, `drawStart`, or `drawDone` in `keyframe_manifest.json`.
- A current post-optimization run missing both `audio/word_timing.json` and `sync/action_timing.json`.
- A current multi-board post-optimization run missing `sync/camera_plan.json` or `sync/action_camera_qa_report.md`.
