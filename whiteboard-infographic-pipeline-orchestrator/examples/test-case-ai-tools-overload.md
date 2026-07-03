# Test Case: AI Tools Overload

## 目标

验证 `whiteboard-infographic-pipeline-orchestrator` 能从一个 topic-only 输入开始，编排 B/C/creator/人工生图/D/E，最终产出可验收的白板信息图讲解视频包。

这个测试特意不复用已经跑通的“先商品后内容”案例，用于检查总编排 Skill 是否能处理新主题。

## 输入

Topic file:

```text
<repo-root>/whiteboard-infographic-pipeline-orchestrator/examples/test-case-ai-tools-overload-topic.txt
```

Project output:

```text
<repo-root>/orchestrator-test-ai-tools-overload
```

## 先跑输入校验

```bash
python3 <repo-root>/whiteboard-infographic-pipeline-orchestrator/scripts/validate_orchestrator_inputs.py \
  --workspace <repo-root> \
  --topic-input <repo-root>/whiteboard-infographic-pipeline-orchestrator/examples/test-case-ai-tools-overload-topic.txt \
  --project-dir <repo-root>/orchestrator-test-ai-tools-overload
```

Expected: `PASS`.

## 预期 B 输出

```text
orchestrator-test-ai-tools-overload/script/
├── polished_voiceover.md
├── voiceover_segments.json
└── visual_beats.json
```

Expected script shape:

- Six segments: `hook`, `反常识`, `例子`, `转折`, `方法`, `结论`.
- Core stance preserved: do not keep adding tools; define a stable task loop first.
- Likely visual anchors:
  - `工具越多`
  - `切换成本`
  - `任务闭环`
  - `一个主工具`

## 预期 C 输出

```text
orchestrator-test-ai-tools-overload/infographic/
├── infographic_plan.json
├── board_specs/
│   ├── board-01.board_spec.json
│   ├── board-02.board_spec.json
│   └── board-03.board_spec.json
└── image_prompts/
    ├── board-01.prompt.md
    ├── board-02.prompt.md
    └── board-03.prompt.md
```

Recommended board split:

- `board-01`: “工具越多，越慢” - show a messy tool pile and rising switching cost.
- `board-02`: “不是工具问题，是流程问题” - contrast scattered tool use with one task loop.
- `board-03`: “一环节一主工具” - checklist method: define task, pick one main tool, review output.

C must keep board specs semantic. Do not add bbox/camera/cursor in C.

## Creator and Imagegen Expected Outputs

```text
orchestrator-test-ai-tools-overload/creator_outputs/
├── board-01.creator_output.md
├── board-02.creator_output.md
└── board-03.creator_output.md

orchestrator-test-ai-tools-overload/imagegen_prompts/
├── board-01.imagegen_prompt.txt
├── board-02.imagegen_prompt.txt
└── board-03.imagegen_prompt.txt
```

Each image prompt should use the hand-drawn whiteboard style:

- parchment `#faf8f3`
- charcoal lines `#1a2332`
- ocean-blue annotations `#2d5a7b`
- only 1-2 semantic highlight colors
- negative prompt excludes photorealistic, 3D render, stock photo, corporate slide, smooth digital art

## 必须暂停的人工生图交接

After image generation, stop and require the user to manually download the preview PNGs to:

```text
orchestrator-test-ai-tools-overload/images/board-01.model-generated.png
orchestrator-test-ai-tools-overload/images/board-02.model-generated.png
orchestrator-test-ai-tools-overload/images/board-03.model-generated.png
```

Do not continue if these files do not exist.

Then run:

```bash
python3 <repo-root>/whiteboard-infographic-pipeline-orchestrator/scripts/write_board_asset_manifest.py \
  --project-dir <repo-root>/orchestrator-test-ai-tools-overload \
  --overwrite
```

Expected:

```text
orchestrator-test-ai-tools-overload/board_asset_manifest.json
```

## 预期 D/E 输出

D output:

```text
orchestrator-test-ai-tools-overload/board_source_for_e/
├── board_index.json
├── combined_motion_plan.json
├── package_report.md
└── board-*/board.png
```

E output:

```text
orchestrator-test-ai-tools-overload/audio/narration.wav
orchestrator-test-ai-tools-overload/audio/voiceover_timing.json
orchestrator-test-ai-tools-overload/audio/captions.srt
orchestrator-test-ai-tools-overload/video/hyperframes/
orchestrator-test-ai-tools-overload/video/preview.mp4
orchestrator-test-ai-tools-overload/video/keyframes/contact_sheet_start.jpg
orchestrator-test-ai-tools-overload/video/keyframes/contact_sheet_done.jpg
orchestrator-test-ai-tools-overload/video/renderer_report.json
```

## 最终验收命令

```bash
python3 <repo-root>/whiteboard-infographic-pipeline-orchestrator/scripts/check_asset_identity.py \
  --project-dir <repo-root>/orchestrator-test-ai-tools-overload
```

Expected: `PASS`, every board reports `identical`.

## 通过标准

- B validator PASS.
- C validator PASS.
- Manual image handoff occurred; no placeholder entered D/E.
- `board_asset_manifest.json` points to `images/*.model-generated.png`.
- D package has per-board `board.png`, manifests, and motion plans.
- E produces real audio timing, subtitles, HyperFrames, MP4, and keyframes.
- Asset identity check PASS.
- `integration_report.md` records the manual image handoff, validation results, and any text drift.
