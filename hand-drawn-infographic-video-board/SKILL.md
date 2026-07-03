---
name: hand-drawn-infographic-video-board
description: Create single-board or multi-board video-ready control packages for hand-drawn whiteboard infographic explainer videos. Use when Codex needs to turn board_spec.json plus board.png, or a project package with board_asset_manifest.json, infographic_plan.json, board_specs, and voiceover_segments.json, into precise board_manifest.json, motion_plan.json, annotation_manifest.json, board_index.json, SVG/HTML alignment layers, and annotation keyframe checks for cursor underline, circle, box, check, and strike effects.
---

# Hand-Drawn Infographic Video Board

## Core Rule

Do not treat a generated PNG as the animation source of truth. Use a dual-layer package:

```text
visual layer: board.png, svg_preview, or url from board_asset_manifest.json
control layer: board_manifest.json + annotation_manifest.json + motion_plan.json + optional board.svg/board.html
```

The video may show `board.png`, but cursor paths, underlines, circles, boxes, checks, strike-through marks, and camera targets must come from explicit canvas-pixel coordinates in the control layer. Never use vague regions such as "upper left area" or "around the title".

## Workflow

1. Read `references/contracts.md` before changing package shape or producing artifacts.
2. Prepare a compact `board_spec.json`. Keep only key visual objects, and give important objects stable ids.
3. Generate or provide board assets through `board_asset_manifest.json`. For local smoke tests, prefer `asset.kind=file` or `asset.kind=svg_preview`.
4. Provide `voiceover_segments.json` with segment ids, text/caption, targets, board ids, and action-level `spokenAnchor` values.
5. For legacy single-board packages, run:

```bash
python3 scripts/generate_board_package.py \
  --input path/to/board_spec.json \
  --board-image path/to/board.png \
  --voiceover path/to/voiceover_segments.json \
  --output path/to/board-package
```

6. For project/multi-board packages, run:

```bash
python3 scripts/generate_board_package.py \
  --project path/to/project-output \
  --asset-manifest path/to/project-output/board_asset_manifest.json \
  --voiceover path/to/project-output/script/voiceover_segments.json \
  --calibration-dir path/to/project-output/calibration \
  --output path/to/project-output/board
```

7. If an AI-generated PNG drifted from the control layout, generate the browser calibration helper, drag element boxes, download `<boardId>.element_bboxes.json`, place it in `calibration/`, and regenerate D:

```bash
python3 scripts/create_calibration_tool.py \
  --project path/to/project-output \
  --calibration-dir path/to/project-output/calibration \
  --output-dir path/to/project-output/calibration_tool \
  --overwrite
```

8. Inspect `package_report.md`, `board_index.json`, each board's `calibration_report.md`, `board.svg`, `board.png`, and `annotation_manifest.json`. Writing explicit `elements[*].bbox` into the matching `board_spec.json` is still supported as a legacy correction path.
9. After rendering a video, extract action-level start/done frames:

```bash
python3 scripts/extract_annotation_keyframes.py \
  --video path/to/preview.mp4 \
  --motion-plan path/to/board-package/motion_plan.json \
  --output path/to/keyframes \
  --contact-sheet
```

## Output Contract

Required files:

```text
board_spec.json
board.png
board.svg
board.html
board_manifest.json
motion_plan.json
annotation_manifest.json
image_prompt.md
calibration_report.md
```

Multi-board project output also requires:

```text
board_index.json
combined_motion_plan.json
package_report.md
board-01/
board-02/
...
```

`board_manifest.json` must include every annotatable element with:

```text
id
kind
text
bbox
camera
cursor
annotations
```

Every annotation must be one of:

```text
underline
circle
box
check
strike
```

Every `motion_plan.json` action must include:

```text
type
element
annotation
spokenAnchor
offset
duration
```

## Asset Kinds

- `file`: resolve `asset.uri` relative to `board_asset_manifest.json` first, then project root; copy local PNG assets to each board folder as `board.png`.
- `svg_preview`: treat as local file. If it is a PNG preview, copy it as `board.png`; otherwise copy it as a pass-through asset and use the board spec canvas.
- `url`: preserve the URL in `assetRef`; do not download in this Skill yet. Report it as pass-through and not locally calibrated.
- `inline_generation`: treat as visual approval metadata only. Convert it to `file` or `url` before expecting local calibration.

## Design Rules

- Preserve the hand-drawn whiteboard style: parchment background, charcoal ink, teal structure, ocean-blue annotations, amber emphasis, and occasional red warning marks.
- Make every meaningful visual object addressable with a stable `id`.
- Use board-image pixel coordinates for `bbox`, `camera`, `cursor`, and annotation geometry.
- Prefer action-level sync using `spokenAnchor`; use sentence-level timing only as a fallback for segment start/end.
- Keep the board sparse. If a script has too many visual objects, produce multiple board packages.
- Use deterministic layout as a first draft, but require manual bbox calibration when the final PNG does not match the generated control layer.
- Prefer a separate calibration layer over polluting C's semantic board specs. Each `calibration/board-01.element_bboxes.json` file should contain `boardId`, optional `canvas`, and `elements[]` with `id`, `bbox`, and optional `annotationTargetBbox`, `camera`, `cursor`, or `annotations`. D reads these files before generating `board_manifest.json`.
- In project mode, filter each board's `motion_plan.json` to that board's assigned voiceover segments. Use `infographic_plan.boards[*].sourceSegments` as the board assignment source when it conflicts with stale `voiceover_segments[*].boardId`, and record the override in `package_report.md`.

## PNG-to-Control Guidance

If the user only has a PNG and no `board_spec.json`, do not promise clean automatic SVG reconstruction. Use PNG conversion only as a fallback:

1. OCR text blocks.
2. Detect major rectangular/card regions.
3. Ask for or infer semantic labels.
4. Create `board_spec.json` with explicit element `bbox` values.
5. Regenerate `board_manifest.json`, `motion_plan.json`, and `annotation_manifest.json`.

The fallback control layer can align to the PNG, but it is not a true editable reconstruction.
