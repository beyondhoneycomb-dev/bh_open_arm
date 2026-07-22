// The inputs S-07 renders from, and an honest offline default. Like every screen,
// data collection is a window: the stamped dataset name, the drop counts, the disk
// prediction, the resumable sessions and the WP-3C gate verdicts all originate in
// the backend. This module names the default source and supplies a fixture standing
// in for a backend that is not attached — the GUI is verified against fixtures,
// never real hardware (WP-G-S07 is AI-offline).
//
// The default is deliberately pre-run and honest: the session is inactive, the disk
// prediction leaves well over an hour of headroom (so the start is not spuriously
// blocked), push_to_hub is off, and every WP-3C gate reads `pending` because those
// hardware gates are not built yet — never a fabricated pass.

import type { CollectData, CollectDataSource } from "./types";

// The three WP-3C gates S-07 surfaces, pre-landing. PG-STO-001 is the storage
// integrity gate (WP-3C-02); the other two name the interlock (WP-3C-06) and the
// crash/resume path (WP-3C-07). All render `pending` until the hardware gate lands.
export function pendingThreeCGates(): CollectData["gates"] {
  return [
    {
      id: "PG-STO-001",
      label: "저장 무결성 (WP-3C-02)",
      state: "pending",
      detail: "하드웨어 게이트 미착지 — 판정 대기",
    },
    {
      id: "WP-3C-06",
      label: "무결성·원본삭제 인터록",
      state: "pending",
      detail: "하드웨어 게이트 미착지 — 판정 대기",
    },
    {
      id: "WP-3C-07",
      label: "크래시·재개",
      state: "pending",
      detail: "하드웨어 게이트 미착지 — 판정 대기",
    },
  ];
}

const GIGABYTE = 1024 * 1024 * 1024;

export function defaultCollectData(): CollectData {
  return {
    sessionActive: false,
    events: { exitEarly: false, rerecordEpisode: false, stopRecording: false },
    dataset: {
      requestedRepoId: "openarm/pick_place",
      stampedRepoId: "openarm/pick_place_20260723_061500",
    },
    taskPrompt: { text: "빨간 블록을 집어 상자에 넣는다" },
    recordedEpisodeCount: 0,
    dropReport: {
      frameCount: 0,
      wsTransmit: [],
      camera: [],
      can: { flaggedFrames: 0, suspectedStaleFrames: 0 },
    },
    storage: {
      freeBytes: 512 * GIGABYTE,
      totalBytes: 1024 * GIGABYTE,
      bytesPerHour: 18 * GIGABYTE,
      headroomHours: 512 / 18,
    },
    preflight: [
      { id: "can", passed: true },
      { id: "cameras", passed: true },
      { id: "velocity_torque", passed: true },
      { id: "calibration", passed: true },
      { id: "disk", passed: true },
      { id: "profile", passed: true },
    ],
    pushToHub: { enabled: false, private: true, tags: [] },
    resumable: [],
    gates: pendingThreeCGates(),
  };
}

export function defaultCollectSource(): CollectDataSource {
  return {
    load: defaultCollectData,
  };
}
