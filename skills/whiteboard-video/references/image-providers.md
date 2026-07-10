# Image providers

Interactive is the default and requires no credentials:

```bash
export WHITEBOARD_IMAGE_MODE=interactive
```

## OpenAI

Configure automatic PNG generation explicitly:

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=openai
export OPENAI_API_KEY="..."
```

The default model is `gpt-image-2`, size is `1536x1024`, quality is `medium`, and output format is PNG. Override the model with `WHITEBOARD_OPENAI_IMAGE_MODEL`. Use `WHITEBOARD_OPENAI_API_KEY_ENV` when the key lives in another environment variable. Use `OPENAI_BASE_URL` only for a trusted OpenAI-compatible endpoint.

Never write the API key to project files, reports, command output, or Git.

## Command provider

Configure an executable adapter:

```bash
export WHITEBOARD_IMAGE_MODE=auto
export WHITEBOARD_IMAGE_PROVIDER=command
export WHITEBOARD_IMAGE_COMMAND="/absolute/path/to/image-provider"
```

The orchestrator executes it without a shell and supplies:

```text
--prompt-file <absolute-prompt-path>
--output-file <absolute-temporary-png-path>
--board-id <board-id>
```

The command must exit `0` and write a valid PNG to `--output-file`. The orchestrator validates the PNG signature and minimum dimensions before atomically moving it to `images/<boardId>.model-generated.png`.

## Safety and resume

- `auto` does not select OpenAI merely because `OPENAI_API_KEY` exists.
- Existing valid PNGs are reused by default, allowing a partial run to resume without buying the same image twice.
- Use `--overwrite` only when regeneration is intentional.
- Provider errors write `image_generation_report.json` with `status=failed` and never create a success manifest.
