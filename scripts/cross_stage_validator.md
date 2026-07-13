# Cross-Stage ID Alignment

The `scripts/cross_stage_validator.py` tool checks that every `targetElement` referenced in `script/voiceover_segments.json` (B output) exists in the matching C `board_spec.json` `keyObjects[].id`.

## Usage

```bash
python3 scripts/cross_stage_validator.py --project-dir /path/to/project-output
```

Or with explicit paths:

```bash
python3 scripts/cross_stage_validator.py \
  --voiceover /path/to/voiceover_segments.json \
  --board-specs-dir /path/to/board_specs \
  --output /path/to/cross_stage_validation_report.json
```

## Output

- `cross_stage_validation_report.json` is written next to the project root (or `--output`).
- Status is `PASS` when every `targetElement` has a matching key object ID.
- Status is `WARN` when there are mismatches; the report includes the closest available ID as a suggestion.
- Example message: `B 脚本引用了 'business_judgment'，但 board_spec 中只有 'judgment_loop'，建议映射为 'judgment_loop'`.

## Integrating into the pipeline

Run this validator after B and C are complete, before D/E. A non-PASS result should not block the pipeline by default, but the warnings should be reviewed because E will fail if `targetElement` maps to a missing board element.
