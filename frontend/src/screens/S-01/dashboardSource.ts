// The inputs S-01 renders from, and an honest offline default. Like every screen
// the dashboard is a window: connection, CAN, camera, disk, GPU, session and
// subsystem state all originate in the committed backend and arrive over the
// CTR-WS envelope. This module names the default source and supplies a fixture
// standing in for a fully-landed backend — the GUI is verified against fixtures,
// never real hardware (WP-G-S01 is AI-offline).
//
// One value is UNAVAILABLE even in this landed stand-in, and deliberately so: the
// loop cycle-time p95 comes from the PG-RT-001b artifact (Wave 3C real-load final
// canon), and on this offline box that artifact has not landed — no hardware, no
// real-load histogram. The fixture therefore carries the cycle-time UNAVAILABLE
// variant, which the tile renders AS unavailable, never as OK or a fabricated
// number (CG-G-S01d/e). Filling that gap with a zero would be the
// get_observation()-fills-missing-with-0 bug in dashboard form.

import { CYCLE_TIME_SOURCE } from "./types";
import type {
  CameraStreamStat,
  CanInterfaceStatus,
  DashboardData,
  DashboardSource,
  SubsystemStatus,
} from "./types";

function subsystems(): SubsystemStatus[] {
  return [
    {
      id: "can",
      label: "CAN 인터페이스 ×2",
      status: "OK",
      detail: "ERROR-ACTIVE, 에러 카운터 정지, 비인가 writer 없음",
      critical: false,
    },
    {
      id: "motors",
      label: "모터 ×16",
      status: "OK",
      detail: "전 축 Enable(ERR=1), 온도 WARN 임계 미만",
      critical: false,
    },
    {
      id: "control_loop",
      label: "제어 루프",
      status: "OK",
      detail: "실측 Hz 목표 이내, 오버런 0",
      critical: false,
    },
    {
      id: "cameras",
      label: "카메라 ×N",
      status: "OK",
      detail: "전 스트림 발행 중, age 임계 미만",
      critical: false,
    },
    {
      id: "vr_link",
      label: "VR 링크",
      status: "OK",
      detail: "validity=OK, 하트비트 age < timeout",
      critical: false,
    },
    {
      id: "ik_solver",
      label: "IK 솔버",
      status: "OK",
      detail: "잔차 임계 미만, 폴백 미발동",
      critical: false,
    },
    {
      id: "gui_backend",
      label: "GUI 백엔드 (CAN 소유)",
      status: "OK",
      detail: "프로세스 생존 + 제어 루프 하트비트",
      critical: false,
    },
    {
      id: "zero_integrity",
      label: "영점 무결성",
      status: "OK",
      detail: "m_off = 골든값, 관절각 리밋 내",
      critical: false,
    },
    {
      id: "dataset_contract",
      label: "데이터셋 계약",
      status: "OK",
      detail: "커플드 플래그 대칭, 차원 정합, push_to_hub=false",
      critical: false,
    },
  ];
}

function canInterfaces(): CanInterfaceStatus[] {
  return [
    {
      iface: "can0",
      lockHeld: true,
      boundSocketCount: 1,
      intruderPresent: false,
      intruderPids: [],
      state: "OK",
    },
    {
      iface: "can1",
      lockHeld: true,
      boundSocketCount: 1,
      intruderPresent: false,
      intruderPids: [],
      state: "OK",
    },
  ];
}

// Two active streams; the tile count is this array's length, so a third camera
// would add a tile with no code change (CG-G-S01c). UI label and dataset key
// differ (per-arm prefix) and both are carried.
function cameras(): CameraStreamStat[] {
  return [
    {
      slot: "left_wrist",
      uiLabel: "wrist_left",
      datasetKey: "observation.images.left_wrist",
      fps: 29.7,
      jitterMs: 1.3,
      state: "OK",
    },
    {
      slot: "right_wrist",
      uiLabel: "wrist_right",
      datasetKey: "observation.images.right_wrist",
      fps: 29.8,
      jitterMs: 1.6,
      state: "OK",
    },
  ];
}

export function defaultDashboardData(): DashboardData {
  return {
    connection: {
      connected: true,
      mode: "MANUAL",
      sessionId: "sess_20260725_dev",
      controlHolder: "operator@console-1",
      activeProfileId: "profile_bimanual_default",
    },
    can: canInterfaces(),
    flags: {
      useVelocityAndTorque: true,
      pushToHub: false,
    },
    cameras: cameras(),
    disk: {
      freeBytes: 442000000000,
      freeDisplay: "442 GB",
      exhaustionDisplay: "2026-09-12 (est.)",
      state: "OK",
    },
    gpu: {
      present: true,
      name: "NVIDIA RTX 5080",
      vramDisplay: "3.1 / 16.0 GB",
      utilizationDisplay: "12 %",
      temperatureDisplay: "44 °C",
      state: "OK",
    },
    // The PG-RT-001b real-load histogram has not landed on this box (no hardware).
    // Rendered UNAVAILABLE, never a number (CG-G-S01d/e).
    cycleTime: {
      available: false,
      source: CYCLE_TIME_SOURCE,
      reason: "실부하 사이클타임 아티팩트 미착지 — Wave 3C(실카메라·데이터셋·동일 프로세스) 하드웨어 필요",
    },
    subsystems: subsystems(),
    sessions: [
      {
        id: "ep_20260724_pickplace",
        name: "bimanual_pick_place",
        startedDisplay: "2026-07-24 14:02",
        episodeCount: 40,
        outcome: "완료",
      },
      {
        id: "ep_20260723_stack",
        name: "bimanual_stack",
        startedDisplay: "2026-07-23 11:20",
        episodeCount: 25,
        outcome: "중단(디스크)",
      },
    ],
    unacked: {
      count: 2,
      highestSeverity: "WARN",
    },
    activeErrorCodes: [],
  };
}

export function defaultDashboardSource(): DashboardSource {
  return { load: defaultDashboardData };
}
