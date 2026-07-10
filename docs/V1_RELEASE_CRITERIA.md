# V1 Release Criteria

V1 is complete when an installed `whiteboard-video` Skill can turn a natural-language topic into a validated 30-60 second video project. V1 is release-driven: work stops when the checks below pass.

## Supported scope

- macOS and Linux.
- Codex and Claude Code.
- Chinese 16:9 whiteboard explainers, normally using 1-2 boards.
- OpenAI or command automatic image providers, with one interactive handoff as a safe fallback.
- Editable HyperFrames, preview MP4, keyframes, action/camera QA, and integration reporting.

OCR, automatic visual bbox discovery, vertical video, Windows, GUI, cloud execution, additional providers, and new visual effects are not V1 blockers.

## Executable acceptance

Run after a real render:

```bash
python3 whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir /absolute/path/to/project
```

The validator writes:

```text
v1_release_acceptance.json
v1_release_acceptance.md
```

It requires:

- A probeable `video/preview.mp4` and `audio/narration.wav`, both 30-60 seconds and within 0.1 seconds of measured timing.
- Completed multi-board rendering, keyframe extraction, and zero-exit HyperFrames lint/validate/inspect.
- `action_camera_qa_report.json` status `pass` with no fallback, compressed rhythm, bbox, camera, or keyframe issues.
- A complete image-provider report, local model-PNG manifest, and matching board IDs across image, D, and renderer stages.
- Byte-identical image assets from `images/` through D and HyperFrames.
- One start/done keyframe pair per action, with consistent action counts.
- Complete editable-project, audio, sync, and integration-report artifacts.

For installed-package isolation, repeat `--forbid-prefix <source-checkout>` to reject obsolete source paths in text outputs.

## Stop condition

Once the installed-runtime forward test, this validator, `npm run check`, macOS/Linux CI, and remote-clone installation smoke all pass, only release metadata may change before `v1.0.0`. All additional visual improvements move to the post-V1 backlog.
