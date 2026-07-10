# Whiteboard Video

[中文](README.md) | English

Turn a topic, viewpoint, or rough script into a 30-60 second AI whiteboard infographic explainer with an editable HyperFrames project, measured audio timing, action/camera QA, keyframes, and an acceptance report.

> `whiteboard-video` is the only public Skill. B, C, Creator, D, E, and the orchestrator remain bundled internal modules; users do not install them separately.

## Verified real-run evidence

The latest local end-to-end acceptance run produced two boards, six voiceover segments, nine matched annotation actions, and a 42.58-second preview. Audio/render duration differed by 0.045 seconds, action/camera QA passed, and both board assets passed the full identity chain. Generated media is intentionally not committed; see the [real end-to-end sample record](docs/REAL_E2E_SAMPLE.md).

## Ask Codex to install it

Copy this prompt into Codex:

```text
Install this project: https://github.com/zkbys/whiteboard.git

Clone it into a temporary directory, read the root README, then run:
python3 scripts/install.py --target codex

After installation, run:
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json

Report the install, render, output, and image statuses separately. Tell me whether installation succeeded, which render dependencies are missing, whether Codex needs a restart, and whether image mode is interactive or auto. Do not use sudo.
```

The default Codex destination is `$HOME/.agents/skills/whiteboard-video`. Codex normally detects Skill changes automatically; restart or open a new task if it does not appear. See the [official Codex Skills documentation](https://learn.chatgpt.com/docs/build-skills).

## Ask Claude Code to install it

Copy this prompt into Claude Code:

```text
Install this project: https://github.com/zkbys/whiteboard.git

Clone it into a temporary directory, read the root README, then run:
python3 scripts/install.py --target claude

After installation, run:
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json

Report the install, render, output, and image statuses separately. Tell me whether installation succeeded, which render dependencies are missing, whether Claude Code needs a restart, and whether image mode is interactive or auto. Do not use sudo.
```

The default Claude Code destination is `~/.claude/skills/whiteboard-video`. Changes are live-detected when the top-level skills directory already existed at session start; restart Claude Code if the installer created that top-level directory for the first time. See the [official Claude Code Skills documentation](https://code.claude.com/docs/en/skills).

## Direct shell installation

Codex:

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard
python3 scripts/install.py --target codex
python3 "$HOME/.agents/skills/whiteboard-video/scripts/doctor.py" --json
```

Claude Code:

```bash
git clone https://github.com/zkbys/whiteboard.git
cd whiteboard
python3 scripts/install.py --target claude
python3 "$HOME/.claude/skills/whiteboard-video/scripts/doctor.py" --json
```

Other supported operations:

```bash
python3 scripts/install.py --target both
python3 scripts/install.py --target both --dry-run
python3 scripts/install.py --target codex --upgrade
```

Reinstalling the same source digest is a no-op. A changed source requires `--upgrade`. The installer uses no sudo or symlinks, refuses to overwrite unowned same-name directories, and creates a self-contained copy that keeps working after the original Git clone is removed.

## Create the first video

In Codex:

```text
Use the whiteboard-video skill to make a 30-60 second video about this idea: “More AI tools can make ordinary people less efficient.”
```

In Claude Code, use the same natural language or invoke it explicitly:

```text
/whiteboard-video Topic: “More AI tools can make ordinary people less efficient.” Duration: 30-60 seconds.
```

Runs default to `whiteboard-runs/` under the user's current working directory, never inside the managed Skill installation.

## Required output

An accepted run includes at least:

```text
whiteboard-runs/<run-id>/
├── script/
├── infographic/
├── images/*.model-generated.png
├── image_generation_report.json
├── board_asset_manifest.json
├── board_source_for_e/
├── audio/
├── sync/
│   ├── action_timing.json
│   ├── camera_plan.json
│   ├── action_camera_qa_report.md
│   └── action_camera_qa_report.json
├── video/
│   ├── preview.mp4
│   ├── hyperframes/
│   ├── keyframes/
│   └── renderer_report.json
└── integration_report.md
```

After a real render, run the unified v1 release validator:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /absolute/path/to/whiteboard-run
```

It checks video/audio duration, image identity, D/E board contracts, HyperFrames, QA, keyframes, and required artifacts, then writes `v1_release_acceptance.json` and `.md`. See [V1 Release Criteria](docs/V1_RELEASE_CRITERIA.md).

## Requirements and doctor

Rendering requires Python 3.10+, Node.js 20+, `ffmpeg`, `ffprobe`, `edge-tts`, `npx`, and downloadable or cached `hyperframes@0.6.99`.

```bash
python3 scripts/doctor.py
python3 scripts/doctor.py --json
```

The doctor reports four independent categories:

| Category | Meaning |
| --- | --- |
| `install` | Public Skill and bundled B/C/Creator/D/E/orchestrator completeness |
| `render` | Python, Node, ffmpeg, ffprobe, edge-tts, npx, and HyperFrames readiness |
| `output` | Whether the project output directory is writable |
| `image` | Whether image mode is `interactive` or `auto` |

`install=PASS` with `render=FAIL` means the Skill is installed correctly but cannot yet perform a real render. `image=WARN` is expected for the default interactive mode; a complete automatic provider configuration reports `image=PASS`.

## Image modes: interactive and auto

Interactive remains the safe credential-free default. When an image tool exposes preview images without stable file paths, the agent pauses once and reads exact PNG destinations from `image_generation_report.json`. It resumes D/E, rendering, keyframes, and QA after every image passes validation.

Configure automatic OpenAI generation and direct PNG persistence with:

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=openai
export OPENAI_API_KEY="..."
```

The default is the current `gpt-image-2` model, `1536x1024`, medium quality, and PNG output, based on the official [GPT Image 2 model page](https://developers.openai.com/api/docs/models/gpt-image-2) and [Images API reference](https://developers.openai.com/api/reference/resources/images). An API key alone never triggers a billable call; the provider must also be configured explicitly.

Custom adapters can use the shell-free command contract:

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=command
export WHITEBOARD_IMAGE_COMMAND="/absolute/path/to/image-provider"
```

Validate either configuration with `python3 scripts/doctor.py --image-mode auto --json`.

## Current limitations

The Skill never searches hidden caches, invents image URLs, substitutes placeholders or D SVG previews, leaks API keys, or claims zero-human automation after a failed/incomplete provider run. Auto mode covers provider calls, atomic PNG persistence, validation, resume, and manifest handoff. OCR/visual bbox initialization is explicitly outside the v1.0 scope; low-confidence geometry uses conservative framing or optional manual calibration.

## Developer architecture and validation

```text
Topic or rough script
  -> B script shaping
  -> C semantic infographic planning
  -> Creator prompts
  -> automatic provider or interactive model-PNG handoff
  -> D board control and calibration
  -> E measured timing, HyperFrames, MP4, keyframes, and QA
  -> integration_report.md
```

Before contributing, read [AGENTS.md](AGENTS.md), [project structure](docs/PROJECT_STRUCTURE.md), [architecture](docs/ARCHITECTURE.md), and [version audit](docs/VERSION_AUDIT.md). Run:

```bash
npm run check
```

The slower real-render regression remains available as `npm run check:renderer-real`.

## License

MIT.
