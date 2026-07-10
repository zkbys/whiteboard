# Installed layout

The installer copies one self-contained public Skill to the selected agent directory:

```text
whiteboard-video/
├── SKILL.md
├── agents/openai.yaml
├── scripts/doctor.py
├── references/
├── installation.json
    └── runtime/
    ├── ip-cognition-script-polisher/
    ├── ip-hand-drawn-infographic-planner/
    ├── hand-drawn-infographic-creator/
    ├── hand-drawn-infographic-video-board/
    ├── whiteboard-infographic-video-renderer/
    └── whiteboard-infographic-pipeline-orchestrator/
```

Each internal runtime module uses `INTERNAL_SKILL.md` in an installed copy. This prevents recursive Agent Skill scanners from exposing internal B/C/Creator/D/E entries as public Skills. The source checkout keeps the original module `SKILL.md` names for development.

Codex uses `$HOME/.agents/skills/whiteboard-video`. Claude Code uses `~/.claude/skills/whiteboard-video`. Both copies use the same source package and relative runtime layout; neither relies on a symlink or the original Git clone.

Keep generated projects outside this managed directory. Default to `<current-working-directory>/whiteboard-runs/` so upgrades cannot delete user outputs.

`installation.json` marks ownership and stores the source digest. The installer must refuse to overwrite a same-named directory without this marker. Reinstalling the same digest is a no-op; changing the digest requires `--upgrade`.
