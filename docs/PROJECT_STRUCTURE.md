# Project Structure

This repository contains the current public AI whiteboard infographic pipeline. It is the canonical workspace for future development.

## Top-Level Files

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Required operating instructions for new agent threads. |
| `CLAUDE.md` | Pointer for tools that read `CLAUDE.md`; delegates to `AGENTS.md`. |
| `CONTRIBUTING.md` | Human-facing development and GitHub push workflow. |
| `README.md` | Default Chinese install-and-use entry. |
| `README.en.md` | English install-and-use entry. |
| `README.zh-CN.md` | Compatibility pointer to the default Chinese README. |
| `package.json` | Validation commands. |
| `.gitignore` | Keeps generated runs, media, caches, and local artifacts out of Git. |

## Public Skill and product tooling

| Path | Purpose |
| --- | --- |
| `skills/whiteboard-video/SKILL.md` | The only user-facing Skill and natural-language video entrypoint. |
| `skills/whiteboard-video/agents/openai.yaml` | Optional Codex/ChatGPT display metadata. |
| `skills/whiteboard-video/scripts/doctor.py` | Location-independent wrapper for the bundled doctor. |
| `scripts/install.py` | Copy-based Codex/Claude installer with dry-run, ownership, idempotence, and upgrade protection. |
| `scripts/doctor.py` | PASS/WARN/FAIL checks for installation, render dependencies, output, and image mode. |
| `tests/test_install.py` | Temporary-directory clean installation and collision/doctor regression tests. |
| `tests/test_image_provider.py` | Mock OpenAI API, command provider, interactive fallback, PNG, secret, and manifest regression tests. |

## Internal Pipeline Modules

The installer copies these directories below `whiteboard-video/runtime/`. They are implementation modules, not separately installed public Skills.

| Directory | Stage | Owns |
| --- | --- | --- |
| `ip-cognition-script-polisher/` | B | Topic or rough-script polishing into `script/` package. |
| `ip-hand-drawn-infographic-planner/` | C | Semantic infographic plans, board specs, and image prompts. |
| `hand-drawn-infographic-creator/` | Creator | Final image-generation prompt and review notes. |
| `hand-drawn-infographic-video-board/` | D | Board control package, annotation geometry, calibration, motion plans. |
| `whiteboard-infographic-video-renderer/` | E | Narration, timing, token sync, HyperFrames, preview video, keyframes. |
| `whiteboard-infographic-pipeline-orchestrator/` | Orchestrator | End-to-end order, automatic/interactive image handoff, validation, reporting. |

## Documentation

| Path | Purpose |
| --- | --- |
| `docs/ARCHITECTURE.md` | Pipeline architecture and contract boundaries. |
| `docs/VERSION_AUDIT.md` | Why this package is the latest baseline and which old versions are excluded. |
| `docs/REAL_E2E_SAMPLE.md` | Latest local real end-to-end sample summary; generated media remains ignored. |
| `docs/OPEN_SOURCE_CHECKLIST.md` | Publishing safety checklist. |
| `whiteboard-infographic-pipeline-orchestrator/references/runbook.md` | End-to-end execution runbook. |
| `whiteboard-infographic-pipeline-orchestrator/references/contracts.md` | Cross-module package contract. |

## Generated Outputs

Generated outputs belong in ignored run folders, usually:

```text
runs/
orchestrator-runs/
whiteboard-runs/
```

They should not be committed unless deliberately converted into a small, public, reusable fixture.
