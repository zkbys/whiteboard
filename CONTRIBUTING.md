# Contributing

## Repository

Canonical local path:

```text
/Users/yanzhengkai/Documents/AI剪辑skill/ai-whiteboard-infographic-pipeline
```

GitHub remote:

```text
https://github.com/zkbys/whiteboard.git
```

## Recommended Workflow

```bash
cd "/Users/yanzhengkai/Documents/AI剪辑skill/ai-whiteboard-infographic-pipeline"
git pull --ff-only
git checkout -b codex/<feature-name>
```

Make the change, then validate:

```bash
npm run check
```

Clean local generated files:

```bash
find . -name ".DS_Store" -delete
find . -name "__pycache__" -type d -prune -exec rm -rf {} +
find . -name "*.pyc" -delete
```

Commit and push:

```bash
git add <changed-files>
git commit -m "<concise change summary>"
git push -u origin codex/<feature-name>
```

For small docs-only fixes, direct commits to `main` are acceptable:

```bash
git checkout main
git pull --ff-only
npm run check
git add <changed-files>
git commit -m "<concise change summary>"
git push origin main
```

## Module Map

| Need to change | Work here |
| --- | --- |
| Script polish, six-segment voiceover package | `ip-cognition-script-polisher/` |
| Semantic board planning and image prompts | `ip-hand-drawn-infographic-planner/` |
| Final image-generation prompt bridge | `hand-drawn-infographic-creator/` |
| Board control layer, bbox calibration, annotation geometry | `hand-drawn-infographic-video-board/` |
| TTS, measured timing, sync, HyperFrames, MP4/keyframes | `whiteboard-infographic-video-renderer/` |
| End-to-end flow, runbook, acceptance report | `whiteboard-infographic-pipeline-orchestrator/` |

## Commit Hygiene

Do not commit generated videos, audio, run folders, private reference material, or old experiment folders. See `AGENTS.md` for the full exclusion list.

When changing a file contract, update both implementation and docs in the same commit.
