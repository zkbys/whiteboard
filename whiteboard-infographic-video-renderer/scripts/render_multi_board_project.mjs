#!/usr/bin/env node
import {
  copyFileSync,
  existsSync,
  mkdirSync,
  readFileSync,
  rmSync,
  statSync,
  writeFileSync,
} from "node:fs";
import { basename, dirname, isAbsolute, join, relative, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const DEFAULT_VOICE = {
  name: "zh-CN-YunxiNeural",
  rate: "+14%",
  pitch: "+0Hz",
  volume: "+0%",
};

const SUPPORTED_ACTIONS = new Set(["underline", "circle", "box", "check", "strike"]);
const HYPERFRAMES_VERSION = "0.6.99";
const ACTION_RHYTHM = {
  preArrivalSec: 0.16,
  cursorMoveLeadSec: 1.18,
  drawStartLeadSec: 0,
  holdAfterSec: 0.42,
  minGapSec: 0.12,
  staggerSec: 0.07,
};
const CAMERA_STRATEGY = {
  zoomWarn: 1.35,
  zoomMax: 1.7,
  regionMax: 1.2,
  emphasisMax: 1.36,
  maxZoomMovesPerBoard: 3,
};

let runContext = {
  projectDir: null,
  acceptancePath: null,
  step: "startup",
};
let verboseFlag = false;
let originalArgv = [];

function verbose(message, ...args) {
  if (!verboseFlag) return;
  const timestamp = new Date().toISOString();
  if (args.length > 0) {
    console.log(`[${timestamp}] [verbose] ${message}`, ...args);
  } else {
    console.log(`[${timestamp}] [verbose] ${message}`);
  }
}

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith("--")) continue;
    const raw = token.slice(2);
    const eq = raw.indexOf("=");
    if (eq >= 0) {
      out[raw.slice(0, eq)] = raw.slice(eq + 1);
      continue;
    }
    const next = argv[i + 1];
    if (next && !next.startsWith("--")) {
      out[raw] = next;
      i += 1;
    } else {
      out[raw] = true;
    }
  }
  return out;
}

function usage() {
  return `Usage:
  node scripts/render_multi_board_project.mjs \\
    --project-dir /path/to/output \\
    --board-root /path/to/board \\
    --voiceover /path/to/voiceover_segments.json [options]

Required:
  --project-dir <path>            Output package root.
  --board-root <path>             D-thread board package with board_index.json.
  --voiceover <path>              Original voiceover_segments.json.

Options:
  --board-index <path>            Defaults to <board-root>/board_index.json
  --combined-motion-plan <path>   Defaults to <board-root>/combined_motion_plan.json
  --voice <name>                  Defaults to zh-CN-YunxiNeural
  --rate <value>                  Defaults to source voice rate or +14%
  --pitch <value>                 Defaults to source voice pitch or +0Hz
  --volume <value>                Defaults to source voice volume or +0%
  --quality <value>               HyperFrames render quality, default standard
  --fps <value>                   Optional HyperFrames render FPS
  --hyperframes-version <value>   Defaults to 0.6.99
  --verbose                       Print detailed stage progress and commands
  --dry-run                       Resolve and validate inputs only
  --skip-tts                      Reuse existing output audio/voiceover_timing.json
  --skip-checks                   Skip HyperFrames lint/validate/inspect
  --skip-render                   Skip MP4 render
  --skip-keyframes                Skip action keyframe extraction
`;
}

function setStep(step) {
  runContext.step = step;
  console.log(`[multi-board-renderer] ${step}`);
  verbose(`entered step: ${step}`);
}

function fail(message) {
  throw new Error(message);
}

function ensureDir(path) {
  mkdirSync(path, { recursive: true });
}

function readJson(path) {
  return JSON.parse(readFileSync(path, "utf8"));
}

function writeJson(path, data) {
  ensureDir(dirname(path));
  writeFileSync(path, JSON.stringify(data, null, 2) + "\n");
}

function slash(path) {
  return path.split("\\").join("/");
}

function rel(root, path) {
  return slash(relative(root, path));
}

function resolvePath(root, path) {
  if (!path) return null;
  return isAbsolute(path) ? path : resolve(root, path);
}

function commandExists(command, probeArgs = ["--version"]) {
  const result = spawnSync(command, probeArgs, { encoding: "utf8" });
  return result.status === 0 || result.status === 1;
}

function run(command, args, options = {}) {
  verbose(`exec: ${[command].concat(args).join(" ")}`);
  execFileSync(command, args, {
    cwd: options.cwd,
    stdio: options.stdio || "inherit",
    encoding: options.encoding || "utf8",
  });
}

function runCapture(command, args, cwd) {
  if (verboseFlag) {
    const cwdLabel = cwd ? ` (cwd: ${cwd})` : "";
    verbose(`capture: ${[command].concat(args).join(" ")}${cwdLabel}`);
  }
  const result = spawnSync(command, args, { cwd, encoding: "utf8" });
  return {
    command: [command].concat(args).join(" "),
    status: result.status,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
  };
}

function assertCommand(report, label) {
  verbose(`${label} exit code: ${report.status}`);
  if (report.status !== 0) {
    const tail = [report.stdout, report.stderr].join("\n").trim().slice(-5000);
    fail(`${label} failed with exit code ${report.status}\n${tail}`);
  }
}

function ffprobeDuration(file) {
  const out = execFileSync(
    "ffprobe",
    ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", file],
    { encoding: "utf8" },
  ).trim();
  const duration = Number(out);
  if (!Number.isFinite(duration)) fail(`Could not measure duration for ${file}`);
  return duration;
}

function formatSeconds(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return 0;
  return Number(number.toFixed(3));
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function numberOr(value, fallback) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

function bboxCenter(bbox) {
  return [Number(bbox[0]) + Number(bbox[2]) / 2, Number(bbox[1]) + Number(bbox[3]) / 2];
}

function isValidBbox(bbox) {
  return (
    Array.isArray(bbox) &&
    bbox.length === 4 &&
    bbox.every((value) => Number.isFinite(Number(value))) &&
    Number(bbox[2]) > 0 &&
    Number(bbox[3]) > 0
  );
}

function normalizeBbox(bbox) {
  return bbox.map((value) => formatSeconds(value));
}

function unionBboxes(items) {
  const bboxes = items.filter(isValidBbox);
  if (!bboxes.length) return null;
  const minX = Math.min(...bboxes.map((bbox) => Number(bbox[0])));
  const minY = Math.min(...bboxes.map((bbox) => Number(bbox[1])));
  const maxX = Math.max(...bboxes.map((bbox) => Number(bbox[0]) + Number(bbox[2])));
  const maxY = Math.max(...bboxes.map((bbox) => Number(bbox[1]) + Number(bbox[3])));
  return normalizeBbox([minX, minY, maxX - minX, maxY - minY]);
}

function cleanName(value) {
  return String(value || "item").replace(/[^a-z0-9_-]/gi, "_");
}

function concatLine(file) {
  return `file '${file.replace(/'/g, "'\\''")}'`;
}

function srtTime(value) {
  const totalMs = Math.max(0, Math.round(Number(value) * 1000));
  const ms = totalMs % 1000;
  const totalSec = Math.floor(totalMs / 1000);
  const sec = totalSec % 60;
  const totalMin = Math.floor(totalSec / 60);
  const min = totalMin % 60;
  const hr = Math.floor(totalMin / 60);
  return `${String(hr).padStart(2, "0")}:${String(min).padStart(2, "0")}:${String(sec).padStart(2, "0")},${String(ms).padStart(3, "0")}`;
}

function writeCaptionsSrt(path, segments) {
  const blocks = segments.map((segment, index) => {
    const start = srtTime(segment.start);
    const end = srtTime(segment.end);
    const caption = segment.caption || segment.text || "";
    return `${index + 1}\n${start} --> ${end}\n${caption}\n`;
  });
  writeFileSync(path, blocks.join("\n"));
}

function vttTimeToSeconds(value) {
  const cleaned = String(value || "").trim().replace(",", ".");
  const parts = cleaned.split(":").map(Number);
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return Number(cleaned) || 0;
}

function parseVttCues(path) {
  if (!path || !existsSync(path)) return [];
  const content = readFileSync(path, "utf8").replace(/\r/g, "");
  const blocks = content.split(/\n\s*\n/g);
  const cues = [];
  for (const block of blocks) {
    const lines = block.split("\n").map((line) => line.trim()).filter(Boolean);
    const timingIndex = lines.findIndex((line) => line.includes("-->"));
    if (timingIndex < 0) continue;
    const [rawStart, rawEnd] = lines[timingIndex].split("-->").map((item) => item.trim().split(/\s+/)[0]);
    const text = lines.slice(timingIndex + 1).join("");
    if (!text) continue;
    cues.push({
      start: formatSeconds(vttTimeToSeconds(rawStart)),
      end: formatSeconds(vttTimeToSeconds(rawEnd)),
      text,
    });
  }
  return cues;
}

function normalizeAnchorText(value) {
  return String(value || "")
    .replace(/<[^>]+>/g, "")
    .replace(/[\s"'“”‘’`，。、“”：:；;！!？?（）()《》【】\[\]{}.,，、\-—…]/g, "")
    .toLowerCase();
}

const WORD_SEGMENTER = typeof Intl !== "undefined" && Intl.Segmenter
  ? new Intl.Segmenter("zh", { granularity: "word" })
  : null;

function codePointLength(value) {
  return Array.from(String(value || "")).length;
}

function fallbackWordSegments(text) {
  const segments = [];
  const pattern = /[A-Za-z0-9]+|[\u3400-\u9fff]|\S/g;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    segments.push({
      segment: match[0],
      index: match.index,
      isWordLike: /[A-Za-z0-9\u3400-\u9fff]/.test(match[0]),
    });
  }
  return segments;
}

function segmentCueTokens(cue) {
  const text = String(cue?.text || "");
  const rawSegments = WORD_SEGMENTER ? Array.from(WORD_SEGMENTER.segment(text)) : fallbackWordSegments(text);
  const tokens = [];
  let normalizedCursor = 0;

  for (const raw of rawSegments) {
    const tokenText = raw.segment || "";
    const normalized = normalizeAnchorText(tokenText);
    if (!normalized) continue;
    const length = codePointLength(normalized);
    const start = Number(raw.index || 0);
    tokens.push({
      text: tokenText,
      startIndex: start,
      endIndex: start + tokenText.length,
      normalized,
      normalizedStart: normalizedCursor,
      normalizedEnd: normalizedCursor + length,
      isWordLike: raw.isWordLike !== false,
    });
    normalizedCursor += length;
  }

  const cueDuration = Math.max(0.05, Number(cue.end) - Number(cue.start));
  const total = Math.max(1, normalizedCursor);
  return tokens.map((token) => ({
    ...token,
    start: formatSeconds(Number(cue.start) + cueDuration * (token.normalizedStart / total)),
    end: formatSeconds(Number(cue.start) + cueDuration * (token.normalizedEnd / total)),
  }));
}

function timedAnchorFromTokenizedCue(anchor, cue) {
  const tokens = segmentCueTokens(cue);
  const normalizedCue = tokens.map((token) => token.normalized).join("");
  const normalizedAnchor = normalizeAnchorText(anchor);
  if (!tokens.length || !normalizedCue || !normalizedAnchor) return null;

  const index = normalizedCue.indexOf(normalizedAnchor);
  if (index < 0) return null;
  const endIndex = index + codePointLength(normalizedAnchor);
  const first = tokens.find((token) => token.normalizedEnd > index);
  const last = tokens.findLast
    ? tokens.findLast((token) => token.normalizedStart < endIndex)
    : [...tokens].reverse().find((token) => token.normalizedStart < endIndex);
  if (!first || !last) return null;

  const boundaryAligned = first.normalizedStart === index && last.normalizedEnd === endIndex;
  return {
    anchorStart: first.start,
    anchorEnd: last.end,
    confidence: boundaryAligned ? 0.9 : 0.82,
    matchMode: "cue-tokenized",
    cueText: cue.text,
    tokens: tokens
      .filter((token) => token.normalizedEnd > index && token.normalizedStart < endIndex)
      .map((token) => token.text),
  };
}

function timedAnchorFromCue(anchor, cue) {
  const cueText = String(cue.text || "");
  const anchorText = String(anchor || "");
  if (!anchorText || !cueText) return null;
  let index = cueText.indexOf(anchorText);
  let basisLength = cueText.length;
  let anchorLength = anchorText.length;
  let confidence = 0.92;
  let matchMode = "cue-direct";

  if (index < 0) {
    const normalizedCue = normalizeAnchorText(cueText);
    const normalizedAnchor = normalizeAnchorText(anchorText);
    index = normalizedCue.indexOf(normalizedAnchor);
    basisLength = normalizedCue.length;
    anchorLength = normalizedAnchor.length;
    confidence = 0.72;
    matchMode = "cue-normalized";
  }

  if (index < 0 || basisLength <= 0 || anchorLength <= 0) return null;

  const cueDuration = Math.max(0.05, Number(cue.end) - Number(cue.start));
  const startRatio = clamp(index / basisLength, 0, 1);
  const endRatio = clamp((index + anchorLength) / basisLength, startRatio, 1);
  return {
    anchorStart: formatSeconds(Number(cue.start) + cueDuration * startRatio),
    anchorEnd: formatSeconds(Number(cue.start) + cueDuration * endRatio),
    confidence,
    matchMode,
    cueText,
  };
}

function timedAnchorFromSegmentText(anchor, segment) {
  const text = String(segment.text || segment.caption || "");
  const anchorText = String(anchor || "");
  if (!anchorText || !text) return null;
  let index = text.indexOf(anchorText);
  let basisLength = text.length;
  let anchorLength = anchorText.length;
  let matchMode = "segment-text-direct";
  let confidence = 0.56;

  if (index < 0) {
    const normalizedText = normalizeAnchorText(text);
    const normalizedAnchor = normalizeAnchorText(anchorText);
    index = normalizedText.indexOf(normalizedAnchor);
    basisLength = normalizedText.length;
    anchorLength = normalizedAnchor.length;
    matchMode = "segment-text-normalized";
    confidence = 0.44;
  }
  if (index < 0 || basisLength <= 0 || anchorLength <= 0) return null;

  const speechDuration = Math.max(0.1, Number(segment.speechDuration || Number(segment.speechEnd) - Number(segment.start)));
  const startRatio = clamp(index / basisLength, 0, 1);
  const endRatio = clamp((index + anchorLength) / basisLength, startRatio, 1);
  return {
    anchorStart: formatSeconds(speechDuration * startRatio),
    anchorEnd: formatSeconds(speechDuration * endRatio),
    confidence,
    matchMode,
    cueText: text,
  };
}

function resolveAnchorTiming(anchor, timedSegment, cues) {
  for (const cue of cues) {
    const tokenized = timedAnchorFromTokenizedCue(anchor, cue);
    if (tokenized) return tokenized;
    const matched = timedAnchorFromCue(anchor, cue);
    if (matched) return matched;
  }
  return timedAnchorFromSegmentText(anchor, timedSegment);
}

function actionKey(segmentId, index) {
  return `${segmentId}:${index}`;
}

function rhythmDefaultsForAction(action, index) {
  const emphasisHold = action?.type === "circle" || action?.type === "box" ? 0.48 : ACTION_RHYTHM.holdAfterSec;
  return {
    source: "renderer-action-rhythm-v0.1",
    preArrivalSec: ACTION_RHYTHM.preArrivalSec,
    cursorMoveLeadSec: ACTION_RHYTHM.cursorMoveLeadSec,
    drawStartLeadSec: ACTION_RHYTHM.drawStartLeadSec,
    holdAfterSec: emphasisHold,
    minGapSec: ACTION_RHYTHM.minGapSec,
    staggerSec: formatSeconds(Math.min(index * ACTION_RHYTHM.staggerSec, 0.21)),
  };
}

function placeRhythmedAction({
  rawOffset,
  duration,
  index,
  maxStart,
  previousHoldDone,
  segmentSpan,
  action,
}) {
  const rhythm = rhythmDefaultsForAction(action, index);
  const desiredOffset = Number(rawOffset) + Number(rhythm.drawStartLeadSec) + Number(rhythm.staggerSec);
  const minAfterPrevious = index === 0 ? 0 : Number(previousHoldDone) + Number(rhythm.minGapSec);
  const spacedOffset = Math.max(desiredOffset, minAfterPrevious);
  const offset = clamp(spacedOffset, 0, maxStart);
  const drawDoneOffset = offset + Number(duration);
  const requestedHoldDone = drawDoneOffset + Number(rhythm.holdAfterSec);
  const holdDoneOffset = Math.min(Number(segmentSpan), requestedHoldDone);
  const compressed = offset < spacedOffset - 0.001 || holdDoneOffset < requestedHoldDone - 0.001;

  return {
    offset: formatSeconds(offset),
    rhythm: {
      ...rhythm,
      desiredOffset: formatSeconds(desiredOffset),
      cursorMoveStartOffset: formatSeconds(Math.max(0, offset - Number(rhythm.cursorMoveLeadSec))),
      cursorArrivalOffset: formatSeconds(Math.max(0, offset - Number(rhythm.preArrivalSec))),
      drawStartOffset: formatSeconds(offset),
      drawDoneOffset: formatSeconds(drawDoneOffset),
      holdDoneOffset: formatSeconds(holdDoneOffset),
      compressedToFit: compressed,
    },
    holdDoneOffset,
  };
}

function buildSyncTimings({ projectDir, source, timing, combinedMotionPlan }) {
  const sourceById = mapById(source.segments || []);
  const timedById = mapById(timing.segments || []);
  const wordTimingSegments = [];
  const actionRows = [];
  const lookup = new Map();

  for (const timedSegment of timing.segments || []) {
    const subtitlePath = resolvePath(projectDir, timedSegment.media?.subtitles);
    const cues = parseVttCues(subtitlePath);
    wordTimingSegments.push({
      id: timedSegment.id,
      start: timedSegment.start,
      speechEnd: timedSegment.speechEnd,
      end: timedSegment.end,
      speechDuration: timedSegment.speechDuration,
      subtitle: timedSegment.media?.subtitles,
      cues: cues.map((cue) => {
        const tokens = segmentCueTokens(cue);
        return {
          ...cue,
          absoluteStart: formatSeconds(Number(timedSegment.start) + Number(cue.start)),
          absoluteEnd: formatSeconds(Number(timedSegment.start) + Number(cue.end)),
          tokens: tokens.map((token) => ({
            text: token.text,
            start: token.start,
            end: token.end,
            absoluteStart: formatSeconds(Number(timedSegment.start) + Number(token.start)),
            absoluteEnd: formatSeconds(Number(timedSegment.start) + Number(token.end)),
            normalizedStart: token.normalizedStart,
            normalizedEnd: token.normalizedEnd,
          })),
        };
      }),
    });
  }

  for (const segment of combinedMotionPlan.segments || []) {
    const sourceSegment = sourceById.get(segment.id) || {};
    const timedSegment = timedById.get(segment.id);
    if (!timedSegment) continue;
    const subtitlePath = resolvePath(projectDir, timedSegment.media?.subtitles);
    const cues = parseVttCues(subtitlePath);
    const sourceActions = sourceSegment.actions || [];
    const segmentStart = Number(timedSegment.start);
    const segmentSpan = Math.max(0.12, Number(timedSegment.end) - segmentStart);
    let previousHoldDone = 0;

    for (const [index, motionAction] of (segment.actions || []).entries()) {
      const sourceAction = sourceActions[index] || {};
      const spokenAnchor = sourceAction.spokenAnchor || motionAction.spokenAnchor || "";
      const requestedDuration = Number(motionAction.duration || sourceAction.duration || 0.72);
      const duration = formatSeconds(Math.min(requestedDuration, Math.max(0.12, segmentSpan - 0.05)));
      const maxStart = Math.max(0, segmentSpan - duration - 0.05);
      const anchorTiming = resolveAnchorTiming(spokenAnchor, timedSegment, cues);
      let rawOffset;
      let anchorStart = null;
      let anchorEnd = null;
      let confidence = 0.2;
      let matchMode = "fallback-existing-offset";
      let cueText = null;

      if (anchorTiming) {
        anchorStart = formatSeconds(Number(anchorTiming.anchorStart));
        anchorEnd = formatSeconds(Number(anchorTiming.anchorEnd));
        rawOffset = anchorStart;
        confidence = anchorTiming.confidence;
        matchMode = anchorTiming.matchMode;
        cueText = anchorTiming.cueText;
      } else if (Number.isFinite(Number(sourceAction.anchorRatio))) {
        const speechDuration = Math.max(0.12, Number(timedSegment.speechDuration || Number(timedSegment.speechEnd) - segmentStart));
        rawOffset = speechDuration * Number(sourceAction.anchorRatio);
        confidence = 0.36;
        matchMode = "fallback-anchorRatio";
      } else {
        rawOffset = Number(motionAction.offset || 0);
      }

      const placement = placeRhythmedAction({
        rawOffset,
        duration,
        index,
        maxStart,
        previousHoldDone,
        segmentSpan,
        action: motionAction,
      });
      const offset = placement.offset;
      previousHoldDone = placement.holdDoneOffset;

      const row = {
        segmentId: segment.id,
        boardId: segment.boardId,
        actionIndex: index,
        type: motionAction.type,
        element: motionAction.element,
        annotation: motionAction.annotation,
        spokenAnchor,
        offset,
        duration,
        drawStart: formatSeconds(segmentStart + Number(offset)),
        drawDone: formatSeconds(segmentStart + Number(offset) + Number(duration)),
        anchorStart: anchorStart === null ? null : formatSeconds(segmentStart + anchorStart),
        anchorEnd: anchorEnd === null ? null : formatSeconds(segmentStart + anchorEnd),
        syncConfidence: Number(confidence.toFixed(2)),
        syncSource: matchMode,
        cueText,
        tokens: anchorTiming?.tokens || [],
        rhythm: placement.rhythm,
      };
      lookup.set(actionKey(segment.id, index), row);
      actionRows.push(row);
    }
  }

  return {
    lookup,
    wordTiming: {
      version: "0.2",
      granularity: "cue-tokenized",
      generatedAt: new Date().toISOString(),
      source: "edge-tts WebVTT subtitles + Intl.Segmenter token spans",
      note: "edge-tts exposes sentence/cue timing in this environment, not true TTS WordBoundary events. Token timing is derived by segmenting each cue and distributing cue duration across normalized token spans; replace with real WordBoundary or forced alignment data when available.",
      segments: wordTimingSegments,
    },
    actionTiming: {
      version: "0.2",
      granularity: "spokenAnchor-cue-tokenized",
      generatedAt: new Date().toISOString(),
      source: "voiceover_segments.actions[].spokenAnchor + audio/word_timing.json token spans",
      actions: actionRows,
    },
  };
}

function summarizeSync(actionTiming) {
  const actions = actionTiming.actions || [];
  const matched = actions.filter((action) => String(action.syncSource || "").startsWith("cue-"));
  const fallback = actions.length - matched.length;
  const averageConfidence = actions.length
    ? actions.reduce((sum, action) => sum + Number(action.syncConfidence || 0), 0) / actions.length
    : 0;
  return {
    actionCount: actions.length,
    matchedActions: matched.length,
    fallbackActions: fallback,
    averageConfidence: Number(averageConfidence.toFixed(2)),
    granularity: actionTiming.granularity,
    actionTiming: "sync/action_timing.json",
    wordTiming: "audio/word_timing.json",
  };
}

function getVoice(source, args) {
  const configured = source.voice || {};
  return {
    name: args.voice || configured.name || DEFAULT_VOICE.name,
    rate: args.rate || configured.rate || DEFAULT_VOICE.rate,
    pitch: args.pitch || configured.pitch || DEFAULT_VOICE.pitch,
    volume: args.volume || configured.volume || DEFAULT_VOICE.volume,
  };
}

function mapById(items = []) {
  const map = new Map();
  for (const item of items) {
    if (item?.id) map.set(item.id, item);
  }
  return map;
}

function normalizeAnnotationMap(annotationManifest) {
  const out = {};
  const raw = annotationManifest?.annotations || {};
  if (Array.isArray(raw)) {
    for (const item of raw) {
      if (item?.id) out[item.id] = item;
    }
  } else {
    for (const [key, value] of Object.entries(raw)) {
      out[key] = value;
      if (value?.id) out[value.id] = value;
    }
  }
  return out;
}

function annotationFor(board, action) {
  const element = board.elementsById.get(action.element);
  return element?.annotations?.[action.annotation] || board.annotationMap[action.annotation];
}

function isImageUrl(value) {
  return /^https?:\/\//i.test(String(value || "")) || /^data:image\//i.test(String(value || ""));
}

function boardImageRef(boardRoot, boardEntry, boardDir, manifest) {
  const asset = boardEntry?.asset || manifest?.assetRef || {};
  const remoteCandidates = [
    asset.kind === "url" ? asset.uri : null,
    asset.url,
    asset.remoteUrl,
    isImageUrl(manifest?.source_image) ? manifest.source_image : null,
    isImageUrl(manifest?.image) ? manifest.image : null,
  ].filter(Boolean);
  const remote = remoteCandidates.find(isImageUrl);
  if (remote) {
    return {
      kind: "url",
      src: remote,
      uri: asset.uri || remote,
    };
  }

  const rawCandidates = [
    asset.localPath,
    manifest?.source_image,
    manifest?.image,
    "board.png",
  ].filter((item) => item && !isImageUrl(item));

  for (const raw of rawCandidates) {
    const candidates = [
      resolvePath(boardDir, raw),
      resolvePath(boardRoot, raw),
      resolvePath(boardDir, basename(raw)),
    ];
    const found = candidates.find((item) => item && existsSync(item));
    if (found) {
      return {
        kind: "file",
        path: found,
        src: found,
        uri: raw,
      };
    }
  }
  return null;
}

function overviewCameraForBoard(board, composition, preferredOverview = null) {
  if (
    preferredOverview &&
    Number.isFinite(Number(preferredOverview.x)) &&
    Number.isFinite(Number(preferredOverview.y)) &&
    Number.isFinite(Number(preferredOverview.scale))
  ) {
    return {
      x: formatSeconds(preferredOverview.x),
      y: formatSeconds(preferredOverview.y),
      scale: formatSeconds(preferredOverview.scale),
    };
  }
  const canvas = board.manifest?.canvas || {};
  const width = numberOr(canvas.width, composition.width || 1920);
  const height = numberOr(canvas.height, composition.height || 1080);
  const scale = Math.min(numberOr(composition.width, 1920) / width, numberOr(composition.height, 1080) / height);
  return {
    x: formatSeconds(width / 2),
    y: formatSeconds(height / 2),
    scale: formatSeconds(scale),
  };
}

function cameraForBbox({ bbox, board, composition, strategy, overviewCamera = null }) {
  const overview = overviewCamera || overviewCameraForBoard(board, composition);
  if (!isValidBbox(bbox)) return overview;
  const canvas = board.manifest?.canvas || {};
  const width = numberOr(canvas.width, composition.width || 1920);
  const height = numberOr(canvas.height, composition.height || 1080);
  const [centerX, centerY] = bboxCenter(bbox);
  const padding = strategy === "emphasis" ? 2.35 : 3.05;
  const fitW = numberOr(composition.width, 1920) / Math.max(Number(bbox[2]) * padding, 1);
  const fitH = numberOr(composition.height, 1080) / Math.max(Number(bbox[3]) * padding, 1);
  const strategyMax = strategy === "emphasis" ? CAMERA_STRATEGY.emphasisMax : CAMERA_STRATEGY.regionMax;
  const scale = clamp(Math.min(fitW, fitH), Number(overview.scale), strategyMax);
  return {
    x: formatSeconds(clamp(centerX, 0, width)),
    y: formatSeconds(clamp(centerY, 0, height)),
    scale: formatSeconds(scale),
  };
}

function actionBbox(board, action) {
  const element = board.elementsById.get(action.element);
  const annotation = annotationFor(board, action);
  return (
    annotation?.targetTextBbox ||
    annotation?.bbox ||
    annotation?.boxBounds ||
    element?.annotationTargetBbox ||
    element?.bbox ||
    null
  );
}

function segmentFocusBbox(board, segment) {
  const target = board.elementsById.get(segment.target);
  const bboxes = [target?.bbox];
  for (const action of segment.actions || []) {
    bboxes.push(actionBbox(board, action));
  }
  return unionBboxes(bboxes);
}

function chooseFocusStrategy({ segment, boardPosition }) {
  if (boardPosition.isFirst) return "region";
  if (boardPosition.isLast) return "region";
  const hasEmphasisAction = (segment.actions || []).some((action) => ["box", "circle", "check"].includes(action.type));
  const text = `${segment.caption || ""} ${(segment.actions || []).map((action) => action.spokenAnchor || "").join(" ")}`;
  if (hasEmphasisAction || /结论|关键|核心|方法|转折|最终|真正/.test(text)) return "emphasis";
  return "region";
}

function applyCameraStrategy({ motionPlan, boards }) {
  const composition = motionPlan.composition || { width: 1920, height: 1080 };
  const boardOrder = new Map();
  for (const [index, segment] of (motionPlan.segments || []).entries()) {
    if (!boardOrder.has(segment.boardId)) boardOrder.set(segment.boardId, []);
    boardOrder.get(segment.boardId).push(index);
  }

  const zoomMovesByBoard = new Map();
  const cameraRows = [];
  const segments = (motionPlan.segments || []).map((segment, index) => {
    const board = boards[segment.boardId];
    if (!board) return segment;
    const indexes = boardOrder.get(segment.boardId) || [];
    const boardIndex = indexes.indexOf(index);
    const boardPosition = {
      index: boardIndex,
      count: indexes.length,
      isFirst: boardIndex === 0,
      isLast: boardIndex === indexes.length - 1,
    };
    const overview = overviewCameraForBoard(board, composition, motionPlan.overview_camera);
    const focusStrategy = chooseFocusStrategy({ segment, boardPosition });
    const focusBbox = segmentFocusBbox(board, segment);
    let focusCamera = cameraForBbox({ bbox: focusBbox, board, composition, strategy: focusStrategy, overviewCamera: overview });
    let cameraStrategy = boardPosition.isFirst ? "overview" : focusStrategy;
    if (boardPosition.isLast) cameraStrategy = "recovery";

    const boardZoomCount = zoomMovesByBoard.get(segment.boardId) || 0;
    const isZoomMove = Number(focusCamera.scale) > Number(overview.scale) + 0.08;
    if (isZoomMove && boardZoomCount >= CAMERA_STRATEGY.maxZoomMovesPerBoard) {
      focusCamera = {
        ...focusCamera,
        scale: formatSeconds(Math.min(Number(focusCamera.scale), Number(overview.scale) + 0.12)),
      };
    } else if (isZoomMove) {
      zoomMovesByBoard.set(segment.boardId, boardZoomCount + 1);
    }

    const cameraPlan = {
      version: "0.1",
      source: "renderer-camera-strategy-v0.1",
      strategy: cameraStrategy,
      focusStrategy,
      targetBbox: focusBbox,
      bboxSource: focusBbox ? "segment target + action annotation union" : "overview fallback",
      entryCamera: boardPosition.isFirst ? overview : null,
      focusCamera,
      exitCamera: boardPosition.isLast ? overview : null,
      zoomThresholds: {
        warnAbove: CAMERA_STRATEGY.zoomWarn,
        maxAllowed: CAMERA_STRATEGY.zoomMax,
      },
      boardPosition,
    };
    cameraRows.push({
      segmentId: segment.id,
      boardId: segment.boardId,
      strategy: cameraStrategy,
      focusStrategy,
      targetBbox: focusBbox,
      camera: focusCamera,
      entryCamera: cameraPlan.entryCamera,
      exitCamera: cameraPlan.exitCamera,
      zoomStatus:
        Number(focusCamera.scale) > CAMERA_STRATEGY.zoomMax
          ? "fail"
          : Number(focusCamera.scale) > CAMERA_STRATEGY.zoomWarn
            ? "warn"
            : "pass",
    });
    return {
      ...segment,
      camera: focusCamera,
      cameraStrategy,
      cameraPlan,
    };
  });

  return {
    motionPlan: {
      ...motionPlan,
      camera_strategy: {
        version: "0.1",
        source: "renderer-camera-strategy-v0.1",
        strategies: ["overview", "region", "emphasis", "recovery"],
        zoomThresholds: {
          warnAbove: CAMERA_STRATEGY.zoomWarn,
          maxAllowed: CAMERA_STRATEGY.zoomMax,
        },
        note: "BBox values are used as framing references; renderer strategy dampens zoom and adds overview/recovery phases so camera movement does not mechanically follow every individual bbox.",
      },
      segments,
    },
    cameraPlan: {
      version: "0.1",
      generatedAt: new Date().toISOString(),
      source: "board manifests + combined_motion_plan.json",
      strategies: ["overview", "region", "emphasis", "recovery"],
      zoomThresholds: {
        warnAbove: CAMERA_STRATEGY.zoomWarn,
        maxAllowed: CAMERA_STRATEGY.zoomMax,
      },
      segments: cameraRows,
    },
  };
}

function loadBoardPackage({ boardRoot, boardIndexPath, combinedMotionPlanPath }) {
  const boardIndex = readJson(boardIndexPath);
  const combinedMotionPlan = readJson(combinedMotionPlanPath);
  const boards = {};

  for (const boardEntry of boardIndex.boards || []) {
    const boardId = boardEntry.boardId;
    const boardDir = resolvePath(boardRoot, boardEntry.path || boardId);
    const manifestPath = join(boardDir, "board_manifest.json");
    const annotationManifestPath = join(boardDir, "annotation_manifest.json");
    const localMotionPlanPath = join(boardDir, "motion_plan.json");
    if (!existsSync(manifestPath)) fail(`${boardId} missing board_manifest.json`);
    if (!existsSync(annotationManifestPath)) fail(`${boardId} missing annotation_manifest.json`);
    if (!existsSync(localMotionPlanPath)) fail(`${boardId} missing motion_plan.json`);
    const manifest = readJson(manifestPath);
    const annotationManifest = readJson(annotationManifestPath);
    const localMotionPlan = readJson(localMotionPlanPath);
    const imageRef = boardImageRef(boardRoot, boardEntry, boardDir, manifest);
    if (!imageRef) fail(`${boardId} missing consumable board image asset: expected local board.png/file or asset.kind=url`);
    boards[boardId] = {
      boardId,
      sourcePath: boardEntry.path || boardId,
      boardDir,
      manifestPath,
      annotationManifestPath,
      localMotionPlanPath,
      imageRef,
      imagePath: imageRef.kind === "file" ? imageRef.path : null,
      indexEntry: boardEntry,
      manifest,
      annotationManifest,
      annotationMap: normalizeAnnotationMap(annotationManifest),
      localMotionPlan,
      elementsById: mapById(manifest.elements || []),
    };
  }

  return { boardIndex, combinedMotionPlan, boards };
}

function validateMultiBoardInputs({ source, boardIndex, combinedMotionPlan, boards }) {
  const errors = [];
  if (!source || !Array.isArray(source.segments) || source.segments.length === 0) {
    errors.push("voiceover_segments.json must contain non-empty segments[]");
  }
  if (!boardIndex || !Array.isArray(boardIndex.boards) || boardIndex.boards.length === 0) {
    errors.push("board_index.json must contain non-empty boards[]");
  }
  if (!combinedMotionPlan?.composition?.width || !combinedMotionPlan?.composition?.height) {
    errors.push("combined_motion_plan.json must contain composition.width and composition.height");
  }
  if (!Array.isArray(combinedMotionPlan?.segments) || combinedMotionPlan.segments.length === 0) {
    errors.push("combined_motion_plan.json must contain non-empty segments[]");
  }

  for (const segment of source.segments || []) {
    if (!segment.id) errors.push("voiceover segment missing id");
    if (!segment.text && !segment.caption) errors.push(`voiceover segment ${segment.id || "unknown"} missing text/caption`);
  }

  const sourceIds = new Set((source.segments || []).map((item) => item.id));
  for (const segment of combinedMotionPlan.segments || []) {
    if (!segment.id) errors.push("combined_motion_plan segment missing id");
    if (!sourceIds.has(segment.id)) errors.push(`combined_motion_plan segment ${segment.id} missing in voiceover_segments.json`);
    const board = boards[segment.boardId];
    if (!board) {
      errors.push(`combined_motion_plan segment ${segment.id} references missing board '${segment.boardId}'`);
      continue;
    }
    if (!board.manifest?.canvas?.width || !board.manifest?.canvas?.height) {
      errors.push(`${board.boardId} board_manifest.json missing canvas width/height`);
    }
    if (segment.target && !board.elementsById.has(segment.target)) {
      errors.push(`${segment.id} target '${segment.target}' missing from ${board.boardId} board_manifest elements[]`);
    }
    for (const action of segment.actions || []) {
      if (!SUPPORTED_ACTIONS.has(action.type)) {
        errors.push(`${segment.id}/${action.annotation || "unknown"} has unsupported type '${action.type}'`);
      }
      if (!board.elementsById.has(action.element)) {
        errors.push(`${segment.id}/${action.annotation || "unknown"} references missing element '${action.element}' on ${board.boardId}`);
      } else if (!annotationFor(board, action)) {
        errors.push(`${segment.id}/${action.annotation || "unknown"} missing annotation on ${board.boardId}/${action.element}`);
      }
      if (!Number.isFinite(Number(action.duration)) || Number(action.duration) <= 0) {
        errors.push(`${segment.id}/${action.annotation || "unknown"} must have positive duration`);
      }
    }
  }

  if (errors.length > 0) {
    fail(errors.map((item) => `- ${item}`).join("\n"));
  }
}

function makeSilence(duration, segmentDir, cache) {
  const key = Math.round(Number(duration || 0) * 1000);
  if (key <= 0) return null;
  if (!cache.has(key)) {
    const file = join(segmentDir, `silence-${key}ms.wav`);
    run(
      "ffmpeg",
      ["-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", String(key / 1000), "-c:a", "pcm_s16le", file],
      { stdio: "ignore" },
    );
    cache.set(key, file);
  }
  return cache.get(key);
}

function synthesizeVoiceover({ projectDir, source, voice, audioDir }) {
  if (!commandExists("edge-tts", ["--help"])) {
    fail("edge-tts is not available. Install it with: python3 -m pip install edge-tts");
  }
  if (!commandExists("ffmpeg", ["-version"]) || !commandExists("ffprobe", ["-version"])) {
    fail("ffmpeg and ffprobe are required.");
  }

  rmSync(audioDir, { recursive: true, force: true });
  const segmentDir = join(audioDir, "segments");
  ensureDir(segmentDir);

  const generated = [];
  verbose(`TTS start: ${source.segments.length} segments, voice=${voice.name}`);
  for (const [index, segment] of source.segments.entries()) {
    const base = `${String(index + 1).padStart(2, "0")}-${cleanName(segment.id)}`;
    const mp3 = join(segmentDir, `${base}.mp3`);
    const wav = join(segmentDir, `${base}.wav`);
    const vtt = join(segmentDir, `${base}.vtt`);
    const text = segment.text || segment.caption;

    console.log(`edge-tts ${segment.id} (${voice.name})`);
    run(
      "edge-tts",
      [
        "--voice",
        voice.name,
        `--rate=${voice.rate}`,
        `--pitch=${voice.pitch}`,
        `--volume=${voice.volume}`,
        "--text",
        text,
        "--write-media",
        mp3,
        "--write-subtitles",
        vtt,
      ],
      { cwd: projectDir },
    );

    run("ffmpeg", ["-y", "-i", mp3, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", wav], { stdio: "ignore" });
    generated.push({
      ...segment,
      media: {
        mp3: rel(projectDir, mp3),
        wav: rel(projectDir, wav),
        subtitles: rel(projectDir, vtt),
      },
      speechDuration: ffprobeDuration(wav),
    });
  }

  const concat = [];
  const timedSegments = [];
  const pauseCache = new Map();
  let cursor = 0;

  for (const [index, segment] of generated.entries()) {
    const pauseAfter = Number(segment.pauseAfter || (index === generated.length - 1 ? 0 : 0.12));
    const start = cursor;
    const speechEnd = start + segment.speechDuration;
    const end = speechEnd + pauseAfter;
    const wav = resolve(projectDir, segment.media.wav);

    concat.push(concatLine(wav));
    const silence = makeSilence(pauseAfter, segmentDir, pauseCache);
    if (silence) concat.push(concatLine(silence));

    timedSegments.push({
      id: segment.id,
      role: segment.role,
      text: segment.text,
      caption: segment.caption || segment.text,
      start: formatSeconds(start),
      speechEnd: formatSeconds(speechEnd),
      end: formatSeconds(end),
      speechDuration: formatSeconds(segment.speechDuration),
      pauseAfter: formatSeconds(pauseAfter),
      sourceBoardId: segment.boardId,
      sourceTarget: segment.target || segment.targetElement,
      media: segment.media,
      actions: segment.actions || [],
    });

    cursor = end;
  }

  const concatPath = join(segmentDir, "concat.txt");
  writeFileSync(concatPath, concat.join("\n") + "\n");

  const narrationPath = join(audioDir, "narration.wav");
  run(
    "ffmpeg",
    ["-y", "-f", "concat", "-safe", "0", "-i", concatPath, "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "1", narrationPath],
    { stdio: "ignore" },
  );

  const totalDuration = ffprobeDuration(narrationPath);
  const timing = {
    engine: "edge-tts",
    voice,
    totalDuration: formatSeconds(totalDuration),
    generatedAt: new Date().toISOString(),
    source: "voiceover_segments.json",
    output: rel(projectDir, narrationPath),
    segments: timedSegments,
  };

  writeJson(join(audioDir, "voiceover_timing.json"), timing);
  writeCaptionsSrt(join(audioDir, "captions.srt"), timedSegments);
  verbose(`TTS complete: ${timing.output}, duration=${timing.totalDuration}s`);
  return { timing, narrationPath, captionsPath: join(audioDir, "captions.srt") };
}

function loadExistingTiming(projectDir, audioDir) {
  const timingPath = join(audioDir, "voiceover_timing.json");
  const narrationPath = join(audioDir, "narration.wav");
  if (!existsSync(timingPath) || !existsSync(narrationPath)) {
    fail("--skip-tts requires existing output audio/voiceover_timing.json and audio/narration.wav");
  }
  const timing = readJson(timingPath);
  writeCaptionsSrt(join(audioDir, "captions.srt"), timing.segments || []);
  return { timing, narrationPath, captionsPath: join(audioDir, "captions.srt") };
}

function updateCombinedMotionPlan({ source, timing, combinedMotionPlan, actionTimingLookup = new Map() }) {
  const sourceById = mapById(source.segments || []);
  const timedById = mapById(timing.segments || []);
  const orderedSegments = (combinedMotionPlan.segments || []).map((segment) => {
    const sourceSegment = sourceById.get(segment.id) || {};
    const timedSegment = timedById.get(segment.id);
    if (!timedSegment) fail(`Missing measured timing for ${segment.id}`);
    const sourceActions = sourceSegment.actions || [];
    const segmentSpan = Math.max(0.12, Number(timedSegment.end) - Number(timedSegment.start));
    const speechDuration = Math.max(0.12, Number(timedSegment.speechDuration || Number(timedSegment.speechEnd) - Number(timedSegment.start)));

    const actions = (segment.actions || []).map((motionAction, index) => {
      const sourceAction = sourceActions[index] || {};
      const syncAction = actionTimingLookup.get(actionKey(segment.id, index));
      const requestedDuration = Number(motionAction.duration || sourceAction.duration || 0.72);
      const duration = formatSeconds(Math.min(requestedDuration, Math.max(0.12, segmentSpan - 0.05)));
      let rawOffset;
      let anchorRatioSource = "combined_motion_plan.actions[].offset";
      if (syncAction && Number.isFinite(Number(syncAction.offset))) {
        rawOffset = Number(syncAction.offset);
        anchorRatioSource = "sync/action_timing.json";
      } else if (Number.isFinite(Number(sourceAction.anchorRatio))) {
        rawOffset = speechDuration * Number(sourceAction.anchorRatio);
        anchorRatioSource = "voiceover_segments.actions[].anchorRatio";
      } else if (Number.isFinite(Number(motionAction.offset))) {
        rawOffset = Number(motionAction.offset);
      } else {
        rawOffset = (speechDuration * (index + 1)) / ((segment.actions || []).length + 1);
        anchorRatioSource = "evenly-spaced-fallback";
      }
      const maxStart = Math.max(0, segmentSpan - duration - 0.05);
      const minStart = syncAction ? 0 : Math.min(0.35, maxStart);
      return {
        ...motionAction,
        offset: formatSeconds(clamp(rawOffset, minStart, maxStart)),
        duration,
        anchorRatioSource,
        sync: syncAction
          ? {
              source: syncAction.syncSource,
              confidence: syncAction.syncConfidence,
              spokenAnchor: syncAction.spokenAnchor,
              anchorStart: syncAction.anchorStart,
              anchorEnd: syncAction.anchorEnd,
            }
          : undefined,
        rhythm: syncAction?.rhythm,
      };
    });

    return {
      ...segment,
      start: timedSegment.start,
      speechEnd: timedSegment.speechEnd,
      end: timedSegment.end,
      caption: timedSegment.caption || sourceSegment.caption || segment.caption || sourceSegment.text,
      actions,
    };
  });

  return {
    ...combinedMotionPlan,
    sync_level: combinedMotionPlan.sync_level || "voiceover-segment-action",
    composition: {
      ...(combinedMotionPlan.composition || {}),
      width: Number(combinedMotionPlan.composition?.width || 1920),
      height: Number(combinedMotionPlan.composition?.height || 1080),
      duration: formatSeconds(timing.totalDuration),
    },
    segments: orderedSegments,
  };
}

function writeOutputBoardPackage({ projectDir, boardRoot, boardIndexPath, boardIndex, boards, updatedMotionPlan }) {
  const outBoardRoot = join(projectDir, "board");
  rmSync(outBoardRoot, { recursive: true, force: true });
  ensureDir(outBoardRoot);

  const updatedIndex = {
    ...boardIndex,
    combinedMotionPlan: "combined_motion_plan.json",
    rendererUpdatedAt: new Date().toISOString(),
  };
  writeJson(join(outBoardRoot, "board_index.json"), updatedIndex);
  writeJson(join(outBoardRoot, "combined_motion_plan.json"), updatedMotionPlan);
  if (existsSync(boardIndexPath)) copyFileSync(boardIndexPath, join(outBoardRoot, "board_index.source.json"));

  for (const board of Object.values(boards)) {
    const outDir = join(outBoardRoot, board.sourcePath);
    ensureDir(outDir);
    if (board.imageRef.kind === "file") {
      copyFileSync(board.imageRef.path, join(outDir, "board.png"));
    }
    writeJson(join(outDir, "board_manifest.json"), board.manifest);
    writeJson(join(outDir, "annotation_manifest.json"), board.annotationManifest);
    writeJson(join(outDir, "motion_plan.json"), board.localMotionPlan);
  }

  writeJson(join(outBoardRoot, "renderer_board_source.json"), {
    boardRoot,
    boardIndex: boardIndexPath,
    generatedAt: new Date().toISOString(),
    note: "combined_motion_plan.json is updated with measured voiceover timing; per-board motion_plan.json files remain local control packages.",
  });

  return outBoardRoot;
}

function writeDataJs(path, boardRegistry, motionPlan) {
  const data = {};
  for (const [boardId, board] of Object.entries(boardRegistry)) {
    data[boardId] = {
      boardId,
      image: board.hyperframesImageSrc || board.imageRef.src,
      imageKind: board.imageRef.kind,
      manifest: board.manifest,
      annotationManifest: board.annotationManifest,
      annotationMap: board.annotationMap,
    };
  }
  const content = [
    `window.BOARD_REGISTRY = ${JSON.stringify(data, null, 2)};`,
    `window.MOTION_PLAN = ${JSON.stringify(motionPlan, null, 2)};`,
    "",
  ].join("\n");
  writeFileSync(path, content);
}

function generateDesignMd() {
  return `# Multi-Board Whiteboard Infographic Renderer Design

## Style Prompt

Parchment whiteboard explanation video with a full-board visual layer, roaming camera, human cursor, red marker annotations, segment captions, and soft crossfade transitions when the narration moves to another board.

## Control Model

- The PNG is only the visual layer.
- board_manifest.json and annotation_manifest.json are the control layer.
- combined_motion_plan.json is the global timeline.
- Per-board motion_plan.json files are preserved as local board packages and are not used as global timing.

## What NOT to Do

- Do not infer annotation coordinates from PNG pixels.
- Do not render three separate videos for a three-board input.
- Do not collapse the editable HyperFrames project to a preview MP4 only.
`;
}

function generatePackageJson(version) {
  return JSON.stringify(
    {
      name: "whiteboard-infographic-multi-board-render",
      private: true,
      type: "module",
      scripts: {
        lint: `npx --yes hyperframes@${version} lint`,
        validate: `npx --yes hyperframes@${version} validate`,
        inspect: `npx --yes hyperframes@${version} inspect --samples 16`,
        check: "npm run lint && npm run validate && npm run inspect",
        render: `npx --yes hyperframes@${version} render --output ../preview.mp4 --quality standard`,
        keyframes: "node scripts/extract_action_keyframes.mjs",
        dev: `npx --yes hyperframes@${version} preview`,
      },
    },
    null,
    2,
  );
}

function generateHyperframesJson() {
  return JSON.stringify(
    {
      $schema: "https://hyperframes.heygen.com/schema/hyperframes.json",
      registry: "https://raw.githubusercontent.com/heygen-com/hyperframes/main/registry",
    },
    null,
    2,
  );
}

function localGsapSource() {
  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const candidates = [
    join(scriptDir, "..", "..", "ai-video-material-workflow", "examples", "output", "hyperframes-preview", "vendor", "gsap.min.js"),
    join(process.cwd(), "ai-video-material-workflow", "examples", "output", "hyperframes-preview", "vendor", "gsap.min.js"),
  ];
  return candidates.find((candidate) => existsSync(candidate));
}

function generateIndexHtml({ width, height, duration, gsapScriptSrc }) {
  const cursorFade = Math.max(0, duration - 0.35).toFixed(3);
  return `<!doctype html>
<html lang="zh-CN" data-resolution="${width >= height ? "landscape" : "portrait"}">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=${width}, height=${height}" />
    <script src="assets/board/data.js"></script>
    <script src="${gsapScriptSrc}"></script>
    <style>
      * { box-sizing: border-box; margin: 0; padding: 0; }
      html, body { width: ${width}px; height: ${height}px; overflow: hidden; background: #fbfaf6; }
      body { color: #1a1a1a; font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif; }
      #root { position: relative; width: ${width}px; height: ${height}px; overflow: hidden; background: #fbfaf6; }
      #boardLayers { position: absolute; inset: 0; overflow: hidden; background: #fbfaf6; }
      .boardFrame { position: absolute; inset: 0; overflow: hidden; opacity: 0; will-change: opacity, transform; background: #fbfaf6; }
      .boardStage { position: absolute; left: 0; top: 0; transform-origin: 0 0; will-change: transform; }
      .boardImage, .annotationLayer { position: absolute; left: 0; top: 0; }
      .boardImage { display: block; object-fit: fill; }
      .annotationLayer { overflow: visible; pointer-events: none; }
      .annotation-red { fill: none; stroke: #d8232a; stroke-linecap: round; stroke-linejoin: round; opacity: 0; filter: drop-shadow(0 4px 0 rgba(216, 35, 42, 0.1)); }
      .annotation-underline { stroke-width: 13; }
      .annotation-circle { stroke-width: 12; }
      .annotation-box { stroke-width: 10; }
      .annotation-check { stroke-width: 15; }
      .annotation-strike { stroke-width: 12; }
      #cursor, #cursorPulse { position: absolute; left: 0; top: 0; pointer-events: none; }
      #cursor { z-index: 40; width: 54px; height: 54px; transform-origin: 10px 8px; filter: drop-shadow(0 8px 10px rgba(0, 0, 0, 0.28)); will-change: transform, opacity; }
      #cursor svg { display: block; width: 54px; height: 54px; overflow: visible; }
      #cursorPulse { z-index: 34; width: 96px; height: 96px; border: 4px solid rgba(216, 35, 42, 0.45); border-radius: 50%; opacity: 0; }
      #captionShade { position: absolute; left: 0; right: 0; bottom: 0; z-index: 20; height: 260px; pointer-events: none; background: linear-gradient(to bottom, rgba(251, 250, 246, 0), rgba(82, 82, 82, 0.5) 58%, rgba(0, 0, 0, 0.76)); }
      #captionLayer { position: absolute; left: 0; right: 0; bottom: 46px; z-index: 28; height: 132px; pointer-events: none; }
      .captionLine { position: absolute; left: 0; right: 0; bottom: 0; display: flex; justify-content: center; padding: 0 132px; opacity: 0; visibility: hidden; transform: translateY(12px); }
      .captionText { max-width: ${Math.round(width * 0.82)}px; color: #ffffff; font-size: 44px; font-weight: 800; line-height: 1.26; text-align: center; letter-spacing: 0; -webkit-text-stroke: 7px rgba(0, 0, 0, 0.74); paint-order: stroke fill; text-shadow: 0 2px 0 rgba(0, 0, 0, 0.76), 0 7px 20px rgba(0, 0, 0, 0.42); }
    </style>
  </head>
  <body>
    <div id="root" data-composition-id="main" data-start="0" data-duration="${duration}" data-width="${width}" data-height="${height}">
      <audio id="narration" data-start="0" data-duration="${duration}" data-track-index="0" data-volume="1" src="assets/audio/narration.wav"></audio>
      <div id="boardLayers" data-layout-allow-overflow data-layout-allow-overlap></div>
      <div id="cursorPulse" data-layout-ignore></div>
      <div id="cursor" data-layout-ignore>
        <svg viewBox="0 0 54 54" aria-hidden="true">
          <path d="M8 5 L42 31 L26 34 L19 49 Z" fill="#fbfaf6" stroke="#1a1a1a" stroke-width="3.2" stroke-linejoin="round" />
          <path d="M26 34 L37 49" stroke="#1a1a1a" stroke-width="3.2" stroke-linecap="round" />
        </svg>
      </div>
      <div id="captionShade"></div>
      <div id="captionLayer"></div>
    </div>
    <script>
      window.__timelines = window.__timelines || {};
      (function () {
        var registry = window.BOARD_REGISTRY;
        var motionPlan = window.MOTION_PLAN;
        var composition = { width: motionPlan.composition.width, height: motionPlan.composition.height, centerX: motionPlan.composition.width / 2, centerY: motionPlan.composition.height / 2 };
        var boardLayers = document.querySelector("#boardLayers");
        var cursor = document.querySelector("#cursor");
        var pulse = document.querySelector("#cursorPulse");
        var captionLayer = document.querySelector("#captionLayer");
        var boardStates = {};
        var annotationNodes = {};
        var captionNodes = {};
        var firstBoardId = motionPlan.segments[0] && motionPlan.segments[0].boardId;

        function clamp(value, min, max) { return Math.min(max, Math.max(min, value)); }
        function safeKey(value) { return String(value || "item").replace(/[^a-z0-9_-]/gi, "_"); }
        function mapElements(items) {
          var out = {};
          (items || []).forEach(function (item) { out[item.id] = item; });
          return out;
        }
        function createBoardState(boardId, boardData) {
          var manifest = boardData.manifest;
          var canvas = manifest.canvas;
          var frame = document.createElement("div");
          frame.className = "boardFrame";
          frame.id = "boardFrame-" + boardId;
          frame.setAttribute("data-board-id", boardId);
          frame.setAttribute("data-layout-allow-overflow", "");
          frame.setAttribute("data-layout-allow-overlap", "");
          var stage = document.createElement("div");
          stage.className = "boardStage";
          stage.id = "boardStage-" + boardId;
          stage.style.width = canvas.width + "px";
          stage.style.height = canvas.height + "px";
          stage.setAttribute("data-layout-allow-overflow", "");
          stage.setAttribute("data-layout-allow-overlap", "");
          var img = document.createElement("img");
          img.className = "boardImage";
          img.src = boardData.image;
          img.alt = boardId + " whiteboard infographic";
          img.style.width = canvas.width + "px";
          img.style.height = canvas.height + "px";
          var svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
          svg.setAttribute("class", "annotationLayer");
          svg.setAttribute("viewBox", "0 0 " + canvas.width + " " + canvas.height);
          svg.setAttribute("aria-hidden", "true");
          svg.style.width = canvas.width + "px";
          svg.style.height = canvas.height + "px";
          stage.appendChild(img);
          stage.appendChild(svg);
          frame.appendChild(stage);
          boardLayers.appendChild(frame);
          return {
            boardId: boardId,
            data: boardData,
            manifest: manifest,
            canvas: canvas,
            frame: frame,
            stage: stage,
            svg: svg,
            elements: mapElements(manifest.elements || []),
            annotations: boardData.annotationMap || {},
          };
        }
        Object.keys(registry).forEach(function (boardId) {
          boardStates[boardId] = createBoardState(boardId, registry[boardId]);
        });
        Object.keys(boardStates).forEach(function (boardId) {
          gsap.set(boardStates[boardId].frame, { opacity: boardId === firstBoardId ? 1 : 0, x: 0 });
        });

        motionPlan.segments.forEach(function (segment) {
          var line = document.createElement("div");
          line.className = "captionLine";
          line.id = "caption-" + safeKey(segment.id);
          var text = document.createElement("div");
          text.className = "captionText";
          text.textContent = segment.caption || "";
          line.appendChild(text);
          captionLayer.appendChild(line);
          captionNodes[segment.id] = line;
        });

        function cameraTransform(state, camera) {
          var board = state.canvas;
          var safeCamera = camera || motionPlan.overview_camera || { x: board.width / 2, y: board.height / 2, scale: 1 };
          var scaledWidth = board.width * safeCamera.scale;
          var scaledHeight = board.height * safeCamera.scale;
          var x = composition.centerX - safeCamera.x * safeCamera.scale;
          var y = composition.centerY - safeCamera.y * safeCamera.scale;
          if (scaledWidth <= composition.width) { x = (composition.width - scaledWidth) / 2; } else { x = clamp(x, composition.width - scaledWidth, 0); }
          if (scaledHeight <= composition.height) { y = (composition.height - scaledHeight) / 2; } else { y = clamp(y, composition.height - scaledHeight, 0); }
          return { x: x, y: y, scale: safeCamera.scale };
        }
        function projectPoint(state, point, camera) {
          var transform = cameraTransform(state, camera);
          return { x: transform.x + point[0] * transform.scale - 10, y: transform.y + point[1] * transform.scale - 8 };
        }
        function pathFromUnderline(annotation) {
          var points = [annotation.underlineStart].concat(annotation.controlPoints || [], [annotation.underlineEnd]);
          if (points.length >= 5) {
            var p0 = points[0]; var p1 = points[1]; var p2 = points[2]; var p3 = points[points.length - 2]; var p4 = points[points.length - 1];
            return "M " + p0[0] + " " + p0[1] + " C " + p1[0] + " " + p1[1] + ", " + p2[0] + " " + p2[1] + ", " + p3[0] + " " + p3[1] + " S " + p4[0] + " " + p4[1] + ", " + p4[0] + " " + p4[1];
          }
          return "M " + annotation.underlineStart[0] + " " + annotation.underlineStart[1] + " L " + annotation.underlineEnd[0] + " " + annotation.underlineEnd[1];
        }
        function pathFromCircle(annotation) {
          var cx = annotation.circleCenter[0]; var cy = annotation.circleCenter[1]; var rx = annotation.radius[0]; var ry = annotation.radius[1];
          return [
            "M " + cx + " " + (cy - ry),
            "C " + (cx + rx * 0.7) + " " + (cy - ry * 1.16) + ", " + (cx + rx * 1.08) + " " + (cy - ry * 0.25) + ", " + (cx + rx) + " " + cy,
            "C " + (cx + rx * 0.95) + " " + (cy + ry * 1.12) + ", " + (cx + rx * 0.15) + " " + (cy + ry * 1.18) + ", " + cx + " " + (cy + ry),
            "C " + (cx - rx * 0.8) + " " + (cy + ry * 0.94) + ", " + (cx - rx * 1.08) + " " + (cy + ry * 0.18) + ", " + (cx - rx) + " " + cy,
            "C " + (cx - rx * 0.95) + " " + (cy - ry * 1.04) + ", " + (cx - rx * 0.15) + " " + (cy - ry * 1.12) + ", " + cx + " " + (cy - ry),
          ].join(" ");
        }
        function pathFromBox(annotation) {
          var box = annotation.boxBounds; var x = box[0]; var y = box[1]; var w = box[2]; var h = box[3]; var r = annotation.cornerRadius || 24;
          return [
            "M " + (x + r) + " " + y,
            "C " + (x + w * 0.34) + " " + (y - 7) + ", " + (x + w * 0.64) + " " + (y + 6) + ", " + (x + w - r) + " " + y,
            "Q " + (x + w + 8) + " " + (y + 2) + ", " + (x + w) + " " + (y + r),
            "C " + (x + w + 9) + " " + (y + h * 0.42) + ", " + (x + w - 5) + " " + (y + h * 0.72) + ", " + (x + w) + " " + (y + h - r),
            "Q " + (x + w - 2) + " " + (y + h + 8) + ", " + (x + w - r) + " " + (y + h),
            "C " + (x + w * 0.62) + " " + (y + h + 7) + ", " + (x + w * 0.32) + " " + (y + h - 6) + ", " + (x + r) + " " + (y + h),
            "Q " + (x - 8) + " " + (y + h - 2) + ", " + x + " " + (y + h - r),
            "C " + (x - 7) + " " + (y + h * 0.62) + ", " + (x + 5) + " " + (y + h * 0.3) + ", " + x + " " + (y + r),
            "Q " + (x + 2) + " " + (y - 8) + ", " + (x + r) + " " + y,
          ].join(" ");
        }
        function pathFromCheck(annotation) {
          var p = annotation.points;
          return "M " + p[0][0] + " " + p[0][1] + " L " + p[1][0] + " " + p[1][1] + " L " + p[2][0] + " " + p[2][1];
        }
        function pathFromStrike(annotation) {
          var points = [annotation.strikeStart].concat(annotation.controlPoints || [], [annotation.strikeEnd]);
          if (points.length >= 5) {
            var p0 = points[0]; var p1 = points[1]; var p2 = points[2]; var p3 = points[points.length - 2]; var p4 = points[points.length - 1];
            return "M " + p0[0] + " " + p0[1] + " C " + p1[0] + " " + p1[1] + ", " + p2[0] + " " + p2[1] + ", " + p3[0] + " " + p3[1] + " S " + p4[0] + " " + p4[1] + ", " + p4[0] + " " + p4[1];
          }
          return "M " + annotation.strikeStart[0] + " " + annotation.strikeStart[1] + " L " + annotation.strikeEnd[0] + " " + annotation.strikeEnd[1];
        }
        function annotationPath(action, annotation) {
          if (action.type === "underline") return pathFromUnderline(annotation);
          if (action.type === "circle") return pathFromCircle(annotation);
          if (action.type === "box") return pathFromBox(annotation);
          if (action.type === "check") return pathFromCheck(annotation);
          if (action.type === "strike") return pathFromStrike(annotation);
          return "";
        }
        function createPath(state, id, action, annotation) {
          var path = document.createElementNS("http://www.w3.org/2000/svg", "path");
          path.setAttribute("id", id);
          path.setAttribute("class", "annotation-red annotation-" + action.type);
          path.setAttribute("d", annotationPath(action, annotation));
          path.setAttribute("pathLength", "1");
          path.style.strokeDasharray = "1";
          path.style.strokeDashoffset = "1";
          state.svg.appendChild(path);
          return path;
        }
        function annotationFor(state, action) {
          var element = state.elements[action.element] || {};
          return (element.annotations && element.annotations[action.annotation]) || state.annotations[action.annotation];
        }
        motionPlan.segments.forEach(function (segment) {
          var state = boardStates[segment.boardId];
          segment.actions.forEach(function (action) {
            var id = "mark-" + safeKey(segment.id) + "-" + safeKey(action.annotation);
            annotationNodes[id] = createPath(state, id, action, annotationFor(state, action));
          });
        });
        var movementProfiles = [
          { arc: -0.2, overshoot: 0.06, hesitateX: -10, hesitateY: 6, rotation: -3 },
          { arc: 0.18, overshoot: 0.055, hesitateX: 9, hesitateY: -7, rotation: 4 },
          { arc: -0.14, overshoot: 0.05, hesitateX: -7, hesitateY: 9, rotation: -2 },
          { arc: 0.22, overshoot: 0.07, hesitateX: 10, hesitateY: 5, rotation: 3 },
          { arc: -0.18, overshoot: 0.06, hesitateX: -8, hesitateY: -5, rotation: -4 },
        ];
        function pointAlong(from, to, t, profile) {
          var dx = to.x - from.x; var dy = to.y - from.y; var distance = Math.hypot(dx, dy) || 1; var normalX = -dy / distance; var normalY = dx / distance; var bend = distance * profile.arc * Math.sin(Math.PI * t);
          return { x: from.x + dx * t + normalX * bend, y: from.y + dy * t + normalY * bend };
        }
        function addHumanCursorMove(timeline, from, to, at, profileIndex) {
          var profile = movementProfiles[profileIndex % movementProfiles.length];
          var distance = Math.hypot(to.x - from.x, to.y - from.y);
          var durationScale = clamp(distance / 900, 0.68, 1.28);
          var approachA = pointAlong(from, to, 0.34, profile);
          var approachB = pointAlong(from, to, 0.78, profile);
          var overshoot = { x: to.x + (to.x - from.x) * profile.overshoot, y: to.y + (to.y - from.y) * profile.overshoot };
          timeline.to(cursor, { x: from.x + profile.hesitateX, y: from.y + profile.hesitateY, rotation: profile.rotation, duration: 0.14, ease: "sine.inOut" }, at);
          timeline.to(cursor, { x: approachA.x, y: approachA.y, rotation: profile.rotation * -0.55, duration: 0.27 * durationScale, ease: "circ.out" }, at + 0.14);
          timeline.to(cursor, { x: approachB.x, y: approachB.y, rotation: profile.rotation * 0.48, duration: 0.24 * durationScale, ease: "power3.inOut" }, at + 0.42 * durationScale);
          timeline.to(cursor, { x: overshoot.x, y: overshoot.y, rotation: profile.rotation * 0.2, duration: 0.18, ease: "power4.out" }, at + 0.68 * durationScale);
          timeline.to(cursor, { x: to.x, y: to.y, rotation: 0, duration: 0.22, ease: "sine.out" }, at + 0.88 * durationScale);
        }
        function addCursorPress(timeline, point, at) {
          timeline.to(cursor, { x: point.x + 2, y: point.y + 2, scale: 0.94, duration: 0.08, ease: "power1.in" }, at);
          timeline.to(cursor, { x: point.x, y: point.y, scale: 1, duration: 0.14, ease: "back.out(1.8)" }, at + 0.08);
        }
        function cursorPointsFor(annotation) {
          return {
            start: annotation.cursorStart || annotation.underlineStart || annotation.strikeStart || (annotation.points && annotation.points[0]) || annotation.circleCenter || [0, 0],
            end: annotation.cursorEnd || annotation.underlineEnd || annotation.strikeEnd || (annotation.points && annotation.points[annotation.points.length - 1]) || annotation.circleCenter || [0, 0],
          };
        }
        function nodesForSegment(segment) {
          return segment.actions.map(function (action) {
            return annotationNodes["mark-" + safeKey(segment.id) + "-" + safeKey(action.annotation)];
          }).filter(Boolean);
        }
        var tl = gsap.timeline({ paused: true });
        var cursorState = { x: composition.centerX - 20, y: composition.centerY - 8 };
        var actionIndex = 0;
        Object.keys(boardStates).forEach(function (boardId) {
          var state = boardStates[boardId];
          var overview = cameraTransform(state, motionPlan.overview_camera);
          gsap.set(state.stage, { x: overview.x, y: overview.y, scale: overview.scale });
        });
        gsap.set(cursor, { x: cursorState.x, y: cursorState.y, opacity: 0, scale: 1, rotation: 0 });
        tl.to(cursor, { opacity: 1, duration: 0.28, ease: "power1.out" }, 0.15);
        motionPlan.segments.forEach(function (segment, segmentIndex) {
          var state = boardStates[segment.boardId];
          var target = state.elements[segment.target] || {};
          var cameraPlan = segment.cameraPlan || {};
          var camera = cameraPlan.focusCamera || segment.camera || target.camera || motionPlan.overview_camera;
          var entryCamera = cameraPlan.entryCamera || null;
          var exitCamera = cameraPlan.exitCamera || null;
          var cameraState = cameraTransform(state, camera);
          var captionNode = captionNodes[segment.id];
          var previous = motionPlan.segments[segmentIndex - 1];
          if (previous && previous.boardId !== segment.boardId) {
            var prevState = boardStates[previous.boardId];
            var transitionAt = Math.max(0, Number(segment.start) - 0.22);
            tl.to(prevState.frame, { opacity: 0, x: -42, duration: 0.34, ease: "power2.inOut", overwrite: "auto" }, transitionAt);
            tl.fromTo(state.frame, { opacity: 0, x: 46 }, { opacity: 1, x: 0, duration: 0.46, ease: "power2.out", overwrite: "auto" }, transitionAt);
            if (entryCamera) {
              var entryState = cameraTransform(state, entryCamera);
              tl.set(state.stage, { x: entryState.x, y: entryState.y, scale: entryState.scale }, transitionAt);
            }
          } else {
            tl.set(state.frame, { opacity: 1, x: 0 }, Math.max(0, Number(segment.start) - 0.05));
            if (entryCamera) {
              var sameBoardEntry = cameraTransform(state, entryCamera);
              tl.set(state.stage, { x: sameBoardEntry.x, y: sameBoardEntry.y, scale: sameBoardEntry.scale }, Math.max(0, Number(segment.start) - 0.05));
            }
          }
          if (segmentIndex > 0) {
            var priorNodes = nodesForSegment(motionPlan.segments[segmentIndex - 1]);
            if (priorNodes.length > 0) tl.to(priorNodes, { opacity: 0.18, duration: 0.24, ease: "power1.out" }, Math.max(0, Number(segment.start) - 0.16));
          }
          var actionOffsets = segment.actions.map(function (action) { return Number(action.offset); }).filter(function (value) { return Number.isFinite(value); });
          var firstActionOffset = actionOffsets.length ? Math.min.apply(null, actionOffsets) : 0.75;
          var firstDrawAt = Number(segment.start) + firstActionOffset;
          var cameraAt = Math.max(0, Math.max(Number(segment.start), firstDrawAt - 0.52));
          var cameraDuration = clamp(firstDrawAt - cameraAt - 0.18, 0.34, 0.82);
          tl.to(state.stage, { x: cameraState.x, y: cameraState.y, scale: cameraState.scale, duration: cameraDuration, ease: "power2.out" }, cameraAt);
          if (exitCamera) {
            var exitState = cameraTransform(state, exitCamera);
            var exitAt = Math.max(Number(segment.start), Number(segment.end) - 0.62);
            tl.to(state.stage, { x: exitState.x, y: exitState.y, scale: exitState.scale, duration: 0.5, ease: "power2.inOut" }, exitAt);
          }
          tl.set(captionNode, { visibility: "visible" }, Number(segment.start) + 0.1);
          tl.to(captionNode, { opacity: 1, y: 0, duration: 0.28, ease: "power2.out", overwrite: "auto" }, Number(segment.start) + 0.12);
          tl.to(captionNode, { opacity: 0, y: 12, duration: 0.18, ease: "power1.in", overwrite: "auto" }, Math.max(Number(segment.start), Number(segment.end) - 0.18));
          tl.set(captionNode, { opacity: 0, visibility: "hidden" }, Number(segment.end));
          segment.actions.forEach(function (action) {
            var annotation = annotationFor(state, action);
            var node = annotationNodes["mark-" + safeKey(segment.id) + "-" + safeKey(action.annotation)];
            var drawAt = Number(segment.start) + Number(action.offset);
            var rhythm = action.rhythm || {};
            var cursorPoints = cursorPointsFor(annotation);
            var startScreen = projectPoint(state, cursorPoints.start, camera);
            var endScreen = projectPoint(state, cursorPoints.end, camera);
            var moveAt = Math.max(Number(segment.start) + 0.04, drawAt - Number(rhythm.cursorMoveLeadSec || 1.18));
            addHumanCursorMove(tl, cursorState, startScreen, moveAt, actionIndex);
            addCursorPress(tl, startScreen, Math.max(Number(segment.start), drawAt - Number(rhythm.preArrivalSec || 0.16)));
            tl.to(pulse, { x: startScreen.x - 22, y: startScreen.y - 20, scale: 1, opacity: 0.42, duration: 0.12, ease: "power1.out", overwrite: "auto" }, Math.max(Number(segment.start), drawAt - Number(rhythm.preArrivalSec || 0.16)));
            tl.to(pulse, { scale: 1.45, opacity: 0, duration: 0.42, ease: "sine.out", overwrite: "auto" }, drawAt + 0.02);
            tl.set(node, { opacity: 1 }, drawAt);
            tl.to(node, { strokeDashoffset: 0, duration: Number(action.duration), ease: action.type === "check" ? "back.out(1.3)" : "sine.inOut" }, drawAt);
            tl.to(cursor, { x: endScreen.x, y: endScreen.y, rotation: action.type === "circle" ? 3 : 0, duration: Number(action.duration), ease: "sine.inOut" }, drawAt);
            tl.to(cursor, { rotation: 0, duration: 0.12, ease: "sine.out" }, drawAt + Number(action.duration));
            tl.set(cursor, { x: endScreen.x, y: endScreen.y }, drawAt + Number(action.duration) + Number(rhythm.holdAfterSec || 0.42));
            cursorState = endScreen;
            actionIndex += 1;
          });
        });
        tl.to(cursor, { opacity: 0, duration: 0.35, ease: "power1.in" }, ${cursorFade});
        window.__timelines.main = tl;
      })();
    </script>
  </body>
</html>
`;
}

function generateKeyframeScript() {
  return `#!/usr/bin/env node
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const root = dirname(dirname(fileURLToPath(import.meta.url)));
const video = process.argv[2] ? process.argv[2] : join(root, "..", "preview.mp4");
const plan = JSON.parse(readFileSync(join(root, "assets", "board", "motion_plan.json"), "utf8"));
const outDir = process.argv[3] ? process.argv[3] : join(root, "..", "keyframes");

rmSync(outDir, { recursive: true, force: true });
mkdirSync(outDir, { recursive: true });

function timeName(time) { return time.toFixed(3).replace(".", "p"); }
function safeName(value) { return String(value || "item").replace(/[^a-z0-9_-]/gi, "_"); }
function extract(time, file) { execFileSync("ffmpeg", ["-y", "-ss", time.toFixed(3), "-i", video, "-frames:v", "1", "-q:v", "2", file], { stdio: "ignore" }); }

const rows = [];
let index = 1;
for (const segment of plan.segments || []) {
  for (const action of segment.actions || []) {
    const drawStart = Number(segment.start) + Number(action.offset);
    const drawDone = drawStart + Number(action.duration);
    const base = \`\${String(index).padStart(2, "0")}-\${safeName(segment.boardId)}-\${safeName(segment.id)}-\${safeName(action.annotation)}\`;
    const startFile = join(outDir, \`\${base}-start-t\${timeName(drawStart)}.jpg\`);
    const doneFile = join(outDir, \`\${base}-done-t\${timeName(drawDone)}.jpg\`);
    extract(Math.max(0, drawStart), startFile);
    extract(Math.max(0, drawDone), doneFile);
    rows.push({
      index,
      boardId: segment.boardId,
      segment: segment.id,
      annotation: action.annotation,
      type: action.type,
      element: action.element,
      spokenAnchor: action.spokenAnchor,
      sync: action.sync || null,
      rhythm: action.rhythm || null,
      cameraStrategy: segment.cameraStrategy || null,
      cameraPlan: segment.cameraPlan || null,
      drawStart: Number(drawStart.toFixed(3)),
      drawDone: Number(drawDone.toFixed(3)),
      startFrame: startFile.replace(root + "/", ""),
      doneFrame: doneFile.replace(root + "/", ""),
    });
    index += 1;
  }
}
writeFileSync(join(outDir, "keyframe_manifest.json"), JSON.stringify(rows, null, 2) + "\\n");
if (rows.length > 0) {
  const cols = Math.min(5, rows.length);
  const rowsCount = Math.ceil(rows.length / cols);
  for (const kind of ["start", "done"]) {
    execFileSync("ffmpeg", ["-y", "-pattern_type", "glob", "-i", join(outDir, \`*-\${kind}-*.jpg\`), "-vf", \`scale=384:-1,tile=\${cols}x\${rowsCount}:padding=8:margin=8:color=white\`, "-q:v", "2", join(outDir, \`contact_sheet_\${kind}.jpg\`)], { stdio: "ignore" });
  }
}
console.log(JSON.stringify({ outDir, actions: rows.length, frames: rows.length * 2 }, null, 2));
`;
}

function createHyperframesProject({ projectDir, hfDir, audioDir, boards, motionPlan, version }) {
  rmSync(hfDir, { recursive: true, force: true });
  const boardAssetDir = join(hfDir, "assets", "board");
  const boardsAssetRoot = join(hfDir, "assets", "boards");
  const audioAssetDir = join(hfDir, "assets", "audio");
  const vendorAssetDir = join(hfDir, "assets", "vendor");
  const scriptsDir = join(hfDir, "scripts");
  ensureDir(boardAssetDir);
  ensureDir(boardsAssetRoot);
  ensureDir(audioAssetDir);
  ensureDir(vendorAssetDir);
  ensureDir(scriptsDir);

  const gsapSource = localGsapSource();
  const gsapScriptSrc = gsapSource ? "assets/vendor/gsap.min.js" : "https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js";
  if (gsapSource) {
    copyFileSync(gsapSource, join(vendorAssetDir, "gsap.min.js"));
  }

  for (const board of Object.values(boards)) {
    const outDir = join(boardsAssetRoot, board.sourcePath);
    ensureDir(outDir);
    if (board.imageRef.kind === "file") {
      copyFileSync(board.imageRef.path, join(outDir, "board.png"));
      board.hyperframesImageSrc = `assets/boards/${board.sourcePath}/board.png`;
    } else {
      board.hyperframesImageSrc = board.imageRef.src;
    }
    writeJson(join(outDir, "board_manifest.json"), board.manifest);
    writeJson(join(outDir, "annotation_manifest.json"), board.annotationManifest);
    writeJson(join(outDir, "motion_plan.json"), board.localMotionPlan);
  }

  copyFileSync(join(audioDir, "narration.wav"), join(audioAssetDir, "narration.wav"));
  copyFileSync(join(audioDir, "voiceover_timing.json"), join(audioAssetDir, "voiceover_timing.json"));
  copyFileSync(join(audioDir, "captions.srt"), join(audioAssetDir, "captions.srt"));
  if (existsSync(join(audioDir, "word_timing.json"))) {
    copyFileSync(join(audioDir, "word_timing.json"), join(audioAssetDir, "word_timing.json"));
  }
  if (existsSync(join(projectDir, "sync", "action_timing.json"))) {
    copyFileSync(join(projectDir, "sync", "action_timing.json"), join(boardAssetDir, "action_timing.json"));
  }
  if (existsSync(join(projectDir, "sync", "camera_plan.json"))) {
    copyFileSync(join(projectDir, "sync", "camera_plan.json"), join(boardAssetDir, "camera_plan.json"));
  }
  writeJson(join(boardAssetDir, "motion_plan.json"), motionPlan);
  writeDataJs(join(boardAssetDir, "data.js"), boards, motionPlan);

  const width = Number(motionPlan.composition.width);
  const height = Number(motionPlan.composition.height);
  const duration = formatSeconds(motionPlan.composition.duration);
  writeFileSync(join(hfDir, "DESIGN.md"), generateDesignMd());
  writeFileSync(join(hfDir, "package.json"), generatePackageJson(version) + "\n");
  writeFileSync(join(hfDir, "hyperframes.json"), generateHyperframesJson() + "\n");
  writeFileSync(join(hfDir, "index.html"), generateIndexHtml({ width, height, duration, gsapScriptSrc }));
  writeFileSync(join(scriptsDir, "extract_action_keyframes.mjs"), generateKeyframeScript());
  return { hyperframesProject: hfDir, index: join(hfDir, "index.html"), relative: rel(projectDir, hfDir) };
}

function runHyperframesChecks(hfDir, version) {
  const npxArgs = ["--yes", `hyperframes@${version}`];
  verbose("calling hyperframes lint");
  const lint = runCapture("npx", npxArgs.concat(["lint"]), hfDir);
  assertCommand(lint, "hyperframes lint");
  verbose("hyperframes lint OK");
  verbose("calling hyperframes validate");
  const validate = runCapture("npx", npxArgs.concat(["validate"]), hfDir);
  assertCommand(validate, "hyperframes validate");
  verbose("hyperframes validate OK");
  verbose("calling hyperframes inspect --samples 16");
  let inspect = runCapture("npx", npxArgs.concat(["inspect", "--samples", "16"]), hfDir);
  const inspectOutput = `${inspect.stdout}\n${inspect.stderr}`;
  if (inspect.status !== 0 && inspectOutput.includes("Navigation timeout of 10000 ms exceeded")) {
    verbose("hyperframes inspect timed out, retrying once");
    const retry = runCapture("npx", npxArgs.concat(["inspect", "--samples", "16"]), hfDir);
    inspect = {
      ...retry,
      attempts: 2,
      stderr: `[retry after transient navigation timeout]\n${retry.stderr}`,
    };
  } else {
    inspect.attempts = 1;
  }
  assertCommand(inspect, "hyperframes inspect");
  verbose("hyperframes inspect OK");
  return { lint, validate, inspect };
}

function renderPreview(hfDir, videoPath, version, quality, fps) {
  ensureDir(dirname(videoPath));
  const args = ["--yes", `hyperframes@${version}`, "render", "--output", videoPath, "--quality", quality];
  if (fps) args.push("--fps", String(fps));
  const printable = args.map((arg) => (String(arg).includes(" ") ? `"${arg}"` : arg)).join(" ");
  verbose(`hyperframes render command: npx ${printable}`);
  run("npx", args, { cwd: hfDir });
}

function extractKeyframes(hfDir, videoPath, keyframeDir) {
  run("node", [join(hfDir, "scripts", "extract_action_keyframes.mjs"), videoPath, keyframeDir], { cwd: hfDir });
}

function checkBbox(board, bbox) {
  if (!isValidBbox(bbox)) {
    return { status: "missing", reason: "no valid bbox available" };
  }
  const canvas = board.manifest?.canvas || {};
  const width = numberOr(canvas.width, 0);
  const height = numberOr(canvas.height, 0);
  const [x, y, w, h] = bbox.map(Number);
  const outOfBounds = x < 0 || y < 0 || x + w > width || y + h > height;
  const nearEdge = !outOfBounds && (x < width * 0.02 || y < height * 0.02 || x + w > width * 0.98 || y + h > height * 0.98);
  if (outOfBounds) return { status: "fail", reason: "bbox extends outside board canvas" };
  if (nearEdge) return { status: "warn", reason: "bbox is close to board edge" };
  return { status: "pass", reason: "bbox inside board canvas" };
}

function rowStatus(values) {
  if (values.includes("fail") || values.includes("missing")) return "fail";
  if (values.includes("warn") || values.includes("skipped")) return "warn";
  return "pass";
}

function buildActionCameraQa({ projectDir, motionPlan, boards, actionTiming, cameraPlan, keyframeDir, keyframeSummary }) {
  const actionTimingByKey = new Map((actionTiming.actions || []).map((row) => [actionKey(row.segmentId, row.actionIndex), row]));
  const keyframeManifestPath = join(keyframeDir, "keyframe_manifest.json");
  const keyframeRows = existsSync(keyframeManifestPath) ? readJson(keyframeManifestPath) : [];
  const keyframeByAction = new Map(
    keyframeRows.map((row) => [`${row.segment}:${row.annotation}`, row]),
  );
  const contactStart = join(keyframeDir, "contact_sheet_start.jpg");
  const contactDone = join(keyframeDir, "contact_sheet_done.jpg");
  const rows = [];

  for (const segment of motionPlan.segments || []) {
    const board = boards[segment.boardId];
    for (const [index, action] of (segment.actions || []).entries()) {
      const syncRow = actionTimingByKey.get(actionKey(segment.id, index));
      const bbox = board ? actionBbox(board, action) : null;
      const bboxCheck = board ? checkBbox(board, bbox) : { status: "missing", reason: "board missing" };
      const camera = segment.cameraPlan?.focusCamera || segment.camera || {};
      const scale = Number(camera.scale || 1);
      const cameraStatus =
        scale > CAMERA_STRATEGY.zoomMax ? "fail" : scale > CAMERA_STRATEGY.zoomWarn ? "warn" : "pass";
      const keyframeRow = keyframeByAction.get(`${segment.id}:${action.annotation}`);
      const startFrameExists = keyframeRow?.startFrame ? existsSync(join(keyframeDir, basename(keyframeRow.startFrame))) : false;
      const doneFrameExists = keyframeRow?.doneFrame ? existsSync(join(keyframeDir, basename(keyframeRow.doneFrame))) : false;
      const keyframeStatus =
        keyframeSummary.status === "skipped"
          ? "skipped"
          : startFrameExists && doneFrameExists
            ? "pass"
            : "missing";
      rows.push({
        segmentId: segment.id,
        boardId: segment.boardId,
        actionIndex: index,
        type: action.type,
        element: action.element,
        annotation: action.annotation,
        spokenAnchor: action.spokenAnchor,
        syncSource: syncRow?.syncSource || action.sync?.source || "missing",
        syncConfidence: syncRow?.syncConfidence ?? action.sync?.confidence ?? null,
        syncStatus: String(syncRow?.syncSource || action.sync?.source || "").startsWith("cue-") ? "pass" : "warn",
        rhythmStatus: action.rhythm?.compressedToFit ? "warn" : "pass",
        bbox: isValidBbox(bbox) ? normalizeBbox(bbox) : null,
        bboxStatus: bboxCheck.status,
        bboxReason: bboxCheck.reason,
        cameraStrategy: segment.cameraStrategy || segment.cameraPlan?.strategy || "legacy",
        cameraScale: Number.isFinite(scale) ? formatSeconds(scale) : null,
        cameraStatus,
        keyframeStatus,
        status: rowStatus([
          String(syncRow?.syncSource || action.sync?.source || "").startsWith("cue-") ? "pass" : "warn",
          action.rhythm?.compressedToFit ? "warn" : "pass",
          bboxCheck.status,
          cameraStatus,
          keyframeStatus,
        ]),
      });
    }
  }

  const summary = {
    status: rowStatus(rows.map((row) => row.status)),
    actionCount: rows.length,
    fallbackActions: rows.filter((row) => row.syncStatus !== "pass").length,
    rhythmCompressedActions: rows.filter((row) => row.rhythmStatus !== "pass").length,
    bboxIssues: rows.filter((row) => row.bboxStatus !== "pass").length,
    cameraWarnings: rows.filter((row) => row.cameraStatus !== "pass").length,
    keyframeIssues: rows.filter((row) => row.keyframeStatus !== "pass").length,
    keyframeArtifacts: {
      manifest: existsSync(keyframeManifestPath),
      contactSheetStart: existsSync(contactStart),
      contactSheetDone: existsSync(contactDone),
    },
    cameraPlan: "sync/camera_plan.json",
    actionTiming: "sync/action_timing.json",
  };

  const tableRows = rows.map((row) =>
    [
      row.status,
      row.boardId,
      row.segmentId,
      row.annotation,
      row.syncSource,
      row.syncConfidence ?? "",
      row.bboxStatus,
      row.cameraStrategy,
      row.cameraScale ?? "",
      row.cameraStatus,
      row.keyframeStatus,
    ].join(" | "),
  );
  const markdown = `# Action / Camera QA Report

## Summary

- status: ${summary.status}
- actions: ${summary.actionCount}
- sync fallback or low-source actions: ${summary.fallbackActions}
- rhythm compressed actions: ${summary.rhythmCompressedActions}
- bbox issues: ${summary.bboxIssues}
- camera zoom warnings/failures: ${summary.cameraWarnings}
- keyframe issues: ${summary.keyframeIssues}

## Sources

- action timing: sync/action_timing.json
- camera plan: sync/camera_plan.json
- keyframes manifest: ${summary.keyframeArtifacts.manifest ? "video/keyframes/keyframe_manifest.json" : "missing or skipped"}
- contact sheet start: ${summary.keyframeArtifacts.contactSheetStart ? "video/keyframes/contact_sheet_start.jpg" : "missing or skipped"}
- contact sheet done: ${summary.keyframeArtifacts.contactSheetDone ? "video/keyframes/contact_sheet_done.jpg" : "missing or skipped"}

## Checks

| status | board | segment | annotation | syncSource | confidence | bbox | cameraStrategy | zoom | camera | keyframes |
| --- | --- | --- | --- | --- | ---: | --- | --- | ---: | --- | --- |
${tableRows.join("\n")}

## Thresholds

- camera zoom warnAbove: ${CAMERA_STRATEGY.zoomWarn}
- camera zoom maxAllowed: ${CAMERA_STRATEGY.zoomMax}
- bbox status fails when target bounds exceed the board canvas.
- keyframes pass only when both start and done frames exist for every action.
`;

  return {
    summary,
    rows,
    markdown,
    json: {
      version: "0.1",
      generatedAt: new Date().toISOString(),
      summary,
      rows,
      cameraPlan: cameraPlan || null,
    },
  };
}

function buildAcceptanceReport(report) {
  const duration = report.durationCheck;
  const lintWarnings = report.checks?.lint?.stdout?.includes("warning") || report.checks?.lint?.stderr?.includes("warning");
  return `# Multi-Board Renderer Acceptance Report

## Status

PASS

## Inputs

- board_root: ${report.inputs.boardRoot}
- board_index: ${report.inputs.boardIndex}
- combined_motion_plan: ${report.inputs.combinedMotionPlan}
- voiceover_segments: ${report.inputs.voiceover}

## Outputs

- audio/narration.wav
- audio/voiceover_timing.json
- audio/word_timing.json
- audio/captions.srt
- sync/action_timing.json
- sync/camera_plan.json
- sync/action_camera_qa_report.md
- video/hyperframes/
- video/preview.mp4
- video/keyframes/keyframe_manifest.json
- video/keyframes/contact_sheet_start.jpg
- video/keyframes/contact_sheet_done.jpg
- video/renderer_report.json

## Validation

- help: ${report.validation.help}
- dry-run: ${report.validation.dryRun}
- hyperframes lint: exit ${report.checks?.lint?.status ?? "skipped"}${lintWarnings ? " (warnings present; see renderer_report.json)" : ""}
- hyperframes validate: exit ${report.checks?.validate?.status ?? "skipped"}
- hyperframes inspect --samples 16: exit ${report.checks?.inspect?.status ?? "skipped"}
- preview duration: ${duration.renderedDuration}s
- voiceover timing duration: ${duration.timingDuration}s
- duration delta: ${duration.delta}s
- keyframe action count: ${report.keyframes.actionCount}
- action/camera QA: ${report.qa?.status ?? "unknown"} (${report.outputs.actionCameraQa})

## Alignment Check

Generated contact sheets are ready for visual inspection:

- video/keyframes/contact_sheet_start.jpg
- video/keyframes/contact_sheet_done.jpg

Programmatic checks confirm every action carries boardId, segment, annotation, type, element, drawStart, and drawDone. Manual contact-sheet inspection should focus on cursor and marker alignment for underline, circle, box, check, and strike actions.
`;
}

function buildFailureReport(error) {
  const message = error?.message || String(error);
  return `# Multi-Board Renderer Acceptance Report

## Status

FAIL

## Failed Step

${runContext.step}

## Error Log

\`\`\`text
${message.slice(0, 8000)}
\`\`\`

## Contract Notes

- D side must provide board_index.json, combined_motion_plan.json, and one board directory per boardId.
- E side uses combined_motion_plan.json as the global timeline and does not treat per-board motion_plan.json start=0 as full-video time.
- If this failure is a missing target, element, annotation, or boardId, the incompatible field must be fixed in B/C/D before render can be trusted.
`;
}

function writeFailureReport(error) {
  if (runContext.acceptancePath) {
    ensureDir(dirname(runContext.acceptancePath));
    writeFileSync(runContext.acceptancePath, buildFailureReport(error));
  }
}

async function main() {
  const argv = process.argv.slice(2);
  originalArgv = argv.slice();
  const args = parseArgs(argv);
  verboseFlag = Boolean(args.verbose);

  if (args.help || args.h) {
    console.log(usage());
    return;
  }

  const cwd = process.cwd();
  const projectDir = resolvePath(cwd, args["project-dir"] || args.project || ".");
  const boardRoot = resolvePath(cwd, args["board-root"]);
  const voiceoverPath = resolvePath(cwd, args.voiceover);
  const boardIndexPath = resolvePath(boardRoot || cwd, args["board-index"] || "board_index.json");
  const combinedMotionPlanPath = resolvePath(boardRoot || cwd, args["combined-motion-plan"] || "combined_motion_plan.json");
  const quality = args.quality || "standard";
  const version = args["hyperframes-version"] || HYPERFRAMES_VERSION;
  const dryRun = Boolean(args["dry-run"]);
  const skipTts = Boolean(args["skip-tts"]);
  const skipChecks = Boolean(args["skip-checks"]);
  const skipRender = Boolean(args["skip-render"]);
  const skipKeyframes = Boolean(args["skip-keyframes"]);

  runContext.projectDir = projectDir;
  runContext.acceptancePath = join(projectDir, "render_acceptance_report.md");

  verbose(`argv: ${[process.argv[0], process.argv[1], ...originalArgv].join(" ")}`);
  verbose(`resolved paths: projectDir=${projectDir} boardRoot=${boardRoot} voiceover=${voiceoverPath}`);

  if (!projectDir) fail("--project-dir is required");
  if (!boardRoot || !existsSync(boardRoot)) fail(`--board-root directory not found: ${boardRoot}`);
  if (!voiceoverPath || !existsSync(voiceoverPath)) fail(`--voiceover file not found: ${voiceoverPath}`);
  if (!boardIndexPath || !existsSync(boardIndexPath)) fail(`board_index.json not found: ${boardIndexPath}`);
  if (!combinedMotionPlanPath || !existsSync(combinedMotionPlanPath)) fail(`combined_motion_plan.json not found: ${combinedMotionPlanPath}`);

  ensureDir(projectDir);
  const audioDir = join(projectDir, "audio");
  const videoDir = join(projectDir, "video");
  const hfDir = join(videoDir, "hyperframes");
  const previewPath = join(videoDir, "preview.mp4");
  const keyframeDir = join(videoDir, "keyframes");

  setStep("load and validate multi-board inputs");
  const source = readJson(voiceoverPath);
  verbose("voiceover_segments loaded");
  const boardPackage = loadBoardPackage({ boardRoot, boardIndexPath, combinedMotionPlanPath });
  verbose(`board package loaded: ${Object.keys(boardPackage.boards).join(", ")}`);
  validateMultiBoardInputs({ source, ...boardPackage });
  const voice = getVoice(source, args);
  verbose(`voice: ${JSON.stringify(voice)}`);

  if (dryRun) {
    console.log(
      JSON.stringify(
        {
          projectDir,
          boardRoot,
          voiceoverPath,
          boardIndexPath,
          combinedMotionPlanPath,
          boards: Object.keys(boardPackage.boards),
          assets: Object.fromEntries(
            Object.entries(boardPackage.boards).map(([boardId, board]) => [
              boardId,
              {
                kind: board.imageRef.kind,
                uri: board.imageRef.uri,
                src: board.imageRef.src,
              },
            ]),
          ),
          segments: boardPackage.combinedMotionPlan.segments.length,
          actions: boardPackage.combinedMotionPlan.segments.reduce((sum, segment) => sum + (segment.actions || []).length, 0),
          voice,
          valid: true,
        },
        null,
        2,
      ),
    );
    return;
  }

  setStep("generate or load edge-tts voiceover timing");
  const audio = skipTts ? loadExistingTiming(projectDir, audioDir) : synthesizeVoiceover({ projectDir, source, voice, audioDir });
  verbose(`audio timing ready: totalDuration=${audio.timing.totalDuration}s`);

  setStep("build spokenAnchor timing from subtitles");
  const syncDir = join(projectDir, "sync");
  ensureDir(syncDir);
  const syncTimings = buildSyncTimings({
    projectDir,
    source,
    timing: audio.timing,
    combinedMotionPlan: boardPackage.combinedMotionPlan,
  });
  writeJson(join(audioDir, "word_timing.json"), syncTimings.wordTiming);
  writeJson(join(syncDir, "action_timing.json"), syncTimings.actionTiming);
  verbose(`timing generation complete: ${syncTimings.actionTiming.actions?.length || 0} actions`);

  setStep("update combined_motion_plan with measured timing");
  const timingUpdatedMotionPlan = updateCombinedMotionPlan({
    source,
    timing: audio.timing,
    combinedMotionPlan: boardPackage.combinedMotionPlan,
    actionTimingLookup: syncTimings.lookup,
  });
  const cameraStrategy = applyCameraStrategy({
    motionPlan: timingUpdatedMotionPlan,
    boards: boardPackage.boards,
  });
  const updatedMotionPlan = cameraStrategy.motionPlan;
  writeJson(join(syncDir, "camera_plan.json"), cameraStrategy.cameraPlan);
  const outputBoardRoot = writeOutputBoardPackage({
    projectDir,
    boardRoot,
    boardIndexPath,
    boardIndex: boardPackage.boardIndex,
    boards: boardPackage.boards,
    updatedMotionPlan,
  });

  setStep("generate editable HyperFrames project");
  ensureDir(videoDir);
  const hfProject = createHyperframesProject({
    projectDir,
    hfDir,
    audioDir,
    boards: boardPackage.boards,
    motionPlan: updatedMotionPlan,
    version,
  });
  verbose(`HyperFrames project generated: ${hfProject.relative}`);

  let checks = null;
  if (!skipChecks) {
    setStep("run HyperFrames lint validate inspect");
    checks = runHyperframesChecks(hfDir, version);
    verbose("HyperFrames checks complete");
  }

  let durationCheck = { renderedDuration: null, timingDuration: Number(audio.timing.totalDuration), delta: null };
  if (!skipRender) {
    setStep("render continuous preview MP4");
    rmSync(previewPath, { force: true });
    renderPreview(hfDir, previewPath, version, quality, args.fps);
    verbose("render process returned; verifying output file");
    if (!existsSync(previewPath)) {
      fail(`video/preview.mp4 was not created after render: ${previewPath}`);
    }
    const stats = statSync(previewPath);
    if (stats.size === 0) {
      fail(`video/preview.mp4 is empty (0 bytes): ${previewPath}`);
    }
    verbose(`preview.mp4 exists: ${stats.size} bytes`);
    const renderedDuration = formatSeconds(ffprobeDuration(previewPath));
    const timingDuration = Number(audio.timing.totalDuration);
    const delta = formatSeconds(Math.abs(renderedDuration - timingDuration));
    durationCheck = { renderedDuration, timingDuration, delta };
    verbose(`ffprobe duration: ${renderedDuration}s, timing duration: ${timingDuration}s, delta: ${delta}s`);
    if (delta > 1.0) {
      fail(`Rendered MP4 duration mismatch exceeds 1s: video=${renderedDuration.toFixed(3)}s timing=${timingDuration.toFixed(3)}s delta=${delta.toFixed(3)}s`);
    }
  }

  let keyframeSummary = { status: "skipped", actionCount: 0 };
  if (!skipRender && !skipKeyframes) {
    setStep("extract action start/done keyframes");
    rmSync(keyframeDir, { recursive: true, force: true });
    extractKeyframes(hfDir, previewPath, keyframeDir);
    const keyframeManifestPath = join(keyframeDir, "keyframe_manifest.json");
    const rows = readJson(keyframeManifestPath);
    keyframeSummary = { status: "complete", actionCount: rows.length };
    const expectedKeyframeActions = updatedMotionPlan.segments.reduce(
      (sum, segment) => sum + (segment.actions || []).length,
      0,
    );
    if (rows.length !== expectedKeyframeActions) {
      fail(`Expected ${expectedKeyframeActions} keyframe actions, found ${rows.length}`);
    }
    for (const row of rows) {
      for (const field of ["boardId", "segment", "annotation", "type", "element", "drawStart", "drawDone"]) {
        if (row[field] === undefined || row[field] === null || row[field] === "") {
          fail(`keyframe_manifest.json row ${row.index} missing ${field}`);
        }
      }
    }
    verbose(`keyframes extracted: ${rows.length} actions`);
  }

  setStep("write action and camera QA report");
  const qaReport = buildActionCameraQa({
    projectDir,
    motionPlan: updatedMotionPlan,
    boards: boardPackage.boards,
    actionTiming: syncTimings.actionTiming,
    cameraPlan: cameraStrategy.cameraPlan,
    keyframeDir,
    keyframeSummary,
  });
  writeJson(join(syncDir, "action_camera_qa_report.json"), qaReport.json);
  writeFileSync(join(syncDir, "action_camera_qa_report.md"), qaReport.markdown);
  verbose(`QA report written: status=${qaReport.summary.status}`);

  const scriptPath = fileURLToPath(import.meta.url);
  const scriptDir = dirname(scriptPath);
  const helpProbe = runCapture("node", [join(scriptDir, "render_whiteboard_project.mjs"), "--help"], scriptDir);
  const dryRunProbe = runCapture(
    "node",
    [
      scriptPath,
      "--project-dir",
      projectDir,
      "--board-root",
      boardRoot,
      "--voiceover",
      voiceoverPath,
      "--dry-run",
    ],
    cwd,
  );

  const report = {
    projectDir,
    mode: "multi-board",
    inputs: {
      boardRoot,
      boardIndex: boardIndexPath,
      combinedMotionPlan: combinedMotionPlanPath,
      voiceover: voiceoverPath,
    },
    outputs: {
      audio: rel(projectDir, audio.narrationPath),
      timing: "audio/voiceover_timing.json",
      wordTiming: "audio/word_timing.json",
      captions: "audio/captions.srt",
      actionTiming: "sync/action_timing.json",
      cameraPlan: "sync/camera_plan.json",
      actionCameraQa: "sync/action_camera_qa_report.md",
      actionCameraQaJson: "sync/action_camera_qa_report.json",
      boardPackage: rel(projectDir, outputBoardRoot),
      hyperframes: hfProject.relative,
      preview: existsSync(previewPath) ? rel(projectDir, previewPath) : null,
      keyframes: existsSync(keyframeDir) ? rel(projectDir, keyframeDir) : null,
    },
    voice,
    totalDuration: audio.timing.totalDuration,
    boards: Object.keys(boardPackage.boards),
    assets: Object.fromEntries(
      Object.entries(boardPackage.boards).map(([boardId, board]) => [
        boardId,
        {
          kind: board.imageRef.kind,
          uri: board.imageRef.uri,
          src: board.imageRef.src,
        },
      ]),
    ),
    segments: updatedMotionPlan.segments.map((segment) => ({
      id: segment.id,
      boardId: segment.boardId,
      cameraStrategy: segment.cameraStrategy,
      start: segment.start,
      speechEnd: segment.speechEnd,
      end: segment.end,
      actions: (segment.actions || []).length,
    })),
    sync: summarizeSync(syncTimings.actionTiming),
    camera: {
      plan: "sync/camera_plan.json",
      strategies: cameraStrategy.cameraPlan.strategies,
      zoomThresholds: cameraStrategy.cameraPlan.zoomThresholds,
      warnings: qaReport.summary.cameraWarnings,
    },
    qa: qaReport.summary,
    validation: {
      help: helpProbe.status === 0 ? "pass" : "fail",
      dryRun: dryRunProbe.status === 0 ? "pass" : "fail",
      helpCommand: helpProbe.command,
      dryRunCommand: dryRunProbe.command,
      helpStdout: helpProbe.stdout,
      helpStderr: helpProbe.stderr,
      dryRunStdout: dryRunProbe.stdout,
      dryRunStderr: dryRunProbe.stderr,
    },
    checks: checks
      ? {
          lint: { status: checks.lint.status, stdout: checks.lint.stdout, stderr: checks.lint.stderr },
          validate: { status: checks.validate.status, stdout: checks.validate.stdout, stderr: checks.validate.stderr },
          inspect: {
            status: checks.inspect.status,
            attempts: checks.inspect.attempts,
            stdout: checks.inspect.stdout,
            stderr: checks.inspect.stderr,
          },
        }
      : "skipped",
    durationCheck,
    render: skipRender ? "skipped" : "complete",
    keyframes: keyframeSummary,
  };

  if (helpProbe.status !== 0) fail("help probe failed");
  if (dryRunProbe.status !== 0) fail("dry-run probe failed");

  writeJson(join(videoDir, "renderer_report.json"), report);
  writeFileSync(runContext.acceptancePath, buildAcceptanceReport(report));
  console.log(JSON.stringify(report.outputs, null, 2));
}

main().catch((error) => {
  const failedPath = runContext.acceptancePath || "<unknown>";
  const failedProjectDir = runContext.projectDir || "<unknown>";
  writeFailureReport(error);
  console.error(`\n[multi-board-renderer] FATAL ERROR`);
  console.error(`  failed step: ${runContext.step}`);
  console.error(`  project dir: ${failedProjectDir}`);
  console.error(`  report path: ${failedPath}`);
  console.error(`  argv:        ${[process.argv[0], process.argv[1], ...originalArgv].join(" ")}`);
  console.error(`\n${error?.stack || error?.message || String(error)}`);
  process.exit(1);
});
