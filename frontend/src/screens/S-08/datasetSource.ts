// The inputs S-08 renders from, and an honest offline default. Like every screen,
// the dataset browser is a window: the dataset inventory, the per-episode signals, the
// capture_ts jitter sidecar, the label sidecar, the integrity report and the CoW edit
// preview all originate in the Wave 3D backend. This module names the default source
// and supplies a fixture standing in for a backend that is not attached — the GUI is
// verified against fixtures, never real hardware (WP-G-S08 is AI-offline).
//
// The fixture is deliberately realistic and honest: the selected dataset carries a
// mixed-unit observation.state (pos/vel/torque per motor, the 24-dim family), an
// episode with an auto-suggested label, a capture_ts sidecar with genuine (uneven)
// grab spacing so the jitter view is non-trivial, an integrity report that verified
// READY, and a copy-on-write delete_episodes preview that writes to a NEW repo_id. A
// second dataset in the list is the pos-only (8-dim) family, so the browse list shows
// both state shapes the names index must survive.

import type {
  CaptureTsSidecar,
  DatasetDataSource,
  DatasetScreenData,
  DatasetSummary,
  EpisodeSignals,
  EpisodeSummary,
  VerificationReport,
} from "./types";
import {
  POSITION_SUFFIX,
  TORQUE_SUFFIX,
  VELOCITY_SUFFIX,
} from "./channels";

const FPS = 30;
const GIGABYTE = 1024 * 1024 * 1024;
const NS_PER_SECOND = 1_000_000_000;

// Two motors, each contributing a .pos/.vel/.torque channel to observation.state —
// the mixed-unit vector the per-channel axis labels exist for (CG-G-S08g).
const MOTORS = ["left_joint_1", "right_gripper"] as const;

function stateNamesFor(useVelocityAndTorque: boolean): string[] {
  const names: string[] = [];
  for (const motor of MOTORS) {
    names.push(`${motor}${POSITION_SUFFIX}`);
    if (useVelocityAndTorque) {
      names.push(`${motor}${VELOCITY_SUFFIX}`);
      names.push(`${motor}${TORQUE_SUFFIX}`);
    }
  }
  return names;
}

// action is position only by CTR-REC@v1 — one .pos channel per motor.
function actionNames(): string[] {
  return MOTORS.map((motor) => `${motor}${POSITION_SUFFIX}`);
}

// A deterministic per-frame row: each channel is a smooth ramp offset by its column,
// so the plot has visible, distinct traces without any timing math in the fixture.
function stateRow(frame: number, dim: number): number[] {
  const row: number[] = [];
  for (let channel = 0; channel < dim; channel += 1) {
    row.push(Number((channel * 5 + frame * 1.5).toFixed(3)));
  }
  return row;
}

function actionRow(frame: number, dim: number): number[] {
  const row: number[] = [];
  for (let channel = 0; channel < dim; channel += 1) {
    row.push(Number((channel * 5 + frame * 1.4).toFixed(3)));
  }
  return row;
}

const FRAME_COUNT = 6;

function signalsFor(episodeIndex: number, useVelocityAndTorque: boolean): EpisodeSignals {
  const stateNames = stateNamesFor(useVelocityAndTorque);
  const actionCols = actionNames();
  const frameIndices = Array.from({ length: FRAME_COUNT }, (_unused, i) => i);
  const timestamps = frameIndices.map((i) => Number((i / FPS).toFixed(6)));
  return {
    episodeIndex,
    timeAxis: {
      fps: FPS,
      frameIndices,
      timestamps,
      isWallClock: false,
      domainNote: "timestamp = frame_index / fps (합성 그리드 좌표, 캡처 시각 아님)",
    },
    stateNames,
    actionNames: actionCols,
    state: frameIndices.map((frame) => stateRow(frame, stateNames.length)),
    action: frameIndices.map((frame) => actionRow(frame, actionCols.length)),
  };
}

// A capture_ts sidecar with genuinely uneven grab spacing (nominal ~33.3 ms at 30 fps,
// but drifting a few ms frame to frame) so the jitter view reports a real, non-zero
// spread — the exact figure the synthetic grid would flatten to zero (CG-G-S08c).
function captureSidecar(slot: string, base: number, spacingMs: readonly number[]): CaptureTsSidecar {
  const captureTsNs: number[] = [base];
  let cursor = base;
  for (const ms of spacingMs) {
    cursor += Math.round(ms * 1_000_000);
    captureTsNs.push(cursor);
  }
  return { slot, captureTsNs };
}

const SELECTED_REPO_ID = "openarm/pick_place_20260723_061500";
const POS_ONLY_REPO_ID = "openarm/stack_cubes_20260722_143000";

function selectedDataset(): DatasetSummary {
  return {
    stampedRepoId: SELECTED_REPO_ID,
    contentHash: "sha256:9f2c1a7e4b",
    revision: "v3.0",
    totalEpisodes: 3,
    totalFrames: 540,
    stateDim: stateNamesFor(true).length,
    useVelocityAndTorque: true,
    fps: FPS,
  };
}

function posOnlyDataset(): DatasetSummary {
  return {
    stampedRepoId: POS_ONLY_REPO_ID,
    contentHash: "sha256:41ad88c012",
    revision: "v3.0",
    totalEpisodes: 5,
    totalFrames: 900,
    stateDim: stateNamesFor(false).length,
    useVelocityAndTorque: false,
    fps: FPS,
  };
}

function episodes(): EpisodeSummary[] {
  return [
    {
      episodeIndex: 0,
      length: 180,
      tasks: ["빨간 블록을 집어 상자에 넣는다"],
      label: {
        episodeIndex: 0,
        status: "judged",
        auto: { verdict: "success", provenance: "auto" },
        manual: { verdict: "success", provenance: "manual" },
        abortReason: null,
        autoSaved: true,
      },
    },
    {
      episodeIndex: 1,
      length: 200,
      tasks: ["빨간 블록을 집어 상자에 넣는다"],
      // Auto suggests success but the human has not yet ruled — the screen shows the
      // suggestion and offers a verdict, never inventing the human's.
      label: {
        episodeIndex: 1,
        status: "judged",
        auto: { verdict: "success", provenance: "auto" },
        manual: null,
        abortReason: null,
        autoSaved: true,
      },
    },
    {
      episodeIndex: 2,
      length: 160,
      tasks: ["빨간 블록을 집어 상자에 넣는다"],
      // A crash-recovered episode held for human judgment — never auto-saved.
      label: {
        episodeIndex: 2,
        status: "pending_judgment",
        auto: null,
        manual: null,
        abortReason: "crash-footerless-parquet",
        autoSaved: false,
      },
    },
  ];
}

function verificationReport(): VerificationReport {
  const pass = (name: string, detail: string) =>
    ({ name, status: "pass", detail }) as const;
  return {
    root: `datasets/${SELECTED_REPO_ID}`,
    results: [
      pass("parquet_footer", "모든 parquet 푸터 present"),
      pass("info_chunk_consistency", "info.json ↔ chunk 파일 정합"),
      pass("index_continuity", "frame_index / episode_index 연속"),
      pass("video_frame_count", "영상 프레임 수 = 에피소드 길이"),
      pass("dtype_match", "feature dtype 정합"),
      pass("stats_hash_match", "stats 해시 일치"),
      pass("no_edit_invalid_marker", "편집 무효화 마커 없음"),
    ],
    ready: true,
    verdict: "READY",
    missingChecks: [],
    elapsedSeconds: 1.84,
    datasetBytes: 3 * GIGABYTE,
  };
}

// A fixed nanosecond origin for the capture_ts fixture. It is an opaque monotonic
// base, never read as wall-clock — the sidecar carries INTERVALS, and the jitter view
// consumes only their spread. Kept small (well under float64's exact-integer range) so
// the interval differences are exact; a real ns epoch is the backend's concern.
const CAPTURE_TS_ORIGIN_NS = 1_000_000_000;

export function defaultDatasetScreenData(): DatasetScreenData {
  const base = CAPTURE_TS_ORIGIN_NS;
  return {
    datasets: [selectedDataset(), posOnlyDataset()],
    selectedRepoId: SELECTED_REPO_ID,
    episodes: episodes(),
    selectedEpisodeIndex: 0,
    signals: signalsFor(0, true),
    cameraStreams: [
      {
        imageKey: "observation.images.right_wrist",
        slot: "right_wrist",
        isDepth: false,
        shape: ["height", "width", 3],
      },
      {
        imageKey: "observation.images.right_wrist_depth",
        slot: "right_wrist",
        isDepth: true,
        shape: ["height", "width", 1],
      },
      {
        imageKey: "observation.images.front",
        slot: "front",
        isDepth: false,
        shape: ["height", "width", 3],
      },
    ],
    captureJitter: [
      captureSidecar("right_wrist", base, [33.4, 33.1, 32.6, 34.8, 32.3]),
      captureSidecar("front", base + NS_PER_SECOND, [33.3, 33.2, 33.5, 33.1, 33.4]),
    ],
    verification: verificationReport(),
    editPreview: {
      operation: "delete_episodes",
      policy: { renumbers: true, inPlace: false, multiOutput: false, crossDataset: false },
      sourceRepoId: SELECTED_REPO_ID,
      outputRepoId: "openarm/pick_place_20260723_061500_edit_20260724_090000",
      summary: "에피소드 2 삭제 → 새 데이터셋으로 기록 (원본 보존)",
    },
  };
}

export function defaultDatasetSource(): DatasetDataSource {
  return {
    load: defaultDatasetScreenData,
  };
}
