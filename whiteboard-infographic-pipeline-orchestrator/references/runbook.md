# End-to-End Runbook

## Natural language entry

If the user only says:

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

Treat that as a complete trigger. Extract the topic and duration, create a run folder automatically, and write the request into `topic_input.txt`.

Default run folder through the public `whiteboard-video` Skill:

```text
<current-working-directory>/whiteboard-runs/YYYYMMDD-HHMMSS-<topic-slug>/
```

Direct repository development may continue to use the ignored legacy folder:

```text
<repo-root>/orchestrator-runs/YYYYMMDD-HHMM-<topic-slug>/
```

Default topic input through `whiteboard-video`:

```text
<current-working-directory>/whiteboard-runs/YYYYMMDD-HHMMSS-<topic-slug>/topic_input.txt
```

Then continue with local setup validation. Do not ask the user to create a file manually unless the request has no usable topic.

## 0. Validate local setup

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace <repo-root> \
  --topic-input /path/to/topic-input.txt \
  --project-dir /path/to/project-output
```

Create these directories before writing outputs:

```text
script/
infographic/board_specs/
infographic/image_prompts/
creator_outputs/
imagegen_prompts/
images/
```

## 1. Run B: script package

Use `ip-cognition-script-polisher` on the topic input.

Write:

```text
script/polished_voiceover.md
script/voiceover_segments.json
script/visual_beats.json
```

Validate:

```bash
python3 ip-cognition-script-polisher/scripts/validate_script_package.py \
  --package-dir /path/to/project-output/script
```

The voiceover package should preserve the user's stance, use the six-segment order, and include downstream fields such as `boardId`, `targetElement`, `actions[]`, `spokenAnchor`, and `anchorRatio` when possible.

## 2. Run C: infographic plan

Use `ip-hand-drawn-infographic-planner` on B's script package.

Write:

```text
infographic/infographic_plan.json
infographic/board_specs/board-XX.board_spec.json
infographic/image_prompts/board-XX.prompt.md
```

Validate:

```bash
python3 ip-hand-drawn-infographic-planner/scripts/validate_infographic_plan.py \
  /path/to/project-output
```

C outputs must stay semantic. Do not add D-only exact coordinates unless you save the C-validated version separately and make the coordinate handoff explicit.

## 3. Run creator prompt pass

For each `infographic/image_prompts/board-XX.prompt.md`, use `hand-drawn-infographic-creator` style rules to write:

```text
creator_outputs/board-XX.creator_output.md
imagegen_prompts/board-XX.imagegen_prompt.txt
```

Every final image prompt should include:

- Hand-drawn whiteboard / engineer's notebook style.
- Parchment background `#faf8f3`.
- Charcoal line work `#1a2332`.
- Ocean-blue annotation color `#2d5a7b`.
- Only 1-2 semantic highlight colors.
- Negative prompt terms excluding photorealistic, 3D render, stock photo, corporate chart, smooth digital art.

## 4. Image provider and interactive fallback

Route final prompts through the provider adapter:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/generate_board_images.py \
  --project-dir /path/to/project-output \
  --provider auto
```

Exit `0` means PNGs and `board_asset_manifest.json` are ready. Exit `2` is a provider/validation failure. Exit `3` means interactive handoff is required; read the exact targets from `image_generation_report.json`.

If the generation tool only shows preview images, stop here and ask the user to download each preview image manually. Required target:

```text
/path/to/project-output/images/board-01.model-generated.png
/path/to/project-output/images/board-02.model-generated.png
/path/to/project-output/images/board-03.model-generated.png
```

Use the board IDs from `infographic/infographic_plan.json`; do not hard-code three boards if the plan has a different count.

Do not:

- Search hidden preview cache paths.
- Invent URLs.
- Use D SVG/HTML as a replacement.
- Reuse older smoke preview PNGs.
- Continue into D/E before the files exist.

After the user confirms the images are saved, rerun the router so it validates and reuses them:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/generate_board_images.py \
  --project-dir /path/to/project-output \
  --provider interactive
```

The lower-level manifest command remains available:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/write_board_asset_manifest.py \
  --project-dir /path/to/project-output \
  --overwrite
```

## 5. Optional calibration layer

If the model PNG text or layout does not match D's first-draft control layer, create:

```text
/path/to/project-output/calibration/board-01.element_bboxes.json
```

Recommended helper:

```bash
python3 hand-drawn-infographic-video-board/scripts/create_calibration_tool.py \
  --project /path/to/project-output \
  --calibration-dir /path/to/project-output/calibration \
  --output-dir /path/to/project-output/calibration_tool \
  --overwrite
```

Open `calibration_tool/index.html`, select a board and element, drag `BBox` around the whole visual object, drag `Target` around the exact text or region to annotate, click `Cursor` where the mouse should land, then download `<boardId>.element_bboxes.json` into `calibration/`.

Minimal shape:

```json
{
  "boardId": "board-01",
  "elements": [
    {
      "id": "operating_system",
      "bbox": [1120, 330, 380, 150],
      "annotationTargetBbox": [1140, 380, 330, 70],
      "camera": { "x": 1310, "y": 405, "scale": 1.18 },
      "cursor": { "x": 1450, "y": 430 }
    }
  ]
}
```

Use board-image pixel coordinates. It is acceptable to calibrate only elements that will be targeted by motion actions.

## 6. Run D: board control package

```bash
python3 hand-drawn-infographic-video-board/scripts/generate_board_package.py \
  --project /path/to/project-output \
  --asset-manifest /path/to/project-output/board_asset_manifest.json \
  --voiceover /path/to/project-output/script/voiceover_segments.json \
  --calibration-dir /path/to/project-output/calibration \
  --output /path/to/project-output/board_source_for_e
```

Inspect:

```text
board_source_for_e/package_report.md
board_source_for_e/board_index.json
board_source_for_e/combined_motion_plan.json
board_source_for_e/board-*/calibration_report.md
board_source_for_e/board-*/board.png
board_source_for_e/board-*/board_manifest.json
board_source_for_e/board-*/annotation_manifest.json
board_source_for_e/board-*/motion_plan.json
```

If annotation targets are wrong, correct the D calibration inputs and regenerate D before rendering.

## 7. Run E: renderer

Dry-run first:

```bash
node whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs \
  --project-dir /path/to/project-output \
  --board-root /path/to/project-output/board_source_for_e \
  --voiceover /path/to/project-output/script/voiceover_segments.json \
  --dry-run
```

Render:

```bash
node whiteboard-infographic-video-renderer/scripts/render_multi_board_project.mjs \
  --project-dir /path/to/project-output \
  --board-root /path/to/project-output/board_source_for_e \
  --voiceover /path/to/project-output/script/voiceover_segments.json \
  --quality standard
```

Inspect:

```text
audio/voiceover_timing.json
audio/word_timing.json
audio/captions.srt
sync/action_timing.json
sync/camera_plan.json
sync/action_camera_qa_report.md
sync/action_camera_qa_report.json
video/hyperframes/
video/preview.mp4
video/keyframes/contact_sheet_start.jpg
video/keyframes/contact_sheet_done.jpg
video/renderer_report.json
```

Prefer runs where `audio/word_timing.json` contains cue `tokens`, `combined_motion_plan.json` actions show `anchorRatioSource: "sync/action_timing.json"`, and `sync/action_timing.json` action rows use tokenized or direct cue sources rather than fallback sources. Any low-confidence or fallback sync, rhythm compression, bbox issue, camera zoom warning, or missing keyframe artifact should be recorded in `integration_report.md`.

## 8. Verify asset identity

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/check_asset_identity.py \
  --project-dir /path/to/project-output
```

If this fails, regenerate D/E from the correct manifest. Do not patch the report to claim success.

## 9. Write integration report

`integration_report.md` should include:

- Absolute output root.
- What B/C/creator/image/D/E produced.
- Validator and renderer pass/fail results.
- Image provider, automatic/manual status, source, and exact file names from `image_generation_report.json`.
- Calibration files used and unresolved alignment issues.
- Word/anchor sync confidence from `sync/action_timing.json`.
- Camera strategy and action/camera QA from `sync/camera_plan.json` and `sync/action_camera_qa_report.md`.
- Asset identity results.
- Keyframe/contact-sheet inspection.
- Known degradations and recovery notes.
- Backfill items for B/C/creator/D/E.

The report is an acceptance artifact, not a marketing summary.

## 10. Run final v1 acceptance

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /path/to/project-output
```

Do not report a real run as complete unless `v1_release_acceptance.json` says `PASS`.
