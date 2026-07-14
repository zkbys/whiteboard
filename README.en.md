# Whiteboard Video

[中文](README.md)

**Input a topic, get a 30–60 second AI whiteboard explainer video.**

<p align="center">
  <img src="https://raw.githubusercontent.com/zkbys/whiteboard/main/assets/demo.gif" width="720" alt="Demo: topic "More AI tools, less efficiency for regular people" (sped up 1.25×)">
  <br>
  <sub>🎬 Demo: topic "More AI tools, less efficiency for regular people" (sped up 1.25×)</sub>
</p>

## 🚀 Quick Start

**Copy this and paste into your AI coding assistant:**

```
Install this project: https://github.com/zkbys/whiteboard.git

After reading the README, run:
python3 scripts/install.py --target codex   # for Codex
python3 scripts/install.py --target claude  # for Claude Code

Then run:
python3 scripts/doctor.py --json

Make me a 30-60 second video about "More AI tools make ordinary people less efficient."
```

The video lands in `whiteboard-runs/<run-id>/video/preview.mp4`.

## Shell Installation

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard

# Codex
python3 scripts/install.py --target codex
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json

# Claude Code
python3 scripts/install.py --target claude
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json
```

Install to both: `--target both`. Preview without writing: `--dry-run`. Upgrade: `--upgrade`.

## What You Get

```text
whiteboard-runs/<run-id>/
├── script/                    # Voiceover segments & visual beats
├── infographic/               # Infographic plan
├── images/*.model-generated.png   # Model-generated whiteboard images
├── calibration/               # Automatic/manual element bbox calibration
├── board_source_for_e/        # Animation control layer
├── audio/                     # Narration, captions, timing
├── sync/                      # Action/camera QA reports
├── video/
│   ├── preview.mp4            # Final video
│   ├── hyperframes/           # Editable project
│   └── keyframes/             # Keyframes
└── integration_report.md      # Acceptance report
```

After rendering, validate with:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /absolute/path/to/whiteboard-run
```

## Requirements

- Python 3.10+
- Node.js 20+
- `ffmpeg`, `ffprobe`
- `edge-tts`, `npx`
- `hyperframes@0.6.99`

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --json
```

The doctor reports four layers:

| Category | Meaning |
|----------|---------|
| `install` | Skill and bundled modules complete |
| `render` | Python, Node, ffmpeg, edge-tts, HyperFrames ready |
| `output` | Output directory writable |
| `image` | Image mode: `interactive` (default) or `auto` |

## Image Modes

Default `interactive`: the agent pauses once after image generation, waits for you to confirm PNGs are saved, then auto-resumes the pipeline.

Auto mode (needs OpenAI API key):

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=openai
export OPENAI_API_KEY="..."
```

An API key alone never triggers a billable call; the provider must also be set explicitly.

## Auto-Calibration

By default, the D stage (animation control layer) uses template coordinates for underlines, boxes, and camera framing. When the model-generated image (e.g., from seedance) drifts from the template layout, annotations land in the wrong place. The pipeline automatically detects real element positions from the actual PNG before D:

```bash
python3 hand-drawn-infographic-video-board/scripts/auto_calibrate.py \
  --project-dir whiteboard-runs/<run-id> \
  --provider auto \
  --json
```

- `agent`: Claude vision model (recommended, uses `ANTHROPIC_AUTH_TOKEN`), no separate `OPENAI_API_KEY` needed. Requires explicit `--provider agent`, `WHITEBOARD_CALIBRATION_PROVIDER=agent`, or `WHITEBOARD_CALIBRATION_AGENT_AUTO=1`.
- `vlm`: OpenAI-compatible endpoint (requires `OPENAI_API_KEY`).
- `ocr`: Local OCR (no API cost): `pip install easyocr`.
- `mock`: Deterministic placeholder coordinates for testing or fallback when no backend is available.

If auto-detection does not cover every target element, a pre-filled calibration tool is generated at `calibration_tool/index.html`. Adjust boxes, save to `calibration/`, then rerun D/E.

Auto-calibration outputs:

```text
calibration/<boardId>.element_bboxes.json
calibration/auto_calibration_report.json
```

## Limitations

- No hidden-cache scraping, no fake URLs, no placeholder substitutions
- Auto-calibration supports agent, VLM, and local OCR; local OCR requires installing `easyocr` or `paddleocr`

## Developers

Pipeline: Topic → B script → C plan → Creator images → D control → E render/QA

Before contributing, read [AGENTS.md](AGENTS.md), [project structure](docs/PROJECT_STRUCTURE.md), [architecture](docs/ARCHITECTURE.md). Before submitting:

```bash
npm run check
```

## License

MIT.
