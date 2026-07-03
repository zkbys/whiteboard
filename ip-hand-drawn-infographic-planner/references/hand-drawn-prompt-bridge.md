# Hand-Drawn Prompt Bridge

The prompt must be ready to hand to `hand-drawn-infographic-creator`.

## Required Style Terms

Include these terms in every prompt:

```text
continuous line art
engineer's notebook sketch with annotations in margins
whiteboard explanation aesthetic
ink on parchment
hand-drawn educational illustration
```

## Required Simplicity Instruction

Every prompt must include this exact Chinese sentence:

```text
内容简洁一点，不要逐字写满口播
```

## Palette

Use these colors:

```yaml
background: "#faf8f3"
primary_line: "#1a2332"
annotation: "#2d5a7b"
active_or_positive: "#4a9d9e"
problem_or_risk: "#e63946"
progress_or_insight: "#f4a261"
```

Rules:

- Use parchment `#faf8f3` as the background.
- Use charcoal `#1a2332` for the main drawing lines.
- Use ocean blue `#2d5a7b` for labels and margin notes.
- Use only 1-2 highlight colors per board.
- Use color for meaning, not decoration.

## Prompt Template

```markdown
# <board-id> Prompt

## Positive Prompt
<subject>, continuous line art, engineer's notebook sketch with annotations in margins,
whiteboard explanation aesthetic, ink on parchment (#faf8f3), charcoal lines (#1a2332),
ocean-blue annotations (#2d5a7b), <1-2 semantic highlight colors>, hand-drawn educational illustration.
内容简洁一点，不要逐字写满口播。

## Content To Include
- <short visible label 1>
- <short visible label 2>
- <short visible label 3>

## Layout Notes
- <semantic layout guidance, no exact coordinates>

## Negative Prompt
photorealistic, 3D render, CGI, stock photo, corporate flowchart, sterile dashboard,
smooth digital art, gradient shading, airbrush, dense text, full transcript on image
```

## Prompt Checks

Before finishing, verify:

- The board can be understood at a glance.
- There are no more than 3-5 key objects.
- The prompt asks for short labels, not complete paragraphs.
- The negative prompt blocks photorealistic and corporate output.
