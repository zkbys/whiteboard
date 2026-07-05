# Project Structure

This repository contains the current public AI whiteboard infographic pipeline. It is the canonical workspace for future development.

## Top-Level Files

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Required operating instructions for new agent threads. |
| `CLAUDE.md` | Pointer for tools that read `CLAUDE.md`; delegates to `AGENTS.md`. |
| `CONTRIBUTING.md` | Human-facing development and GitHub push workflow. |
| `README.md` | English project overview. |
| `README.zh-CN.md` | Chinese project overview. |
| `package.json` | Validation commands. |
| `.gitignore` | Keeps generated runs, media, caches, and local artifacts out of Git. |

## Pipeline Modules

| Directory | Stage | Owns |
| --- | --- | --- |
| `ip-cognition-script-polisher/` | B | Topic or rough-script polishing into `script/` package. |
| `ip-hand-drawn-infographic-planner/` | C | Semantic infographic plans, board specs, and image prompts. |
| `hand-drawn-infographic-creator/` | Creator | Final image-generation prompt and review notes. |
| `hand-drawn-infographic-video-board/` | D | Board control package, annotation geometry, calibration, motion plans. |
| `whiteboard-infographic-video-renderer/` | E | Narration, timing, token sync, HyperFrames, preview video, keyframes. |
| `whiteboard-infographic-pipeline-orchestrator/` | Orchestrator | End-to-end order, manual handoff rules, validation, reporting. |

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
```

They should not be committed unless deliberately converted into a small, public, reusable fixture.
