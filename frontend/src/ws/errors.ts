// CTR-ERR@v1, mirrored for the browser. The single WebSocket surfaces backend
// faults as an error envelope wrapping a registered `OA-*` code; this module
// holds the code grammar and the four severity levels so the browser recognises
// and never invents a code. `errors.contract.test.ts` reads the frozen
// `contracts/errors/error_registry.yaml` and asserts this grammar, the severity
// set, and the closed domain set all agree with it (CR-2 staleness catch).

// OA-<domain>-<3 chars>. The last group is hex because OA-MOT mirrors the Damiao
// ERR nibble (008..00E), so 00A..00E are valid code numbers, not typos.
export const OA_CODE_PATTERN = /^OA-[A-Z]+-[0-9A-F]{3}$/;

// The four fixed severity levels (diagnostic_msgs semantics). A value outside
// this set is not a CTR-ERR@v1 severity.
export const SEVERITY_LEVELS = {
  OK: 0,
  WARN: 1,
  ERROR: 2,
  STALE: 3,
} as const;
export type SeverityName = keyof typeof SEVERITY_LEVELS;
export const SEVERITY_NAMES = Object.keys(SEVERITY_LEVELS) as SeverityName[];

// The closed set of domain prefixes. A code outside these is rejected; adding a
// domain is a CTR-ERR@v(n+1) bump, never an in-place edit.
export const OA_DOMAINS = [
  "OA-CAN",
  "OA-MOT",
  "OA-CTL",
  "OA-CAM",
  "OA-TEL",
  "OA-IK",
  "OA-SYS",
  "OA-INF",
  "OA-DAT",
  "OA-ZRO",
] as const;
export type OaDomain = (typeof OA_DOMAINS)[number];

export function isOaCode(value: unknown): value is string {
  return typeof value === "string" && OA_CODE_PATTERN.test(value);
}

export function isSeverityName(value: unknown): value is SeverityName {
  return typeof value === "string" && value in SEVERITY_LEVELS;
}

export function oaDomainOf(code: string): OaDomain | null {
  const match = /^(OA-[A-Z]+)-[0-9A-F]{3}$/.exec(code);
  if (!match) {
    return null;
  }
  const domain = match[1];
  return (OA_DOMAINS as readonly string[]).includes(domain) ? (domain as OaDomain) : null;
}

// One CTR-ERR@v1 error, wrapped identically for every surface: a registered code,
// a human reason, and the code's fixed severity.
export interface ErrorEnvelope {
  code: string;
  reason: string;
  severity: SeverityName;
}

export function isErrorEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null) {
    return false;
  }
  const candidate = value as Record<string, unknown>;
  return (
    isOaCode(candidate.code) &&
    typeof candidate.reason === "string" &&
    isSeverityName(candidate.severity)
  );
}
