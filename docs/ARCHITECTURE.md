# Architecture

## Design Goal

The pipeline produces a reviewable project package, not just a final video file. Each stage owns one contract and hands off explicit artifacts to the next stage.

## Data Flow

```text
topic_input.txt
  -> script/
  -> infographic/
  -> creator_outputs/ + imagegen_prompts/
  -> images/*.model-generated.png
  -> board_asset_manifest.json
  -> calibration/*.element_bboxes.json
  -> board_source_for_e/
  -> audio/ + sync/ + video/
  -> integration_report.md
```

## Contract Boundaries

- B owns script shaping and voiceover segments.
- C owns semantic board planning only. C must not own final bbox, cursor, camera, or animation coordinates.
- Creator owns prompt refinement and image-generation review notes.
- The operator owns manual PNG handoff when an image tool exposes previews but no stable file path.
- D owns board-control geometry, annotation manifests, and motion plans.
- E owns measured audio timing, tokenized spoken-anchor sync, HyperFrames output, MP4 preview, and keyframes.
- The orchestrator owns run order and acceptance reporting.

## Latest Version Signals

Use the package as current only if these features are present:

- D supports `--calibration-dir`.
- D includes `scripts/create_calibration_tool.py`.
- E writes `audio/word_timing.json`.
- E writes `sync/action_timing.json`.
- E records `anchorRatioSource=sync/action_timing.json` when anchors match.
- The orchestrator acceptance criteria mention calibration and tokenized sync.

Older prototype packages may render a video but do not represent the current architecture.
