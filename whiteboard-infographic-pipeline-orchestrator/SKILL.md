---
name: whiteboard-infographic-pipeline-orchestrator
description: Orchestrate the AI whiteboard infographic explainer video pipeline from a natural-language user request or a topic/script input file into a validated project package. Use when the user says things like "请使用白板总编排skill帮我做一个视频", "白板总编排 Skill", "用白板信息图流水线做视频", gives a topic such as "主题为..." and a duration such as "30-60秒左右", or asks Codex to make an AI 白板信息图讲解视频. Coordinate ip-cognition-script-polisher, ip-hand-drawn-infographic-planner, hand-drawn-infographic-creator, automatic or interactive model-image handoff, hand-drawn-infographic-video-board, and whiteboard-infographic-video-renderer to produce script assets, infographic plans, creator prompts, board_asset_manifest.json, board control packages, AI narration, captions, HyperFrames, preview.mp4, keyframes, and integration_report.md without substituting placeholder images.
---

# Whiteboard Infographic Pipeline Orchestrator

## 使用场景

Use this skill when the user wants a complete AI 白板信息图讲解视频流水线 run from a topic text file, not another isolated B/C/D/E test. The expected result is a reviewable project directory containing the script package, infographic planning package, model-generated board images, D control package, E rendered video package, and an integration report.

This skill is an orchestrator. It does not replace the existing module Skills. It calls or guides them in a fixed order and enforces the fragile handoff rules between them.

## 自然语言一键入口

If the user gives a request like:

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

Start the pipeline directly. Do not ask the user to prepare a separate input file.

Extract:

- `topic`: text inside `主题为...`, quoted text, or the clearest stated idea.
- `targetDurationSec`: if the user says `30-60秒`, keep B's normal 30-60 second range and default target to about 45 seconds.
- `style`: default to `IP孵化/商业认知/AI认知类短视频` unless the user states another style.

When this internal module is called through the public `whiteboard-video` Skill, create the run folder under the user's current working directory:

```text
whiteboard-runs/YYYYMMDD-HHMMSS-<topic-slug>/
```

For direct repository development runs, the legacy ignored location remains available:

```text
orchestrator-runs/YYYYMMDD-HHMM-<topic-slug>/
```

Inside it, write the user's request into:

```text
topic_input.txt
```

Then run the normal pipeline using that file as `--topic-input` and the run folder as `--project-dir`. Only ask a clarification if the request has no usable topic or gives mutually incompatible requirements. The manual image-download pause applies only when no automatic provider is configured or provider output fails validation.

## 输入要求

Required:

- Either a natural-language user request containing the topic, or a topic/source-script text file.
- A project output directory for one run. Through `whiteboard-video`, default to `<current-working-directory>/whiteboard-runs/`; direct repository development may use ignored `orchestrator-runs/`.
- The local module Skill folders in the same workspace:
  - `ip-cognition-script-polisher/`
  - `ip-hand-drawn-infographic-planner/`
  - `hand-drawn-infographic-creator/`
  - `hand-drawn-infographic-video-board/`
  - `whiteboard-infographic-video-renderer/`

Before running the pipeline, validate inputs:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace <repo-root> \
  --topic-input /path/to/topic.txt \
  --project-dir /path/to/project-output
```

## 输出目录结构

Create or update the project output directory with this shape:

```text
project-output/
├── script/
│   ├── polished_voiceover.md
│   ├── voiceover_segments.json
│   └── visual_beats.json
├── infographic/
│   ├── infographic_plan.json
│   ├── board_specs/*.board_spec.json
│   └── image_prompts/*.prompt.md
├── creator_outputs/*.creator_output.md
├── imagegen_prompts/*.imagegen_prompt.txt
├── images/*.model-generated.png
├── image_generation_report.json
├── calibration/*.element_bboxes.json
├── board_asset_manifest.json
├── sync/action_timing.json
├── sync/camera_plan.json
├── sync/action_camera_qa_report.md
├── sync/action_camera_qa_report.json
├── board_source_for_e/
│   ├── board_index.json
│   ├── combined_motion_plan.json
│   └── board-*/board.png
├── audio/
├── video/
│   ├── hyperframes/
│   ├── preview.mp4
│   ├── renderer_report.json
│   ├── keyframes/contact_sheet_start.jpg
│   └── keyframes/contact_sheet_done.jpg
└── integration_report.md
```

Use `board_source_for_e/` as D's output that E reads. Do not point E's `--board-root` at `project-output/board` while E is writing `project-output/board`; the successful integration found that this can delete or overwrite the input board package.

## 固定顺序

1. **B script package**: Use `ip-cognition-script-polisher` to convert the topic input into `script/polished_voiceover.md`, `script/voiceover_segments.json`, and `script/visual_beats.json`. Validate with B's `validate_script_package.py`.
2. **C infographic planning**: Use `ip-hand-drawn-infographic-planner` to create `infographic/infographic_plan.json`, `infographic/board_specs/*.board_spec.json`, and `infographic/image_prompts/*.prompt.md`. Validate with C's `validate_infographic_plan.py`.
3. **Creator outputs**: Use `hand-drawn-infographic-creator` style rules to turn each C prompt into `creator_outputs/board-XX.creator_output.md` and a final `imagegen_prompts/board-XX.imagegen_prompt.txt`.
4. **Image provider route**: Run `scripts/generate_board_images.py --project-dir <project> --provider auto`. A configured provider writes and validates PNGs directly; otherwise it returns `3` with exact manual handoff paths in `image_generation_report.json`.
5. **Manifest**: Automatic completion writes `board_asset_manifest.json`. After an interactive download, rerun the provider router or `write_board_asset_manifest.py` to validate the PNGs and write the manifest.
6. **Calibration layer (auto, then manual if needed)**: Run `hand-drawn-infographic-video-board/scripts/auto_calibrate.py` to detect element bboxes from the actual PNGs. `--provider auto` prefers the `agent` backend (Claude vision via `ANTHROPIC_AUTH_TOKEN`) when no `OPENAI_API_KEY` is configured, then VLM, OCR, and mock. If it exits `0`, proceed to D. If it exits `3`, open the generated `calibration_tool/index.html`, adjust pre-filled boxes, save `calibration/<boardId>.element_bboxes.json`, and rerun auto-calibrate or proceed directly to D.
7. **D board control package**: Use `hand-drawn-infographic-video-board` with the project package, `board_asset_manifest.json`, and any `calibration/` files to create `board_source_for_e/`.
8. **E renderer**: Use `whiteboard-infographic-video-renderer` multi-board mode to create narration, measured timing, `audio/word_timing.json`, `sync/action_timing.json`, renderer action rhythm, `sync/camera_plan.json`, action/camera QA, captions, HyperFrames, preview MP4, and keyframes.
9. **Identity check and report**: Run `check_asset_identity.py`, inspect keyframes, and write `integration_report.md`.
10. **V1 release acceptance**: Run `validate_release_candidate.py`. A real run is complete only when it writes PASS `v1_release_acceptance.json` and `.md`.

## 生图 provider 与人工下载暂停点

Use automatic output only when `image_generation_report.json` has `status=complete` and every PNG passes validation. When the built-in image generation tool gives only preview images, this remains a hard rule:

- Do not search for hidden local paths.
- Do not invent or guess URLs.
- Do not use D-generated SVG/HTML as a substitute visual layer.
- Do not reuse old smoke preview images.
- Do not continue into D/E with placeholders.
- Pause and tell the user exactly where to save the images and how to name them.

Required naming:

```text
project-output/images/board-01.model-generated.png
project-output/images/board-02.model-generated.png
project-output/images/board-03.model-generated.png
```

Use the actual board IDs from `infographic/infographic_plan.json`. If there are two boards, require only `board-01` and `board-02`; if there are more, require all of them. After the user confirms the files are present, run:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/write_board_asset_manifest.py \
  --project-dir /path/to/project-output \
  --overwrite
```

## 不允许的行为

- Do not collapse the pipeline into an MP4-only output; the editable HyperFrames project is required.
- Do not replace measured audio timing with estimated script timing.
- Do not let C produce final animation coordinates; C stays semantic. Bbox/camera/cursor calibration belongs to D or a D handoff file.
- Do not let D's generated SVG/HTML become the video background when real model PNGs are required.
- Do not treat `asset.kind=inline_generation` as a consumable video asset. Convert it to `file` after manual download or to a verified `url` if a real stable URL exists.
- Do not proceed when `board_asset_manifest.json` points at missing, non-PNG, zero-byte, or wrong-board files.
- Do not claim the video used the model image unless `check_asset_identity.py` passes.

## 验收标准

A run is complete only when all of these are true:

- B validator passes on `script/`.
- C validator passes on `infographic/`.
- `board_asset_manifest.json` uses `asset.kind=file` for local model PNGs and references `images/*.model-generated.png`.
- `image_generation_report.json` records `complete` for automatic mode or the resolved interactive handoff before D/E.
- D produces `board_source_for_e/board_index.json`, `combined_motion_plan.json`, and per-board `board_manifest.json`, `annotation_manifest.json`, `motion_plan.json`, and `board.png`.
- E produces `audio/narration.wav`, `audio/voiceover_timing.json`, `audio/captions.srt`, `sync/camera_plan.json`, `sync/action_camera_qa_report.md`, `sync/action_camera_qa_report.json`, `video/hyperframes/`, `video/preview.mp4`, `video/keyframes/`, and `video/renderer_report.json`.
- HyperFrames lint/validate/inspect have no blocking errors.
- MP4 duration and measured timing are within E's threshold.
- `audio/word_timing.json` contains cue token spans, `sync/action_timing.json` exists, and most actions use `anchorRatioSource=sync/action_timing.json`; low-confidence matches, rhythm compression, bbox issues, camera zoom thresholds, and missing keyframe artifacts are reported instead of hidden.
- If visual alignment is off, `calibration/<boardId>.element_bboxes.json` exists for the affected board and D reports the calibration file in `calibration_report.md`.
- `check_asset_identity.py` confirms manifest PNG -> D `board.png` -> HyperFrames `board.png` are identical for every board.
- `integration_report.md` records pass/fail results, asset source, known degradations, keyframe inspection, and next backfill items.
- `validate_release_candidate.py` probes final audio/video and enforces the cross-stage v1 contract.

## 常见失败和恢复方式

- **No automatic provider or preview-only output**: Stop. Read the exact targets from `image_generation_report.json`, ask the user to save every PNG, then rerun the provider router.
- **Automatic provider fails**: Keep `status=failed`, preserve any validated earlier PNGs for resume, fix the provider/configuration, and rerun without claiming success.
- **Chinese text drift in generated images**: Record the drift in `board_asset_manifest.json` notes and D calibration. Preserve voiceover anchors separately from actual image text.
- **C semantic spec lacks bbox**: Keep the C-validated semantic spec as backup, then provide D with calibrated bbox data or a post-image calibration handoff. Do not make C own exact coordinates.
- **D image and control layer drift**: Correct element bboxes in the D input spec and regenerate D. Do not fake keyframe alignment in the report.
- **E deletes or overwrites input board package**: Use separate `board_source_for_e/` input and let E write its own `project-output/board/` output.
- **Video uses wrong image**: Run `check_asset_identity.py`; if it fails, regenerate D/E from the fixed `board_asset_manifest.json` before reporting success.

## References

- Read `references/contracts.md` when checking file contracts, board asset schema, and module boundaries.
- Read `references/runbook.md` when executing a run end to end.
- Use `scripts/validate_orchestrator_inputs.py` before starting a run.
- Use `scripts/generate_board_images.py` after Creator prompts to select automatic or interactive image handling.
- Use `scripts/write_board_asset_manifest.py` after the manual image download pause.
- Use `scripts/check_asset_identity.py` after D/E to prove the rendered project used the manifest PNGs.
- Use `scripts/validate_release_candidate.py` last; smoke-mode warnings are not real-release acceptance.
