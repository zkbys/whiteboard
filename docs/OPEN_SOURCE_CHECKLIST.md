# Open Source Checklist

## Already Prepared

- Clean package folder under `ai-whiteboard-infographic-pipeline/`.
- Only current pipeline Skill folders are included.
- Old experiment folders and large generated outputs are excluded.
- Local absolute paths were removed from public-facing docs.
- Old recovery/sobriety-specific creator prompt material was replaced with a generic whiteboard infographic prompt bridge.
- Latest sync/calibration requirements were added to root docs and contracts.

## Confirm Before Publishing

Please confirm these items before pushing to GitHub:

- GitHub repository name.
- Public copyright holder name.
- License choice. Current default is MIT.
- Whether generated example image `whiteboard-infographic-video-renderer/examples/input/board/board.png` is safe to publish.
- Whether you want docs primarily in Chinese, English, or bilingual.
- Whether this should be published as a standalone repo or copied into a larger skill marketplace repo.

## Recommended GitHub Exclusions

Keep these out of the public repo:

- `whiteboard-infographic-prototype-v0.*`
- `integration-smoke-test-*`
- `integration-full-run-*`
- `optimization-sync-calibration-test/`
- `orchestrator-runs/`
- `reference-video-analysis/`
- `visual-hammer-v0.1/`
- `*.mp4`, `*.mov`, `*.mp3`, `*.wav`, `*.aiff`
- generated model PNGs and keyframe contact sheets, unless explicitly curated as small public examples
- `.DS_Store`, `__pycache__/`, `node_modules/`, `.playwright-cli/`
