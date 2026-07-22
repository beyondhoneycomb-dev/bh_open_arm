// The public health projection (CG-G-04g, FR-GUI-092). The public health endpoint
// must NOT leak the control holder or the active profile — CTR-WS@v1
// health.forbidden_fields = ["control_holder", "active_profile"]. `PublicHealth`
// has no slot for either field, so a component cannot render what the type cannot
// carry, and `projectPublicHealth` copies only the allowlisted fields — a backend
// that mistakenly included a forbidden field cannot smuggle it through this
// projection into the UI.

// The fields CTR-WS forbids from the public health payload. Kept as data so the
// projection and its test read the same list.
export const FORBIDDEN_HEALTH_FIELDS = ["control_holder", "active_profile"] as const;

export interface PublicHealth {
  // Coarse liveness the public endpoint may expose. Deliberately excludes who
  // holds control and which profile is active.
  status: string;
  uptimeSeconds: number;
  canLinkUp: boolean;
}

function readString(raw: Record<string, unknown>, key: string, fallback: string): string {
  const value = raw[key];
  return typeof value === "string" ? value : fallback;
}

function readNumber(raw: Record<string, unknown>, key: string, fallback: number): number {
  const value = raw[key];
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function readBool(raw: Record<string, unknown>, key: string, fallback: boolean): boolean {
  const value = raw[key];
  return typeof value === "boolean" ? value : fallback;
}

// Project a raw health document to the public view, copying only allowlisted
// fields. Forbidden fields present in `raw` are dropped, never carried across.
export function projectPublicHealth(raw: Record<string, unknown>): PublicHealth {
  return {
    status: readString(raw, "status", "unknown"),
    uptimeSeconds: readNumber(raw, "uptimeSeconds", 0),
    canLinkUp: readBool(raw, "canLinkUp", false),
  };
}
