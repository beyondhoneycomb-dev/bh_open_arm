// The 13 §2.6 screen-inventory canon, transcribed straight from the spec table as
// the audit's independent ground truth. It is deliberately NOT derived from
// src/routes/registry.ts: CG-5-04a diffs the committed registry against this canon,
// and a canon read from the very thing under test would prove nothing. This mirrors
// how routes/registry.test.ts keeps its own EXPECTED transcription.
//
// `viewportCell` holds the verbatim "3D viewport" column text for the row (canon
// data, so its Korean is preserved); `tier` classifies that text into the embed
// permission the row grants (CG-5-04b):
//   - none        : the "no viewport" cell — the screen must embed no shared viewport
//                   (S-10, S-13)
//   - read_only   : reduced / pose-confirm / limit / frustum / auxiliary / replay — may
//                   show the viewport but never wire it as a command surface
//                   (S-01..S-03, S-06..S-08)
//   - interactive : the primary control/edit surface (S-04, S-05, S-09, S-11, S-12)

export type ViewportTier = "none" | "read_only" | "interactive";

export interface ScreenInventoryRow {
  id: string;
  paths: readonly string[];
  viewportCell: string;
  tier: ViewportTier;
}

// S-01..S-13 in 13 §2.6 order. S-02 owns two routes; every other screen owns one.
export const SCREEN_INVENTORY: readonly ScreenInventoryRow[] = [
  { id: "S-01", paths: ["/"], viewportCell: "축소(읽기전용)", tier: "read_only" },
  {
    id: "S-02",
    paths: ["/connection", "/home-zero"],
    viewportCell: "연결 후 자세 확인",
    tier: "read_only",
  },
  { id: "S-03", paths: ["/motors"], viewportCell: "리밋 시각화", tier: "read_only" },
  { id: "S-04", paths: ["/manual"], viewportCell: "주 화면", tier: "interactive" },
  {
    id: "S-05",
    paths: ["/teleop"],
    viewportCell: "주 화면(리더 vs 팔로워)",
    tier: "interactive",
  },
  { id: "S-06", paths: ["/cameras"], viewportCell: "프러스텀 연동", tier: "read_only" },
  { id: "S-07", paths: ["/collect"], viewportCell: "보조", tier: "read_only" },
  { id: "S-08", paths: ["/datasets"], viewportCell: "리플레이", tier: "read_only" },
  {
    id: "S-09",
    paths: ["/sim"],
    viewportCell: "주 화면(sim vs real)",
    tier: "interactive",
  },
  { id: "S-10", paths: ["/training"], viewportCell: "없음", tier: "none" },
  {
    id: "S-11",
    paths: ["/inference"],
    viewportCell: "주 화면(정책 목표 vs 현재)",
    tier: "interactive",
  },
  {
    id: "S-12",
    paths: ["/safety"],
    viewportCell: "주 화면(편집 대상)",
    tier: "interactive",
  },
  { id: "S-13", paths: ["/system"], viewportCell: "없음", tier: "none" },
];

// The one route the shell mounts beyond the 13 screens: the standalone /viewport
// (FR-GUI-003). It is not a §2.6 screen, so it is the single permitted extra route.
export const VIEWPORT_ROUTE = "/viewport";

export function inventoryRow(id: string): ScreenInventoryRow | undefined {
  return SCREEN_INVENTORY.find((row) => row.id === id);
}

export function canonScreenIds(): string[] {
  return SCREEN_INVENTORY.map((row) => row.id);
}

export function canonScreenPaths(): string[] {
  return SCREEN_INVENTORY.flatMap((row) => [...row.paths]);
}
