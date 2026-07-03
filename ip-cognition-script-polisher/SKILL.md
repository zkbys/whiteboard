---
name: ip-cognition-script-polisher
description: Polish rough topics, short opinions, or draft scripts into 30-60 second IP incubation, business cognition, and AI cognition short-video voiceover packages for whiteboard infographic videos. Use when Codex needs to preserve a user's core stance while producing polished_voiceover.md, voiceover_segments.json, and visual_beats.json with hook/反常识/例子/转折/方法/结论 segments, spokenAnchors, visualIntent, and duration-checkable output.
---

# IP Cognition Script Polisher

## Overview

Use this skill to turn a topic, rough opinion, or partial draft into a reviewable script package for IP incubation, business cognition, and AI cognition short videos. The output is not a final video; it is the upstream script contract for whiteboard infographic planning, voiceover timing, and later rendering.

## Workflow

1. Read the user's brief and extract the core stance, target audience, promised value, and any non-negotiable wording.
2. Preserve the user's core viewpoint. Sharpen framing and rhythm, but do not reverse the stance or smuggle in a different conclusion.
3. If the input is only a topic, infer a conservative thesis and make the inference explicit in `polished_voiceover.md` under `Stance basis`.
4. Produce exactly six voiceover segments in this role order: `hook`, `反常识`, `例子`, `转折`, `方法`, `结论`.
5. Keep the total estimated voiceover length between 30 and 60 seconds. Default target is 45 seconds unless the user specifies otherwise.
6. Add `spokenAnchors` and `visualIntent` to every segment. Use anchors that appear verbatim in the segment text or caption.
7. Create only necessary visual beats. Do not turn every sentence into a board object; group the script into 3-6 strong visual ideas.
8. Validate the package with the bundled script before handing it off.

## Outputs

Write these files into the requested package directory, usually `script/` inside a workflow project:

```text
script/
├── polished_voiceover.md
├── voiceover_segments.json
└── visual_beats.json
```

`voiceover_segments.json` is the source of truth for narration. `visual_beats.json` is the source of truth for the next infographic-planning skill. `polished_voiceover.md` is the human review surface.

## Segment Rules

- `hook`: Start with a sharp, memorable tension. Avoid vague openings such as "今天聊聊".
- `反常识`: State the counterintuitive claim without overclaiming beyond the user's brief.
- `例子`: Use one concrete scene, comparison, or mini case. Prefer business/IP/AI operator details over generic life advice.
- `转折`: Reframe the issue and connect the example back to the core thesis.
- `方法`: Give a repeatable 2-4 step method, checklist, or decision rule.
- `结论`: End with a compact sentence that can become the final subtitle or board title.

Each segment must include:

```json
{
  "id": "seg-01-hook",
  "role": "hook",
  "text": "口播正文",
  "caption": "字幕文本",
  "visualIntent": "这一段应该让白板画面表达什么",
  "spokenAnchors": ["必须出现在 text 或 caption 里的短语"]
}
```

Optional fields such as `boardId`, `targetElement`, `targetDurationSec`, and `pauseAfter` are useful for downstream timing and board control.

## References

Read `references/script_patterns.md` when shaping a script from a very short topic or when the structure feels flat. Read `references/schema.md` before changing JSON fields or building downstream consumers.

## Validation

Run:

```bash
python3 scripts/validate_script_package.py --package-dir examples/output
```

For an external project package:

```bash
python3 /path/to/ip-cognition-script-polisher/scripts/validate_script_package.py --package-dir /path/to/project-output/script
```

Validation checks required fields, exact role coverage/order, `spokenAnchors`, matching visual beat segment IDs, and estimated duration.
