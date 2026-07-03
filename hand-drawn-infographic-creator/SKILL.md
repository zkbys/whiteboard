---
name: hand-drawn-infographic-creator
description: Generate concise hand-drawn whiteboard infographic prompts, layout notes, and accessibility text for AI image generation. Use this as the creator-facing prompt bridge inside the AI whiteboard infographic video pipeline.
---

# Hand-Drawn Infographic Creator

## Purpose

Turn a semantic board prompt into a final image-generation prompt for a sparse hand-drawn whiteboard infographic. This skill produces prompt text and review notes only. It does not create video, audio, animation coordinates, or final board-control JSON.

## Output

For each board, write a creator output file and a final image prompt:

```text
creator_outputs/board-XX.creator_output.md
imagegen_prompts/board-XX.imagegen_prompt.txt
```

The final prompt is the input for an image model. If the image tool returns only a preview, the operator must manually save the PNG into:

```text
images/board-XX.model-generated.png
```

## Visual Style

- Hand-drawn whiteboard explanation.
- Engineer's notebook sketch.
- Continuous charcoal line art.
- Parchment/whiteboard background.
- Sparse labels, not a full transcript.
- Margin annotations only where they clarify the diagram.

Palette:

```yaml
background: "#faf8f3"
primary_line: "#1a2332"
annotation: "#2d5a7b"
positive: "#4a9d9e"
risk: "#e63946"
insight: "#f4a261"
```

Use one or two semantic highlight colors per board. Use color for meaning, not decoration.

## Prompt Requirements

Every final prompt should include:

- Aspect ratio and target framing, usually `16:9 landscape`.
- The board title and 3-5 key objects.
- The required short labels that should appear on the board.
- The drawing style vocabulary listed above.
- The sentence `内容简洁一点，不要逐字写满口播`.
- Negative prompt terms:
  `photorealistic, 3D render, CGI, stock photo, corporate dashboard, smooth digital art, dense tiny text, watermark`.

## Handoff Rules

- Keep ids stable. If C calls an object `workflow_asset`, keep that id in creator notes.
- Do not invent final animation coordinates. Bbox, camera, cursor, and annotation geometry belong to D.
- If the generated image changes Chinese text, record the drift in the creator output or `board_asset_manifest.json`.
- Do not treat the prompt as proof that the final PNG contains exact text. The PNG must be reviewed before D/E.

## Creator Output Template

```markdown
# Creator Output: board-01

## Board Intent
[One sentence explaining the board.]

## Required Visible Labels
- [short label]
- [short label]

## Layout Notes
- [where the main object should sit]
- [where the margin note or takeaway should sit]

## Final Image Prompt
[model-ready prompt]

## Negative Prompt
[negative prompt]

## Review Notes
- Text that must be checked after generation.
- Elements that need D calibration if the model drifts.
```
