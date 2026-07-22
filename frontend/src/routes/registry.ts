// Canonical route inventory (FR-GUI-002, CG-G-00b). This table is the shell's
// frozen contract: exactly the 13 screens of 13 §2.6 plus the shared 3D viewport
// route (/viewport). The shell adds and removes no screens — a diff against 13
// §2.6 must be zero. Sibling screen WPs (WP-G-S01..S13) and the viewport WP
// (WP-G-02) fill each route's content; they do not change this set.

import type { DomainCode, DomainSpecRef } from "../config/domainSpec";
import { getDomainSpecs } from "../config/domainSpec";

export type ScreenId =
  | "S-01"
  | "S-02"
  | "S-03"
  | "S-04"
  | "S-05"
  | "S-06"
  | "S-07"
  | "S-08"
  | "S-09"
  | "S-10"
  | "S-11"
  | "S-12"
  | "S-13";

export interface ScreenDescriptor {
  id: ScreenId;
  title: string;
  // Web route paths for this screen (13 §2.6). S-02 owns two (/connection,
  // /home-zero); every other screen owns one.
  paths: readonly string[];
  domainCodes: readonly DomainCode[];
}

// Ordered exactly as 13 §2.6 lists S-01..S-13.
export const SCREENS: readonly ScreenDescriptor[] = [
  { id: "S-01", title: "대시보드", paths: ["/"], domainCodes: ["SYS", "OPS", "NFR"] },
  {
    id: "S-02",
    title: "로봇 연결",
    paths: ["/connection", "/home-zero"],
    domainCodes: ["CON"],
  },
  { id: "S-03", title: "모터 설정", paths: ["/motors"], domainCodes: ["MOT"] },
  { id: "S-04", title: "수동 동작", paths: ["/manual"], domainCodes: ["MAN"] },
  { id: "S-05", title: "텔레옵", paths: ["/teleop"], domainCodes: ["TEL"] },
  { id: "S-06", title: "카메라", paths: ["/cameras"], domainCodes: ["CAM"] },
  { id: "S-07", title: "데이터 수집", paths: ["/collect"], domainCodes: ["REC"] },
  { id: "S-08", title: "데이터셋", paths: ["/datasets"], domainCodes: ["DAT"] },
  { id: "S-09", title: "시뮬레이션", paths: ["/sim"], domainCodes: ["SIM"] },
  { id: "S-10", title: "학습", paths: ["/training"], domainCodes: ["TRN"] },
  { id: "S-11", title: "추론/평가", paths: ["/inference"], domainCodes: ["INF"] },
  { id: "S-12", title: "충돌·안전", paths: ["/safety"], domainCodes: ["SAF"] },
  { id: "S-13", title: "시스템/로그", paths: ["/system"], domainCodes: ["OPS"] },
];

// The shared 3D viewport is a standalone route as well as an embedded component
// (FR-GUI-003). It is not a screen in 13 §2.6, so it is tracked separately and
// is the one route the shell adds beyond the 13-screen inventory.
export const VIEWPORT_PATH = "/viewport";

export function screenById(id: ScreenId): ScreenDescriptor {
  const found = SCREENS.find((screen) => screen.id === id);
  if (!found) {
    throw new Error(`unknown screen id: ${id}`);
  }
  return found;
}

// Every screen route path, in inventory order. S-02 contributes two.
export function screenPaths(): string[] {
  return SCREENS.flatMap((screen) => [...screen.paths]);
}

// Every route the shell mounts: all screen paths plus the viewport route.
export function allRoutePaths(): string[] {
  return [...screenPaths(), VIEWPORT_PATH];
}

// Resolve a screen's domain-spec references so the screen can query which
// domain specification(s) it implements (CG-G-00c).
export function domainSpecsForScreen(id: ScreenId): DomainSpecRef[] {
  return getDomainSpecs(screenById(id).domainCodes);
}
