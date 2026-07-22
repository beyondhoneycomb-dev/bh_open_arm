// Diagnostic-bundle completeness (CG-G-S13c, CG-G-S13e). FR-OPS-023 enumerates
// the contents of the bundle and 13 §2.7 forbids cherry-picking: EVERY item must
// be present, one missing BLOCKS generation. This module mirrors that required
// set so the browser can enforce completeness; `diagnosticBundle.test.tsx` reads
// the frozen FR-OPS-023 line from docs/spec/14 and asserts every `specPhrase`
// still appears there, so dropping an item or a spec revision fails the lane
// rather than silently shrinking the bundle. `specPhrase` is the anchor the drift
// guard matches; it is not shown to the user.

import type { BundleManifest } from "./types";

export interface DiagnosticItemSpec {
  id: string;
  labelKo: string;
  specPhrase: string;
}

// The FR-OPS-023 contents, in document order. Each `specPhrase` is a verbatim
// substring of the FR-OPS-023 requirement text (docs/spec/14 §2 ops).
export const REQUIRED_DIAGNOSTIC_ITEMS: readonly DiagnosticItemSpec[] = [
  { id: "system_info", labelKo: "시스템 정보 (커널·PREEMPT_RT·chrt·어피니티·VmLck·Python)", specPhrase: "시스템 정보" },
  { id: "ip_link_stats", labelKo: "인터페이스별 링크 통계", specPhrase: "ip -details -statistics link show" },
  { id: "can_raw_bindings", labelKo: "CAN raw 바인딩 목록", specPhrase: "/proc/net/can/raw" },
  { id: "dependency_versions", labelKo: "의존성 버전 + git commit SHA", specPhrase: "의존성 버전" },
  { id: "structured_logs", labelKo: "최근 N분 구조화 로그", specPhrase: "구조화 로그" },
  { id: "diagnostic_snapshot", labelKo: "진단 스냅샷", specPhrase: "진단 스냅샷" },
  { id: "error_histogram", labelKo: "최근 에러 코드 히스토그램", specPhrase: "에러 코드 히스토그램" },
  { id: "active_profile", labelKo: "활성 프로파일·게인·리밋 전문", specPhrase: "활성 프로파일" },
  { id: "observation_state_index", labelKo: "observation.state 인덱스 매핑", specPhrase: "observation.state" },
  { id: "bound_port_map", labelKo: "실제 바인딩 포트 맵", specPhrase: "실제 바인딩 포트 맵" },
];

// The required item ids, for set membership tests.
export const REQUIRED_ITEM_IDS: readonly string[] = REQUIRED_DIAGNOSTIC_ITEMS.map((item) => item.id);

// Which required items the manifest omits. Any non-empty result BLOCKS the bundle.
export function missingRequiredItems(manifest: BundleManifest): string[] {
  const included = new Set(manifest.includedItemIds);
  return REQUIRED_DIAGNOSTIC_ITEMS.filter((item) => !included.has(item.id)).map((item) => item.id);
}

export function bundleIsComplete(manifest: BundleManifest): boolean {
  return missingRequiredItems(manifest).length === 0;
}

// Generation is blocked whenever any FR-OPS-023 item is missing (no cherry-pick).
export function bundleGenerationBlocked(manifest: BundleManifest): boolean {
  return !bundleIsComplete(manifest);
}

// Video and personal data are opt-in and default OFF (CG-G-S13e). These are the
// defaults a fresh bundle selection starts from; the user turns them on knowingly.
export const DEFAULT_INCLUDE_VIDEO = false;
export const DEFAULT_INCLUDE_PII = false;

export interface BundlePrivacySelections {
  includeVideo: boolean;
  includePii: boolean;
}

export function defaultPrivacySelections(): BundlePrivacySelections {
  return { includeVideo: DEFAULT_INCLUDE_VIDEO, includePii: DEFAULT_INCLUDE_PII };
}
