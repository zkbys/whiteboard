# Script Package Schema

## `voiceover_segments.json`

Required top-level fields:

```json
{
  "topic": "string",
  "style": "IP孵化/商业认知/AI认知类短视频",
  "targetDurationSec": 45,
  "estimatedDurationSec": 45.8,
  "segments": []
}
```

Required segment roles, in exact order:

```json
["hook", "反常识", "例子", "转折", "方法", "结论"]
```

Required segment fields:

```json
{
  "id": "seg-01-hook",
  "role": "hook",
  "text": "string",
  "caption": "string",
  "visualIntent": "string",
  "spokenAnchors": ["string"]
}
```

Recommended segment fields:

```json
{
  "boardId": "board-01",
  "targetElement": "stable_element_id",
  "targetDurationSec": 5.5,
  "pauseAfter": 0.18
}
```

Rules:

- `spokenAnchors` must be a non-empty string array.
- Every anchor must appear verbatim in `text` or `caption`.
- `caption` may equal `text` at this stage.
- `visualIntent` should describe what the board must communicate, not only how it looks.
- IDs should be lowercase ASCII with digits and hyphens.

## `visual_beats.json`

Required top-level fields:

```json
{
  "topic": "string",
  "visualStyle": "string",
  "beats": []
}
```

Required beat fields:

```json
{
  "id": "beat-01",
  "sourceSegmentId": "seg-01-hook",
  "boardId": "board-01",
  "priority": 1,
  "beatType": "contrast",
  "headline": "string",
  "visualIntent": "string",
  "spokenAnchors": ["string"],
  "keyObjects": [
    { "id": "stable_object_id", "label": "string", "role": "problem" }
  ],
  "annotationSuggestions": [
    { "type": "underline", "targetObjectId": "stable_object_id", "spokenAnchor": "string" }
  ]
}
```

Rules:

- `sourceSegmentId` must match a segment ID in `voiceover_segments.json`.
- `keyObjects[].id` should be stable snake_case.
- Keep beats sparse: 3-6 beats is usually enough for a 30-60 second video.
- Use `annotationSuggestions` only for meaningful emphasis points.

## Duration Estimate

The validator estimates duration using weighted text units:

```text
estimated seconds = (CJK characters + non-CJK words * 1.8) / chars_per_sec + pauses
```

Default `chars_per_sec` is `4.8`, tuned for concise Mandarin voiceover at a moderately fast short-video pace. The package should estimate between 30 and 60 seconds unless the user gives a different range.

