---
name: whiteboard-infographic-video-renderer
description: Generate editable HyperFrames whiteboard infographic video projects from board_manifest.json, motion_plan.json, voiceover_segments.json, and board visual assets such as board.png or asset.kind=url. Use when Codex needs to synthesize edge-tts Chinese narration, measure real segment durations, update motion timing, create captions, render MP4 previews, and extract action-level start/done keyframes for AI whiteboard explanation videos.
---

# Whiteboard Infographic Video Renderer

## Overview

Use this skill to turn a calibrated whiteboard board package into a reviewable video output: AI narration, subtitles, an editable HyperFrames project, a preview MP4, and synchronization keyframes. The renderer does not create or recalibrate the board image; it consumes the control layer produced upstream.

## Workflow

1. Read `references/contracts.md` before changing paths, JSON fields, or timing behavior.
2. Confirm the project package has `script/voiceover_segments.json`, a `board_manifest.json`, a `motion_plan.json`, and a consumable board visual asset. Single-board packages usually use `board.png`; multi-board packages may use per-board `board.png`/`asset.localPath` or `asset.kind=url`.
3. Run the bundled renderer script from this skill directory:

```bash
node scripts/render_whiteboard_project.mjs --project-dir /path/to/project-output --quality standard
```

For faster iteration:

```bash
node scripts/render_whiteboard_project.mjs --project-dir /path/to/project-output --quality draft
```

4. Check `video/renderer_report.json`, `audio/voiceover_timing.json`, `video/preview.mp4`, `video/hyperframes/`, and `video/keyframes/keyframe_manifest.json`.
5. Treat `validate` and `inspect` failures as blocking. `lint` warnings may be reported if there are no lint errors and the generated video artifacts are complete.

## Multi-Board Workflow

Use the multi-board entry when upstream D produces `board_index.json` and `combined_motion_plan.json`:

```bash
node scripts/render_multi_board_project.mjs \
  --project-dir /path/to/project-output \
  --board-root /path/to/board \
  --voiceover /path/to/voiceover_segments.json \
  --quality standard
```

Rules:

- Read `board_index.json` and `combined_motion_plan.json`.
- Treat `combined_motion_plan.json` as the full-video timeline.
- Preserve each board directory's `motion_plan.json` as a local control package; do not interpret local `start=0` values as full-video time.
- Switch the visual board by `segment.boardId`.
- Use each board's consumable visual asset as the visual layer: local `board.png`/`asset.localPath`, or `asset.kind=url` for cloud/object-storage model outputs.
- Use `board_manifest.json`, `annotation_manifest.json`, and `combined_motion_plan.json` as the control layer.

## Defaults

- TTS engine: `edge-tts`
- Voice: `zh-CN-YunxiNeural`
- Audio: segmented MP3 from edge-tts, converted to 48 kHz mono WAV, then concatenated into `audio/narration.wav`
- Captions: segment-level SRT plus bottom captions inside the HyperFrames project
- HyperFrames CLI: `npx --yes hyperframes@0.6.99`
- Output root: `audio/` and `video/` inside the project package

## Timing Rules

- Always measure real audio duration with `ffprobe`; do not trust estimated script duration.
- Build `voiceover_timing.json` from measured segment WAV files and pauses.
- Write `audio/word_timing.json` and `sync/action_timing.json` when subtitle cues are available. In the current Edge TTS path, the local runtime exposes sentence/cue timing rather than true TTS WordBoundary events, so the renderer segments each cue into token spans, matches `spokenAnchor` against those spans, and falls back to character interpolation only when token matching is unavailable. Every action records sync confidence and sync source.
- Update `motion_plan.json` or multi-board `combined_motion_plan.json` from measured timing. Single-board mode saves a one-time `.before-renderer-timing.json` backup before overwriting the source plan. Multi-board mode writes the timing-updated combined plan into the output package.
- Prefer `sync/action_timing.json` for action offsets. If no spokenAnchor match exists, fall back to `voiceover_segments.json` action `anchorRatio`; if missing, clamp the existing `motion_plan.json` offset into the measured segment span.
- Extract two keyframes for every action: `start` at `segment.start + action.offset` and `done` at `start + action.duration`.
- Start camera movement before the first action in a segment and keep the camera transition short enough that the frame is mostly settled when annotation drawing starts.

## Renderer Script

`scripts/render_whiteboard_project.mjs` accepts explicit paths when the package does not use the default layout:

```bash
node scripts/render_whiteboard_project.mjs \
  --project-dir /path/to/project-output \
  --voiceover script/voiceover_segments.json \
  --board-manifest board/board-01.board_manifest.json \
  --motion-plan board/board-01.motion_plan.json \
  --board-image infographic/images/board-01.png
```

Useful flags:

- `--dry-run`: resolve and validate inputs without writing outputs.
- `--skip-tts`: reuse existing `audio/voiceover_timing.json` or `assets/audio/voiceover_timing.json`.
- `--skip-render`: generate the HyperFrames project and run checks without rendering MP4.
- `--skip-checks`: skip HyperFrames lint/validate/inspect.
- `--skip-keyframes`: skip action keyframe extraction.
- `--voice zh-CN-XiaoxiaoNeural`: override the default voice.
- `--rate +10%`, `--pitch +0Hz`, `--volume +0%`: override edge-tts voice parameters.

## Non-Goals

- Do not generate the hand-drawn infographic image.
- Do not infer rough annotation coordinates from a PNG.
- Do not generate Jianying/CapCut drafts.
- Do not collapse the output to only MP4; the editable HyperFrames project is a required artifact.

## Validation

Validate the skill structure after edits:

```bash
python3 <codex-skill-creator>/quick_validate.py <repo-root>/whiteboard-infographic-video-renderer
```

Validate a generated HyperFrames project from inside `video/hyperframes/`:

```bash
npx --yes hyperframes@0.6.99 lint
npx --yes hyperframes@0.6.99 validate
npx --yes hyperframes@0.6.99 inspect --samples 16
```
