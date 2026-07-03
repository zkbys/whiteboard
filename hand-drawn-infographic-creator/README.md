# Hand-Drawn Infographic Creator

Prompt bridge for the AI whiteboard infographic video pipeline.

It converts semantic board prompts into model-ready image prompts and review notes. It intentionally does not render images, produce animation coordinates, or create videos.

Use it between:

```text
ip-hand-drawn-infographic-planner
  -> hand-drawn-infographic-creator
  -> image model / manual PNG handoff
  -> hand-drawn-infographic-video-board
```

Keep images simple: one board, one main idea, 3-5 objects, sparse labels, and enough blank space for cursor annotations.
