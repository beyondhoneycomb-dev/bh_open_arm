// Domain-spec catalog (FR-GUI-002, CG-G-00c). Each screen is the window onto one
// or more domain specification documents; from any screen the shell can resolve
// which spec it implements and an address to query it. The shell does not hold
// the spec content — it holds the reference and a same-origin URL the backend
// serves the spec from.

import { SPEC_ENDPOINT_BASE } from "./endpoints";

// Domain codes as the screen inventory (13 §2.6) uses them.
export type DomainCode =
  | "SYS"
  | "OPS"
  | "NFR"
  | "CON"
  | "MOT"
  | "MAN"
  | "TEL"
  | "CAM"
  | "REC"
  | "DAT"
  | "SIM"
  | "TRN"
  | "INF"
  | "SAF";

export interface DomainSpecRef {
  code: DomainCode;
  // Spec document number as in docs/spec/ (e.g. "02" is robot connection).
  doc: string;
  title: string;
  // Same-origin address the backend serves the spec document from.
  specUrl: string;
}

interface DomainEntry {
  doc: string;
  title: string;
}

// One entry per domain code, each pointing at its docs/spec/ document.
const DOMAIN_CATALOG: Readonly<Record<DomainCode, DomainEntry>> = {
  SYS: { doc: "01", title: "시스템 아키텍처" },
  CON: { doc: "02", title: "로봇 연결 및 온보딩" },
  MOT: { doc: "03", title: "모터 설정" },
  MAN: { doc: "04", title: "수동 동작" },
  TEL: { doc: "05", title: "텔레오퍼레이션" },
  CAM: { doc: "06", title: "카메라 서브시스템" },
  REC: { doc: "07", title: "데이터 수집" },
  DAT: { doc: "08", title: "데이터셋 관리" },
  SIM: { doc: "09", title: "시뮬레이션" },
  TRN: { doc: "10", title: "학습" },
  INF: { doc: "11", title: "추론 및 평가" },
  SAF: { doc: "12", title: "충돌감지 및 안전" },
  OPS: { doc: "14", title: "시스템 운영" },
  NFR: { doc: "15", title: "비기능 요구사항" },
};

export function domainSpecUrl(doc: string): string {
  return `${SPEC_ENDPOINT_BASE}/${doc}`;
}

export function getDomainSpec(code: DomainCode): DomainSpecRef {
  const entry = DOMAIN_CATALOG[code];
  return { code, doc: entry.doc, title: entry.title, specUrl: domainSpecUrl(entry.doc) };
}

export function getDomainSpecs(codes: readonly DomainCode[]): DomainSpecRef[] {
  return codes.map(getDomainSpec);
}
