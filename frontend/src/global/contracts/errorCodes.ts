// Browser-side mirror of the frozen CTR-ERR@v1 error-code contract, consumed by
// the notification center. The canon is the backend registry
// (contracts/errors/error_registry.yaml); the browser never authors codes, it
// only renders codes the backend emits over the WS. This module pins the two
// pieces the GUI reasons about — the 4-level severity and the closed domain set
// — so a drift from the frozen contract fails errorCodes.test.ts rather than
// silently mislabelling an alert. The GUI must not duplicate the full code table:
// that stays backend-owned and arrives at runtime.

// The 4 fixed severity levels (CTR-ERR@v1, 14 §2.10). Values are the contract:
// OK < WARN < ERROR on the diagnostic axis, STALE the staleness axis above ERROR.
// A const object rather than a TS enum keeps the numeric values explicit and
// isolatedModules-safe.
export const Severity = {
  OK: 0,
  WARN: 1,
  ERROR: 2,
  STALE: 3,
} as const;

export type SeverityName = keyof typeof Severity;
export type SeverityValue = (typeof Severity)[SeverityName];

export const SEVERITY_NAMES: readonly SeverityName[] = ["OK", "WARN", "ERROR", "STALE"];

// CG-G-03g / FR-GUI-066: an alert at ERROR or above holds its badge until the
// operator acknowledges it. STALE (value 3) sits above ERROR on the numeric axis
// and is a serious condition, so it holds too.
export const BADGE_HOLD_MIN_SEVERITY: SeverityValue = Severity.ERROR;

export function holdsBadgeUntilAck(severity: SeverityValue): boolean {
  return severity >= BADGE_HOLD_MIN_SEVERITY;
}

// The closed set of OA-* domain prefixes (CTR-ERR@v1). A code outside these is
// not a valid code; a new domain is a contract bump, never an in-place addition.
export const OA_DOMAINS: readonly string[] = [
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
];

// OA-<domain>-<3 hex>. The number group is hex because OA-MOT mirrors the Damiao
// ERR nibble (008..00E), so 00A..00E are valid, not typos (CTR-ERR@v1).
export const OA_CODE_PATTERN = /^OA-([A-Z]+)-([0-9A-F]{3})$/;

// Report whether a string is a well-formed code in one of the closed domains.
export function isValidErrorCode(code: string): boolean {
  const match = OA_CODE_PATTERN.exec(code);
  if (!match) {
    return false;
  }
  return OA_DOMAINS.includes(`OA-${match[1]}`);
}
