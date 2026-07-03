# Board Package Contracts

Coordinates are always board canvas pixels. When `board.png` is provided, its width and height define the canvas. The PNG, SVG, manifest, cursor, and annotation overlay must share the same coordinate system.

## Project Mode Inputs

Project/multi-board mode reads:

```text
project/
├── board_asset_manifest.json
├── infographic/
│   ├── infographic_plan.json
│   └── board_specs/
│       ├── board-01.board_spec.json
│       ├── board-02.board_spec.json
│       └── board-03.board_spec.json
└── script/
    └── voiceover_segments.json
```

Run:

```bash
python3 scripts/generate_board_package.py \
  --project project \
  --asset-manifest project/board_asset_manifest.json \
  --voiceover project/script/voiceover_segments.json \
  --output project/board
```

Each board gets its own control package. The root output gets `board_index.json`, `combined_motion_plan.json`, and `package_report.md`.

## `board_spec.json`

Authoring input. Keep it semantic and compact. Prefer `sections` for generated first drafts, or explicit `elements` when aligning to an existing PNG.

```json
{
  "id": "board-01",
  "title": "AI 时代个人 IP 内容工作流",
  "subtitle": "从输入材料到可沉淀 Skill",
  "canvas": { "width": 1920, "height": 1080 },
  "sections": [
    {
      "id": "inputs",
      "title": "输入材料",
      "items": ["成交案例", "客户问题", "参考视频"],
      "actions": ["underline", "circle"]
    }
  ],
  "elements": [
    {
      "id": "core_boundary",
      "kind": "emphasis_box",
      "text": "先定边界",
      "bbox": [1180, 520, 360, 92],
      "actions": ["box", "underline"],
      "annotationTargetBbox": [1225, 545, 270, 44]
    }
  ]
}
```

Rules:

- `id` must be lowercase letters, digits, hyphens, or underscores.
- Explicit `elements[*].bbox` is required when the final PNG no longer matches the generated layout.
- `annotationTargetBbox` is the precise text/shape bbox used for marks. If omitted, the element `bbox` is used.
- Supported annotation actions are `underline`, `circle`, `box`, `check`, and `strike`.
- Legacy `highlight`, `point`, `zoom`, `frame`, and `rect` may be accepted as aliases, but output must normalize to the supported action types.

## `voiceover_segments.json`

Speech-to-motion input. Use top-level `segments`.

```json
{
  "topic": "为什么 AI 工作流要先定边界",
  "segments": [
    {
      "id": "boundary",
      "start": 8.2,
      "speechEnd": 13.4,
      "end": 13.6,
      "caption": "真正提高效率的第一步，是先定清楚 AI 工作流的边界。",
      "boardId": "board-01",
      "target": "core_boundary",
      "actions": [
        {
          "type": "box",
          "element": "core_boundary",
          "spokenAnchor": "先定清楚",
          "anchorRatio": 0.42,
          "duration": 0.8
        }
      ]
    }
  ]
}
```

Rules:

- `target` or action-level `element` must match an element id in `board_manifest.json`.
- Every action must have or infer a non-empty `spokenAnchor`; production inputs should provide it explicitly.
- `offset` is seconds after segment `start`. If absent, the generator may derive it from `anchorRatio` or the anchor's character position in `caption`.
- `start`, `speechEnd`, and `end` should come from real TTS/audio timing when available.
- In project mode, `infographic_plan.boards[*].sourceSegments` may override stale `segments[*].boardId`. Record overrides in `package_report.md`.

## `board_asset_manifest.json`

Bridge from creator/image generation to D/E. D must not assume every board image lives at a fixed `board.png` path.

```json
{
  "version": "0.1",
  "assetContract": {
    "allowedKinds": ["file", "url", "inline_generation", "svg_preview"]
  },
  "boards": [
    {
      "boardId": "board-01",
      "title": "工具越多，不等于产出越多",
      "asset": {
        "kind": "file",
        "uri": "images/board-01.local-preview.png",
        "width": 1536,
        "height": 864,
        "sourcePrompt": "imagegen_prompts/board-01.imagegen_prompt.txt",
        "creatorOutput": "creator_outputs/board-01.creator_output.md"
      }
    }
  ]
}
```

Rules:

- `file`: resolve `asset.uri` relative to the manifest path first, then project root. Copy local PNG assets to the board package as `board.png`.
- `svg_preview`: handle as a local file. PNG previews become `board.png`; non-PNG previews are copied as pass-through assets and reported as not PNG-calibrated.
- `url`: preserve the URL in `assetRef.uri` and `assetRef.remoteUrl`. D does not download it yet; report it as pass-through and not locally calibrated.
- `inline_generation`: keep as visual approval metadata only. Convert to `file` or `url` before using it as the visual layer.
- Every output `board_manifest.json` must include `assetRef` with the source manifest, board id, kind, uri, `remoteUrl` for URL assets, and local path when available.

## `board_manifest.json`

Machine contract for camera and annotation control. Every object that can be pointed at, circled, boxed, checked, underlined, or struck must be present.

```json
{
  "canvas": { "width": 1920, "height": 1080 },
  "source_image": "board.png",
  "coordinate_system": "board-image-pixels",
  "elements": [
    {
      "id": "core_boundary",
      "kind": "emphasis_box",
      "text": "先定边界",
      "bbox": [1180, 520, 360, 92],
      "camera": { "x": 1360, "y": 566, "scale": 1.35 },
      "cursor": { "x": 1475, "y": 574 },
      "annotationTargetBbox": [1225, 545, 270, 44],
      "annotations": {
        "box_core_boundary": {
          "type": "box",
          "targetTextBbox": [1225, 545, 270, 44],
          "boxBounds": [1203, 534, 314, 66],
          "cursorStart": [1203, 534],
          "cursorEnd": [1517, 582]
        }
      }
    }
  ]
}
```

Rules:

- `bbox` is `[x, y, width, height]`.
- Every annotatable element must have `bbox`, `camera`, `cursor`, and `annotations`.
- Annotation geometry must be exact numeric coordinates, not rough regions.
- Annotation ids must be stable because `motion_plan.json` actions reference them.
- `camera` is D's calibrated control-layer camera reference. E may generate a renderer-level `sync/camera_plan.json` with overview, region, emphasis, and recovery strategies, but it should not require D to stop emitting calibrated element cameras.

## `annotation_manifest.json`

Flattened annotation index for renderers and QA.

```json
{
  "canvas": { "width": 1920, "height": 1080 },
  "source_image": "board.png",
  "supportedTypes": ["underline", "circle", "box", "check", "strike"],
  "annotations": [
    {
      "id": "box_core_boundary",
      "type": "box",
      "element": "core_boundary",
      "usedInMotionPlan": true,
      "bbox": [1180, 520, 360, 92],
      "camera": { "x": 1360, "y": 566, "scale": 1.35 },
      "cursor": { "x": 1475, "y": 574 },
      "targetTextBbox": [1225, 545, 270, 44],
      "boxBounds": [1203, 534, 314, 66],
      "cursorStart": [1203, 534],
      "cursorEnd": [1517, 582]
    }
  ]
}
```

Use this file to audit whether every planned action has exact coordinates before rendering.

## `motion_plan.json`

Audio-to-motion contract. It follows the v0.5 structure but must not hardcode v0.5 content.

```json
{
  "sync_level": "voiceover-segment-action",
  "composition": { "width": 1920, "height": 1080, "duration": 28.4 },
  "overview_camera": { "x": 960, "y": 540, "scale": 1.0 },
  "segments": [
    {
      "id": "boundary",
      "start": 8.2,
      "speechEnd": 13.4,
      "end": 13.6,
      "caption": "真正提高效率的第一步，是先定清楚 AI 工作流的边界。",
      "boardId": "board-01",
      "target": "core_boundary",
      "camera": { "x": 1360, "y": 566, "scale": 1.35 },
      "actions": [
        {
          "type": "box",
          "element": "core_boundary",
          "annotation": "box_core_boundary",
          "spokenAnchor": "先定清楚",
          "offset": 2.18,
          "duration": 0.8
        }
      ]
    }
  ]
}
```

Rules:

- `sync_level` must be `voiceover-segment-action` for action-level annotation timing.
- Every action must bind `spokenAnchor`, `element`, and `annotation`.
- `annotation` must exist in `board_manifest.json` and `annotation_manifest.json`.
- Camera-only segments may have `actions: []`, but annotation segments may not omit action coordinates.
- Segment `camera` is an initial focus reference. In current multi-board E renders, final camera movement is strategyized after measured audio timing and recorded in `sync/camera_plan.json`.

## `board_index.json`

Root index for E and later handoff steps.

```json
{
  "version": "0.1",
  "sources": {
    "assetManifest": "project/board_asset_manifest.json",
    "voiceoverSegments": "project/script/voiceover_segments.json",
    "infographicPlan": "project/infographic/infographic_plan.json"
  },
  "boards": [
    {
      "boardId": "board-01",
      "path": "board-01",
      "asset": {
        "kind": "file",
        "uri": "images/board-01.local-preview.png",
        "localPath": "board.png"
      },
      "counts": {
        "elements": 5,
        "annotations": 14,
        "motionSegments": 2,
        "motionActions": 3
      }
    }
  ],
  "combinedMotionPlan": "combined_motion_plan.json",
  "packageReport": "package_report.md"
}
```

## `combined_motion_plan.json`

Combined root-level motion index. It does not replace per-board motion plans; it lets E read all boards and all segments in timeline order.

Rules:

- `segments[*].boardId` must match one generated board directory.
- Every segment action must still include `type`, `element`, `annotation`, `spokenAnchor`, `offset`, and `duration`.
- Per-board `motion_plan.json` must include only segments assigned to that board.

## `image_prompt.md`

Prompt bridge to the hand-drawn infographic visual workflow. It must describe the same layout as `board_spec.json`, keep content sparse, and explicitly ask not to copy the whole voiceover into the board.

## Layering In Video

Recommended stack:

```text
camera wrapper
  board.png              visual texture layer
  board.svg              hidden or low-opacity alignment layer
  annotation overlay     cursor/underline/circle/box/check/strike effects
caption layer
audio layer
```

## Keyframe QA

After render, use `scripts/extract_annotation_keyframes.py` to extract two frames for each action:

- `start`: `segment.start + action.offset`
- `done`: `segment.start + action.offset + action.duration`

Review the contact sheets and `keyframe_manifest.json`; if a mark does not align, update explicit bboxes in `board_spec.json` and regenerate.
