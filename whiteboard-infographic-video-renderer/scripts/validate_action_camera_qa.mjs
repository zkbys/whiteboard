#!/usr/bin/env node
import {
  copyFileSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join, resolve } from "node:path";
import { execFileSync, spawnSync } from "node:child_process";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--keep-temp") {
      out.keepTemp = true;
    } else if (token === "--real-render") {
      out.realRender = true;
    } else if (token === "--quality") {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) fail("--quality requires a value");
      out.quality = argv[i + 1];
      i += 1;
    } else if (token.startsWith("--quality=")) {
      out.quality = token.slice("--quality=".length);
      if (!out.quality) fail("--quality requires a value");
    } else if (token === "--fps") {
      if (!argv[i + 1] || argv[i + 1].startsWith("--")) fail("--fps requires a value");
      out.fps = argv[i + 1];
      i += 1;
    } else if (token.startsWith("--fps=")) {
      out.fps = token.slice("--fps=".length);
      if (!out.fps) fail("--fps requires a value");
    } else if (token === "--help" || token === "-h") {
      out.help = true;
    } else {
      fail(`Unknown option: ${token}`);
    }
  }
  return out;
}

function usage() {
  return `Usage:
  node whiteboard-infographic-video-renderer/scripts/validate_action_camera_qa.mjs [--keep-temp]
  node whiteboard-infographic-video-renderer/scripts/validate_action_camera_qa.mjs --real-render [--quality draft] [--fps 8] [--keep-temp]

Builds a temporary multi-board renderer fixture, runs render_multi_board_project.mjs
with --skip-tts --skip-checks --skip-render by default, and verifies action
rhythm, camera strategy, and action/camera QA outputs.

With --real-render, the script reuses deterministic fixture timing with a local
silent WAV, then runs HyperFrames checks, MP4 rendering, and action keyframe
extraction in the temporary fixture.`;
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

function writeText(path, text) {
  ensureDir(dirname(path));
  writeFileSync(path, text);
}

function assertFile(path, label) {
  if (!existsSync(path)) fail(`${label} missing: ${path}`);
}

function assert(condition, message) {
  if (!condition) fail(message);
}

function assertNumber(value, label) {
  assert(Number.isFinite(Number(value)), `${label} must be numeric`);
}

function cloneJson(value) {
  return JSON.parse(JSON.stringify(value));
}

function buildAnnotationManifest(manifest) {
  const annotations = [];
  for (const element of manifest.elements || []) {
    for (const [id, annotation] of Object.entries(element.annotations || {})) {
      annotations.push({
        id,
        element: element.id,
        bbox: element.bbox,
        camera: element.camera,
        ...annotation,
      });
    }
  }
  return {
    canvas: manifest.canvas,
    source_image: "board.png",
    coordinate_system: "board-image-pixels",
    annotations,
  };
}

function fixtureTiming(source) {
  return {
    engine: "fixture",
    totalDuration: 8,
    segments: [
      {
        id: "hook",
        text: source.segments[0].text,
        caption: source.segments[0].caption,
        start: 0,
        speechEnd: 3.5,
        end: 3.62,
        speechDuration: 3.5,
        media: { subtitles: "audio/segments/01-hook.vtt" },
        actions: source.segments[0].actions,
      },
      {
        id: "method",
        text: source.segments[1].text,
        caption: source.segments[1].caption,
        start: 3.62,
        speechEnd: 8,
        end: 8,
        speechDuration: 4.38,
        media: { subtitles: "audio/segments/02-method.vtt" },
        actions: source.segments[1].actions,
      },
    ],
  };
}

function writeSilentNarration(path, durationSec) {
  ensureDir(dirname(path));
  execFileSync(
    "ffmpeg",
    [
      "-y",
      "-f",
      "lavfi",
      "-i",
      "anullsrc=r=48000:cl=mono",
      "-t",
      String(durationSec),
      "-c:a",
      "pcm_s16le",
      path,
    ],
    { stdio: "ignore" },
  );
}

function buildFixture({ repoRoot, projectDir, useRealAudio }) {
  const exampleRoot = join(repoRoot, "whiteboard-infographic-video-renderer", "examples", "input");
  const source = cloneJson(readJson(join(exampleRoot, "script", "voiceover_segments.json")));
  const manifest = readJson(join(exampleRoot, "board", "board-01.board_manifest.json"));
  const motion = cloneJson(readJson(join(exampleRoot, "board", "board-01.motion_plan.json")));

  for (const segment of source.segments || []) segment.boardId = "board-01";
  for (const segment of motion.segments || []) segment.boardId = "board-01";

  const boardRoot = join(projectDir, "board_source_for_e");
  const boardDir = join(boardRoot, "board-01");
  ensureDir(boardDir);

  writeJson(join(projectDir, "script", "voiceover_segments.json"), source);
  copyFileSync(join(exampleRoot, "board", "board.png"), join(boardDir, "board.png"));
  writeJson(join(boardDir, "board_manifest.json"), manifest);
  writeJson(join(boardDir, "annotation_manifest.json"), buildAnnotationManifest(manifest));
  writeJson(join(boardDir, "motion_plan.json"), motion);
  writeJson(join(boardRoot, "board_index.json"), {
    version: "0.1",
    boards: [
      {
        boardId: "board-01",
        path: "board-01",
        asset: { kind: "file", localPath: "board.png" },
      },
    ],
    combinedMotionPlan: "combined_motion_plan.json",
  });
  writeJson(join(boardRoot, "combined_motion_plan.json"), motion);

  const timing = fixtureTiming(source);
  if (useRealAudio) {
    writeSilentNarration(join(projectDir, "audio", "narration.wav"), timing.totalDuration);
  } else {
    writeText(join(projectDir, "audio", "narration.wav"), "placeholder audio for skipped render validation\n");
  }
  writeJson(join(projectDir, "audio", "voiceover_timing.json"), timing);
  writeText(
    join(projectDir, "audio", "segments", "01-hook.vtt"),
    "WEBVTT\n\n00:00:00.000 --> 00:00:03.500\n做白板视频，最怕的是画面和口播不同步。\n",
  );
  writeText(
    join(projectDir, "audio", "segments", "02-method.vtt"),
    "WEBVTT\n\n00:00:00.000 --> 00:00:04.380\n先测真实音频时长，再把每个批注动作压到句子里面。\n",
  );

  return {
    source,
    boardRoot,
    voiceoverPath: join(projectDir, "script", "voiceover_segments.json"),
  };
}

function runRenderer({ repoRoot, projectDir, boardRoot, voiceoverPath, realRender, quality, fps }) {
  const scriptPath = join(repoRoot, "whiteboard-infographic-video-renderer", "scripts", "render_multi_board_project.mjs");
  const args = [
    scriptPath,
    "--project-dir",
    projectDir,
    "--board-root",
    boardRoot,
    "--voiceover",
    voiceoverPath,
  ];
  if (realRender) {
    args.push("--skip-tts", "--quality", quality || "draft");
    if (fps) args.push("--fps", String(fps));
  } else {
    args.push("--skip-tts", "--skip-checks", "--skip-render");
  }
  const result = spawnSync(
    process.execPath,
    args,
    { cwd: repoRoot, encoding: "utf8" },
  );
  if (result.status !== 0) {
    const output = [result.stdout, result.stderr].join("\n").trim();
    fail(`renderer smoke failed with exit ${result.status}\n${output}`);
  }
}

function validateOutputs(projectDir, { realRender }) {
  const actionTimingPath = join(projectDir, "sync", "action_timing.json");
  const cameraPlanPath = join(projectDir, "sync", "camera_plan.json");
  const qaMarkdownPath = join(projectDir, "sync", "action_camera_qa_report.md");
  const qaJsonPath = join(projectDir, "sync", "action_camera_qa_report.json");
  const combinedPath = join(projectDir, "board", "combined_motion_plan.json");
  const hfPlanPath = join(projectDir, "video", "hyperframes", "assets", "board", "motion_plan.json");
  const hfAudioPath = join(projectDir, "video", "hyperframes", "assets", "audio", "narration.wav");
  const hfCameraPath = join(projectDir, "video", "hyperframes", "assets", "board", "camera_plan.json");
  const reportPath = join(projectDir, "video", "renderer_report.json");
  const previewPath = join(projectDir, "video", "preview.mp4");
  const keyframeManifestPath = join(projectDir, "video", "keyframes", "keyframe_manifest.json");
  const contactStartPath = join(projectDir, "video", "keyframes", "contact_sheet_start.jpg");
  const contactDonePath = join(projectDir, "video", "keyframes", "contact_sheet_done.jpg");

  for (const [path, label] of [
    [join(projectDir, "audio", "word_timing.json"), "word timing"],
    [actionTimingPath, "action timing"],
    [cameraPlanPath, "camera plan"],
    [qaMarkdownPath, "QA markdown"],
    [qaJsonPath, "QA json"],
    [combinedPath, "updated combined motion plan"],
    [hfPlanPath, "HyperFrames motion plan copy"],
    [hfAudioPath, "HyperFrames audio copy"],
    [hfCameraPath, "HyperFrames camera plan copy"],
    [reportPath, "renderer report"],
  ]) {
    assertFile(path, label);
  }

  const actionTiming = readJson(actionTimingPath);
  const cameraPlan = readJson(cameraPlanPath);
  const qa = readJson(qaJsonPath);
  const combined = readJson(combinedPath);
  const report = readJson(reportPath);
  const qaMarkdown = readFileSync(qaMarkdownPath, "utf8");

  assert(actionTiming.actions?.length === 2, "fixture should produce two action timing rows");
  for (const [index, action] of actionTiming.actions.entries()) {
    assert(action.syncSource === "cue-tokenized", `action ${index} should use cue-tokenized sync`);
    assert(action.rhythm?.source === "renderer-action-rhythm-v0.1", `action ${index} missing rhythm source`);
    for (const field of ["preArrivalSec", "cursorMoveLeadSec", "holdAfterSec", "drawStartOffset", "drawDoneOffset"]) {
      assertNumber(action.rhythm[field], `action ${index} rhythm.${field}`);
    }
  }

  for (const strategy of ["overview", "region", "emphasis", "recovery"]) {
    assert(cameraPlan.strategies?.includes(strategy), `camera plan missing ${strategy} strategy`);
  }
  assert(cameraPlan.segments?.length === 2, "camera plan should include two segment rows");
  assert(cameraPlan.segments.some((segment) => segment.strategy === "overview"), "camera plan should include overview strategy");
  assert(cameraPlan.segments.some((segment) => segment.strategy === "recovery"), "camera plan should include recovery strategy");
  assert(cameraPlan.segments.every((segment) => segment.zoomStatus === "pass"), "fixture camera zoom should pass");

  for (const [segmentIndex, segment] of (combined.segments || []).entries()) {
    assert(segment.cameraPlan?.source === "renderer-camera-strategy-v0.1", `segment ${segmentIndex} missing camera plan`);
    assert(segment.cameraStrategy, `segment ${segmentIndex} missing camera strategy`);
    for (const [actionIndex, action] of (segment.actions || []).entries()) {
      assert(action.anchorRatioSource === "sync/action_timing.json", `segment ${segmentIndex} action ${actionIndex} should use action timing`);
      assert(action.rhythm?.source === "renderer-action-rhythm-v0.1", `segment ${segmentIndex} action ${actionIndex} missing rhythm`);
    }
  }

  assert(qa.summary?.actionCount === 2, "QA summary should cover two actions");
  assert(qa.summary?.fallbackActions === 0, "QA summary should report zero fallback actions");
  assert(qa.summary?.bboxIssues === 0, "QA summary should report zero bbox issues");
  assert(qa.summary?.cameraWarnings === 0, "QA summary should report zero camera warnings");
  if (realRender) {
    assertFile(previewPath, "preview MP4");
    assertFile(keyframeManifestPath, "keyframe manifest");
    assertFile(contactStartPath, "start contact sheet");
    assertFile(contactDonePath, "done contact sheet");
    const keyframes = readJson(keyframeManifestPath);
    assert(keyframes.length === 2, "real render should create two keyframe rows");
    assert(qa.summary?.keyframeArtifacts?.manifest === true, "real render should create keyframe manifest");
    assert(qa.summary?.keyframeArtifacts?.contactSheetStart === true, "real render should create start contact sheet");
    assert(qa.summary?.keyframeArtifacts?.contactSheetDone === true, "real render should create done contact sheet");
    assert(qa.summary?.keyframeIssues === 0, "real render should report zero keyframe issues");
  } else {
    assert(qa.summary?.keyframeArtifacts?.manifest === false, "skipped render should not create keyframe manifest");
    assert(qaMarkdown.includes("keyframes manifest: missing or skipped"), "QA markdown should disclose skipped keyframes");
  }

  assert(report.outputs?.cameraPlan === "sync/camera_plan.json", "renderer report missing camera plan output");
  assert(report.outputs?.actionCameraQa === "sync/action_camera_qa_report.md", "renderer report missing QA output");
  assert(report.qa?.actionCount === 2, "renderer report missing QA summary");
  if (realRender) {
    assert(report.render === "complete", "real render should report render complete");
    assert(report.keyframes?.status === "complete", "real render should report keyframes complete");
    assert(Number(report.durationCheck?.delta) <= 0.1, "real render duration delta should be within threshold");
  }

  return {
    mode: realRender ? "real-render-fixture-audio" : "fast-smoke",
    actions: actionTiming.actions.length,
    strategies: cameraPlan.segments.map((segment) => segment.strategy),
    qaStatus: qa.summary.status,
    keyframes: realRender ? qa.summary.keyframeArtifacts : "skipped",
  };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(usage());
    return;
  }

  const scriptDir = dirname(fileURLToPath(import.meta.url));
  const repoRoot = resolve(scriptDir, "..", "..");
  const projectDir = mkdtempSync(join(tmpdir(), "whiteboard-action-camera-qa-"));
  let passed = false;

  try {
    const fixture = buildFixture({ repoRoot, projectDir, useRealAudio: Boolean(args.realRender) });
    runRenderer({
      repoRoot,
      projectDir,
      boardRoot: fixture.boardRoot,
      voiceoverPath: fixture.voiceoverPath,
      realRender: Boolean(args.realRender),
      quality: args.quality,
      fps: args.fps,
    });
    const summary = validateOutputs(projectDir, { realRender: Boolean(args.realRender) });
    passed = true;
    console.log(
      JSON.stringify(
        {
          status: "pass",
          projectDir: args.keepTemp ? projectDir : "<removed>",
          ...summary,
        },
        null,
        2,
      ),
    );
  } finally {
    if (passed && !args.keepTemp) {
      rmSync(projectDir, { recursive: true, force: true });
    } else if (!passed || args.keepTemp) {
      console.error(`temporary fixture retained at: ${projectDir}`);
    }
  }
}

main();
