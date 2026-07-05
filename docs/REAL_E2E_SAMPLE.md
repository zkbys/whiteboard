# Real End-to-End Sample

This document records the latest local real end-to-end acceptance sample. Generated videos, audio, PNGs, contact sheets, and run directories remain ignored by Git.

## Latest Local Run

Run date: 2026-07-05

Ignored run directory:

```text
orchestrator-runs/20260705-action-camera-real-e2e
```

Primary local artifacts:

- `orchestrator-runs/20260705-action-camera-real-e2e/video/preview.mp4`
- `orchestrator-runs/20260705-action-camera-real-e2e/integration_report.md`
- `orchestrator-runs/20260705-action-camera-real-e2e/sync/action_camera_qa_report.md`
- `orchestrator-runs/20260705-action-camera-real-e2e/video/keyframes/contact_sheet_start.jpg`
- `orchestrator-runs/20260705-action-camera-real-e2e/video/keyframes/contact_sheet_done.jpg`

## Scope

The sample runs the current pipeline with:

- B script package validation.
- C semantic infographic plan validation.
- Generated board PNG handoff into `images/`.
- Manual bbox calibration JSON for the generated PNGs.
- D board-control package generation.
- E multi-board rendering with real Edge TTS narration on the first render.
- E rerender with `--skip-tts` after fixing one rhythm-compression warning.
- Renderer action rhythm, camera plan, action/camera QA, MP4 preview, and keyframe extraction.
- Asset identity check from `images/` to D `board.png` to HyperFrames assets.

## Acceptance Snapshot

Final sample result:

- Boards: 2
- Voiceover segments: 6
- Annotation actions: 9
- Rendered preview duration: 42.581333 seconds
- Timing duration: 42.536 seconds
- Duration delta: 0.045 seconds
- Sync source: `cue-tokenized`
- Matched actions: 9
- Fallback actions: 0
- Average sync confidence: 0.9
- Action/camera QA status: `pass`
- Rhythm compressed actions: 0
- Bbox issues: 0
- Camera warnings: 0
- Keyframe issues: 0
- Keyframe artifacts: manifest, start contact sheet, and done contact sheet present
- Asset identity: pass for both boards

Camera behavior exercised:

- Segment strategies: `overview`, `emphasis`, `recovery`
- Region focus: used inside overview/recovery camera planning
- Zoom threshold: all segments passed under `warnAbove=1.35` and `maxAllowed=1.7`

## Reproduction Notes

The sample was created in an ignored run directory, so the exact generated PNGs and media are not committed. To reproduce a comparable run:

1. Create or copy a valid B script package into a new ignored run directory.
2. Create a valid C plan with board specs and image prompts.
3. Generate board PNGs and save them under `images/`.
4. Write `board_asset_manifest.json`.
5. Add calibration JSON when model PNG layout differs from the board spec.
6. Run D `generate_board_package.py`.
7. Run E `render_multi_board_project.mjs`.
8. Inspect `sync/action_camera_qa_report.json`, `video/renderer_report.json`, and contact sheets.
9. Run the asset identity checker.
10. Write an `integration_report.md` in the ignored run directory.

## Known Non-Blocking Warnings

The sample records these non-blocking warnings:

- HyperFrames `composition_file_too_large`.
- HyperFrames `font_family_without_font_face` for local Chinese font-family names.
- Node ExperimentalWarning from npm internals.
- Model-generated board text is visually usable but not guaranteed to match every requested character exactly.

These warnings do not block this sample because renderer validation, layout inspection, action/camera QA, keyframe extraction, preview rendering, and asset identity all passed.
