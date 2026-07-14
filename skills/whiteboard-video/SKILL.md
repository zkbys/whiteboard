---
name: whiteboard-video
description: Create a complete 30-60 second AI whiteboard infographic explainer video from a topic, viewpoint, or rough script. Use when the user asks for a whiteboard video, AI whiteboard explainer, 白板信息图讲解视频, or explicitly asks to use whiteboard-video; produce editable HyperFrames, preview.mp4, action/camera QA, keyframes, and integration_report.md with automatic PNG providers when configured and a safe interactive fallback.
---

# Whiteboard Video

Turn the user's topic or rough script into a reviewable whiteboard-video project. Treat this Skill as the only public entrypoint. Use B, C, Creator, D, E, and the orchestrator from the bundled `runtime/` as internal implementation modules.

## Resolve the installation

1. Treat the directory containing this `SKILL.md` as `SKILL_ROOT`.
2. Read `SKILL_ROOT/installation.json` when present.
3. Resolve the bundled runtime as `SKILL_ROOT/runtime/` for an installed copy. In a source checkout, resolve the repository root two directories above `SKILL_ROOT`.
4. Run the deterministic environment check before the first video in a session:

```bash
python3 <SKILL_ROOT>/scripts/doctor.py --json --output-dir <OUTPUT_PARENT>
```

Report the `install`, `render`, `output`, and `image` statuses separately. Do not treat interactive image handoff as an installation failure.

## Start from natural language

Accept a topic, viewpoint, or rough script directly. Do not require the user to create an input file. If the user gives a range such as 30-60 seconds, target about 45 seconds while keeping the final result inside the requested range.

Default the output parent to the user's current working directory, not the managed Skill installation. Create:

```text
<current-working-directory>/whiteboard-runs/YYYYMMDD-HHMMSS-<topic-slug>/
```

Write the original request to `topic_input.txt` inside that project directory.

Use a lowercase ASCII `topic-slug` with letters, digits, and hyphens. Fall back to `whiteboard-video` when the topic cannot be represented safely. If the path already exists, append `-2`, `-3`, and so on; never overwrite an earlier run implicitly.

## Execute the internal pipeline

Read these bundled internal instructions before executing their stage. Installed packages name each internal entry `INTERNAL_SKILL.md` so Agent discovery exposes only `whiteboard-video`; source checkouts use `SKILL.md` in the same module directory.

1. `runtime/ip-cognition-script-polisher/INTERNAL_SKILL.md`
2. `runtime/ip-hand-drawn-infographic-planner/INTERNAL_SKILL.md`
3. `runtime/hand-drawn-infographic-creator/INTERNAL_SKILL.md`
4. `runtime/hand-drawn-infographic-video-board/INTERNAL_SKILL.md`
5. `runtime/whiteboard-infographic-video-renderer/INTERNAL_SKILL.md`
6. `runtime/whiteboard-infographic-pipeline-orchestrator/INTERNAL_SKILL.md`
7. `runtime/whiteboard-infographic-pipeline-orchestrator/references/runbook.md`
8. `runtime/whiteboard-infographic-pipeline-orchestrator/references/contracts.md`

Run the fixed sequence:

1. Preserve the user's stance and create the six-part B script package.
2. Create semantic C board plans without bbox, camera, cursor, or animation geometry.
3. Create final hand-drawn infographic prompts and review notes.
4. Route every required board prompt through the configured image provider.
5. Complete automatic PNG validation or the interactive image handoff described below.
6. Write and validate `board_asset_manifest.json`.
7. Calibrate generated-image bboxes when needed. `--provider auto` tries the `agent` backend (Claude vision via `ANTHROPIC_AUTH_TOKEN`) when no `OPENAI_API_KEY` is configured, falling back to VLM, OCR, or mock as available.
8. Generate D into `board_source_for_e/`.
9. Render E from measured audio timing into editable HyperFrames and MP4.
10. Run asset identity and action/camera QA, inspect keyframes, and write `integration_report.md`.
11. Run `validate_release_candidate.py`; do not call the video complete unless it writes PASS acceptance reports.

Prefer the smallest board count that communicates the idea: normally 1-2 boards for a 30-60 second video, and more only when the content clearly requires it. Treat bundled examples as test fixtures, not board-count requirements.

Use scripts from the bundled runtime with absolute paths derived from `SKILL_ROOT`; never assume the current directory is the Git clone or the Skill installation.

In source-checkout testing only, replace `INTERNAL_SKILL.md` with the module's original `SKILL.md`.

## Route image generation

After C and Creator prompts exist, run:

```bash
python3 <RUNTIME>/whiteboard-infographic-pipeline-orchestrator/scripts/generate_board_images.py \
  --project-dir <PROJECT> \
  --provider auto
```

Interpret the exit status:

- `0`: all PNGs passed validation and `board_asset_manifest.json` was written; continue to calibration and D/E.
- `3`: no automatic provider is configured or some interactive PNGs are missing; generate previews with the available image tool and follow every exact path in `image_generation_report.json`.
- `2`: provider, API, PNG validation, or manifest generation failed; stop and report the error without claiming image success.

`auto` only uses OpenAI when `WHITEBOARD_IMAGE_PROVIDER=openai` is explicitly configured. The mere presence of `OPENAI_API_KEY` must not trigger a billable request. Before the first billable call, state the provider, model, size, and quality being used. Never print, persist, or expose the API key.

For custom providers, use `WHITEBOARD_IMAGE_PROVIDER=command` and an executable `WHITEBOARD_IMAGE_COMMAND`; read `references/image-providers.md` for its argument contract.

## Keep the interactive fallback honest

Interactive remains the safe default. If the image tool returns preview images without a stable local path:

- Stop once all preview images are generated.
- Ask the user to save each preview as `<project>/images/<boardId>.model-generated.png`.
- List every exact required path.
- Resume only after the files exist and pass PNG validation.
- Never search hidden caches, invent URLs, reuse old assets, or substitute D SVG previews or placeholders.

Do not claim zero-human automation unless `image_generation_report.json` has `status=complete`, `automatic=true`, every board is `generated` or `reused`, and the manifest records `previewChecked=false`.

## Require the product outputs

Do not call a run complete until it contains and validates at least:

```text
video/preview.mp4
video/hyperframes/
video/keyframes/
video/renderer_report.json
image_generation_report.json
sync/action_timing.json
sync/camera_plan.json
sync/action_camera_qa_report.md
sync/action_camera_qa_report.json
integration_report.md
v1_release_acceptance.json
v1_release_acceptance.md
```

Also require the B/C packages, local model-generated PNG manifest, D control package, measured narration timing, captions, HyperFrames lint/validate/inspect results, and asset identity check defined by the internal contracts.

Record all PASS/WARN/FAIL results and the manual image source in `integration_report.md`. A renderer warning from a deliberately skipped render is not equivalent to real-video acceptance.

Finish with:

```bash
python3 <RUNTIME>/whiteboard-infographic-pipeline-orchestrator/scripts/validate_release_candidate.py \
  --project-dir <PROJECT>
```

## Additional reference

Read `references/install-layout.md` when installation resolution or target-agent behavior is unclear.

Read `references/image-providers.md` before configuring OpenAI or a custom command provider.
