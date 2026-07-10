# Pipeline Contracts

## Module boundaries

The orchestrator keeps the successful B/C/creator/image/D/E boundaries intact:

- **B `ip-cognition-script-polisher`** owns script shaping and writes `script/polished_voiceover.md`, `script/voiceover_segments.json`, and `script/visual_beats.json`.
- **C `ip-hand-drawn-infographic-planner`** owns semantic planning and writes `infographic/infographic_plan.json`, `infographic/board_specs/*.board_spec.json`, and `infographic/image_prompts/*.prompt.md`. C must not own bbox, camera, cursor, or annotation coordinates.
- **`hand-drawn-infographic-creator`** owns creator-facing prompt/spec text and final image generation prompts. It does not guarantee a stable file path.
- **Image provider handoff** owns automatic PNG persistence through OpenAI or a command adapter, with preview-only output falling back to manual files under `images/`.
- **D `hand-drawn-infographic-video-board`** owns control-layer files: `board_manifest.json`, `annotation_manifest.json`, `motion_plan.json`, `combined_motion_plan.json`, and per-board `board.png`.
- **E `whiteboard-infographic-video-renderer`** owns real audio timing, captions, HyperFrames, preview MP4, keyframes, and renderer reports.

## Canonical project tree

```text
project-output/
├── script/
├── infographic/
├── creator_outputs/
├── imagegen_prompts/
├── images/
├── image_generation_report.json
├── calibration/
├── board_asset_manifest.json
├── board_source_for_e/
├── audio/
├── sync/
├── video/
├── integration_report.md
├── v1_release_acceptance.json
└── v1_release_acceptance.md
```

Use `board_source_for_e/` as D's output and E's input. E may write its own `project-output/board/` copy.

## `board_asset_manifest.json`

`board_asset_manifest.json` is the gate between model image generation and D/E. Only confirmed real model-generated board images may enter D/E.

Minimum shape:

```json
{
  "version": "0.1",
  "assetContract": {
    "allowedKinds": ["file", "url", "inline_generation", "svg_preview"],
    "rule": "Only confirmed real model-generated image assets may enter D/E."
  },
  "generationRun": {
    "mode": "built-in image_gen preview with manual download",
    "previewChecked": true,
    "checkedAt": "YYYY-MM-DD",
    "notes": []
  },
  "boards": [
    {
      "boardId": "board-01",
      "title": "Board title",
      "asset": {
        "kind": "file",
        "uri": "images/board-01.model-generated.png",
        "width": 1672,
        "height": 941,
        "sourcePrompt": "imagegen_prompts/board-01.imagegen_prompt.txt",
        "creatorOutput": "creator_outputs/board-01.creator_output.md",
        "previewCheck": "confirmed model-generated board for this run; not D SVG and not old smoke preview"
      }
    }
  ]
}
```

For local runs, `asset.kind` must be `file` before D/E. Automatic runs use a mode such as `auto:openai:gpt-image-2` with `previewChecked=false`; interactive runs keep the manual-download mode with `previewChecked=true`. `inline_generation` is metadata only and is not consumable by D/E. `svg_preview` is not allowed as a substitute for the requested model-generated PNG in this pipeline.

## `image_generation_report.json`

The provider router writes this report before D/E. Required fields are:

```json
{
  "schemaVersion": 1,
  "status": "complete",
  "providerRequested": "auto",
  "providerResolved": "openai",
  "automatic": true,
  "boards": [
    {
      "boardId": "board-01",
      "promptPath": "imagegen_prompts/board-01.imagegen_prompt.txt",
      "outputPath": "images/board-01.model-generated.png",
      "status": "generated",
      "width": 1536,
      "height": 1024
    }
  ],
  "manifestPath": "board_asset_manifest.json"
}
```

Allowed top-level statuses are `dry_run`, `handoff_required`, `complete`, and `failed`. Do not enter D/E unless the status is `complete` and the manifest exists. Reports may name the API-key environment variable and whether it is present, but must never contain the key value.

## Image naming

The automatic and manual target is:

```text
project-output/images/<boardId>.model-generated.png
```

Examples:

```text
images/board-01.model-generated.png
images/board-02.model-generated.png
images/board-03.model-generated.png
```

The scripts validate PNG signature and dimensions. Automatic providers also record their resolved provider and model; interactive runs still require the operator to confirm the preview source manually.

## D input contract

Run D in project mode:

```bash
python3 hand-drawn-infographic-video-board/scripts/generate_board_package.py \
  --project /path/to/project-output \
  --asset-manifest /path/to/project-output/board_asset_manifest.json \
  --voiceover /path/to/project-output/script/voiceover_segments.json \
  --calibration-dir /path/to/project-output/calibration \
  --output /path/to/project-output/board_source_for_e
```

Required D outputs:

```text
board_source_for_e/
├── board_index.json
├── combined_motion_plan.json
├── package_report.md
└── board-*/
    ├── board.png
    ├── board_manifest.json
    ├── annotation_manifest.json
    └── motion_plan.json
```

If generated board text drifts from C prompt text, preserve both:

- `spokenAnchor` remains the voiceover sync anchor.
- D calibration records the actual visible text and bbox on the PNG.

## Calibration handoff

When the generated PNG does not match D's deterministic first-draft layout, create one JSON file per affected board:

```text
calibration/<boardId>.element_bboxes.json
```

Recommended helper:

```bash
python3 hand-drawn-infographic-video-board/scripts/create_calibration_tool.py \
  --project /path/to/project-output \
  --calibration-dir /path/to/project-output/calibration \
  --output-dir /path/to/project-output/calibration_tool \
  --overwrite
```

Minimal shape:

```json
{
  "boardId": "board-01",
  "elements": [
    {
      "id": "main_point",
      "bbox": [200, 180, 520, 140],
      "annotationTargetBbox": [230, 220, 460, 70],
      "camera": { "x": 460, "y": 250, "scale": 1.16 },
      "cursor": { "x": 650, "y": 260 }
    }
  ]
}
```

C remains semantic. Calibration belongs to D or a D handoff file.

## E input contract

Run E in multi-board mode:

```bash
node whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs \
  --project-dir /path/to/project-output \
  --board-root /path/to/project-output/board_source_for_e \
  --voiceover /path/to/project-output/script/voiceover_segments.json \
  --quality standard
```

Required E outputs:

```text
audio/narration.wav
audio/voiceover_timing.json
audio/word_timing.json
audio/captions.srt
sync/action_timing.json
sync/camera_plan.json
sync/action_camera_qa_report.md
sync/action_camera_qa_report.json
video/hyperframes/
video/preview.mp4
video/keyframes/
video/renderer_report.json
```

E must measure actual audio duration with `ffprobe` and update timing from real audio. Estimated script duration is not enough.

Current sync granularity is `spokenAnchor-cue-tokenized`: the renderer uses Edge TTS WebVTT cue timing plus `Intl.Segmenter` token spans. If a real WordBoundary or forced-alignment source is added later, it should replace `audio/word_timing.json` without changing the D/E handoff contract.

Current multi-board action rhythm is renderer-owned: `sync/action_timing.json` and the timing-updated `board/combined_motion_plan.json` carry early cursor arrival, draw start, hold-after, light staggering, and compression-to-fit metadata.

Current multi-board camera strategy is renderer-owned: `sync/camera_plan.json` records `overview`, `region`, `emphasis`, and `recovery` segment strategies. D camera and bbox fields remain references; E dampens final zoom and records threshold status in QA.

`sync/action_camera_qa_report.md` and `.json` must summarize sync source/fallbacks, rhythm compression, bbox boundary status, camera zoom threshold status, and keyframe artifact completeness.

## Asset identity contract

After D/E, each board must pass this identity chain:

```text
images/<boardId>.model-generated.png
  == board_source_for_e/<boardId>/board.png
  == video/hyperframes/assets/boards/<boardId>/board.png
```

Use:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/check_asset_identity.py \
  --project-dir /path/to/project-output
```

Do not report that the video used the model images unless this check passes.
