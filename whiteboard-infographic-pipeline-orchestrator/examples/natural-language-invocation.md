# Natural Language Invocation Example

User says:

```text
请使用白板总编排skill帮我做一个视频，我想表达的主题为“AI 工具越多，普通人反而越低效”，时长在30-60秒左右
```

Expected Skill behavior:

1. Trigger `whiteboard-infographic-pipeline-orchestrator`.
2. Extract:
   - topic: `AI 工具越多，普通人反而越低效`
   - duration range: `30-60秒`
   - default target duration: about `45秒`
   - style: `IP孵化/商业认知/AI认知类短视频`
3. Create a project folder automatically:

```text
<repo-root>/orchestrator-runs/YYYYMMDD-HHMM-ai-tools-overload/
```

4. Write the request into:

```text
topic_input.txt
```

5. Run B/C/creator/image/D/E in the normal orchestrator sequence.
6. Pause at the model-image handoff if generated images are preview-only.
7. After the user manually downloads PNGs into `images/`, continue D/E and finish with:

```text
video/preview.mp4
video/keyframes/contact_sheet_start_done.jpg
integration_report.md
```

The user should not need to provide a pre-made input file or choose module-level commands.
