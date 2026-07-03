---
name: ip-hand-drawn-infographic-planner
description: Plan concise hand-drawn infographic inputs for IP incubation, business cognition, and AI cognition whiteboard explainer videos. Use when Codex needs to convert polished_voiceover.md, voiceover_segments.json, or visual_beats.json into infographic/infographic_plan.json, board_specs/*.json, and image_prompts/*.prompt.md for hand-drawn-infographic-creator without rendering images, writing board coordinates, or producing video.
---

# IP Hand-Drawn Infographic Planner

## Overview

Turn polished short-video voiceover and visual beats into a compact hand-drawn infographic plan. The output prepares structured inputs for `hand-drawn-infographic-creator` and the later video board control layer.

## Non-Goals

- Do not generate PNGs, videos, audio, subtitles, or HyperFrames projects.
- Do not replace `hand-drawn-infographic-creator`; only prepare its prompt-level inputs.
- Do not write `board_manifest.json`, `motion_plan.json`, `bbox`, `camera`, `cursor`, or annotation coordinates.
- Do not copy the voiceover sentence by sentence onto the board.

## Required Inputs

Prefer a project package with:

```text
script/
├── polished_voiceover.md
├── voiceover_segments.json
└── visual_beats.json
```

If only prose voiceover is available, first segment it into stable segment ids and visual beats before writing infographic outputs.

## Workflow

1. Read `references/schema.md` before writing outputs.
2. Read `references/business-cognition-diagram-patterns.md` before deciding board count and diagram type.
3. Read `references/hand-drawn-prompt-bridge.md` before writing image prompts.
4. Extract the one core thesis and the few visual beats that actually need a board.
5. Decide board count:
   - Use one board for one thesis, one contrast, or up to 5 key objects.
   - Use two boards when the voiceover has two separate jobs, usually problem framing plus method/checklist.
   - Use three boards only when the script is longer than the normal 30-60 second package or has clearly separate concepts.
6. For each board, keep `contentDensity` as `simple`, set `maxKeyObjects` to 3-5, and give every key object a stable semantic `id`.
7. Write:

```text
infographic/
├── infographic_plan.json
├── board_specs/
│   └── board-01.board_spec.json
└── image_prompts/
    └── board-01.prompt.md
```

8. Run the validator:

```bash
python3 ip-hand-drawn-infographic-planner/scripts/validate_infographic_plan.py <project-output>
```

## Planning Rules

- Each board carries one main point, not a transcript.
- Each prompt must include this exact sentence: `内容简洁一点，不要逐字写满口播`.
- Use style vocabulary from `hand-drawn-infographic-creator`: `continuous line art`, `engineer's notebook sketch with annotations in margins`, `whiteboard explanation aesthetic`, `ink on parchment`.
- Use the hand-drawn palette: parchment `#faf8f3`, charcoal `#1a2332`, ocean-blue annotations `#2d5a7b`, and only 1-2 semantic highlight colors per board.
- Use coral `#e63946` for risk/problem, teal `#4a9d9e` for active/positive, and amber `#f4a261` for progress/insight.
- Key object ids must be lowercase, stable, semantic, and reusable by downstream control-layer Skills, for example `workflow_asset`, not `left_box_1`.
- Keep board specs semantic. Use layout zones such as `left_panel` or `bottom_takeaway`; do not use exact coordinates.

## Resources

- `references/schema.md`: output schema and validation expectations.
- `references/business-cognition-diagram-patterns.md`: board splitting and diagram selection rules.
- `references/hand-drawn-prompt-bridge.md`: prompt template aligned to `hand-drawn-infographic-creator`.
- `scripts/validate_infographic_plan.py`: deterministic contract validator.
- `examples/ai-cognition-example/`: complete commercial cognition / AI cognition sample.

## Handoff

After validation, pass `image_prompts/*.prompt.md` to `hand-drawn-infographic-creator` for image generation. Pass `board_specs/*.json` plus generated PNGs to `hand-drawn-infographic-video-board` for controllable board manifests and motion plans.
