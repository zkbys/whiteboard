# V1 Loop Log

This is the durable state for release-driven Loop Engineering. Each loop fixes only the first failed release condition, runs the full gate, commits, and pushes before the next loop begins.

## Loop 1 - Executable release acceptance

Status: complete

Hypothesis: the remaining product risk cannot be controlled until final delivery acceptance is executable rather than described only in Markdown.

Planned evidence:

- `validate_release_candidate.py` checks video/audio duration, image provenance and identity, D/E board contracts, renderer state, QA, keyframes, and required artifacts.
- Healthy and adversarial temporary fixtures run without committed media.
- The validator is bundled into installed Skills and included in `npm run check`.

Evidence:

- Six release-acceptance tests cover healthy delivery, missing preview, out-of-range duration, QA/asset failures, incomplete provider/renderer state, and obsolete source-prefix detection.
- The historical real sample is correctly rejected because it predates `image_generation_report.json` and contains old checkout paths.
- `npm run check` passes with the new `check:release-candidate` gate.

## Loop 2 - Installed-runtime forward test

Status: complete

Hypothesis: the self-contained installed runtime can generate and validate a real MP4 outside the source checkout.

Evidence:

- `scripts/install.py` creates a self-contained Skill copy under Codex/Claude Code user directories.
- `tests/test_install.py` validates clean install, idempotence, upgrade, collision refusal, and path handling.
- `scripts/doctor.py` reports installation, render, output, and image-mode readiness.
- The installed runtime includes B/C/Creator/D/E/orchestrator modules and can execute the full pipeline.

## Loop 3 - Release engineering

Status: complete

Hypothesis: after functional acceptance passes, the remaining release risk is CI, doctor remediation, repository hygiene, and immutable release documentation.

Evidence:

- `AGENTS.md`, `CONTRIBUTING.md`, `README.md`/`README.en.md` describe current workflow.
- `docs/PROJECT_STRUCTURE.md` and `docs/VERSION_AUDIT.md` exclude old prototype folders and generated media.
- Obsolete Loop 2 Markdown reports and redundant diagnostic scripts were removed.
- `npm run check` covers Python compile, Node syntax, install, image-provider, release-candidate, renderer QA, and auto-calibration checks.

## Publication gate

PR, merge, tag, and GitHub Release remain blocked until explicit user authorization after all three loops pass.
