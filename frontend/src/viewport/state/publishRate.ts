// Telemetry publish-rate resolution (CG-G-02i). Default is 30 Hz; the hard cap is
// 60 Hz. A request above the cap is REJECTED, not clamped: silently clamping an
// over-configuration hides that the operator asked for a rate the platform will
// not sustain. An unset request resolves to the default; a non-positive or
// non-finite request is rejected as malformed.

import { PUBLISH_RATE_DEFAULT_HZ, PUBLISH_RATE_MAX_HZ } from "../constants";

export type PublishRateResult =
  | { readonly ok: true; readonly hz: number }
  | { readonly ok: false; readonly reason: string; readonly requested: number };

export function resolvePublishRate(requestedHz?: number): PublishRateResult {
  if (requestedHz === undefined) {
    return { ok: true, hz: PUBLISH_RATE_DEFAULT_HZ };
  }
  if (!Number.isFinite(requestedHz) || requestedHz <= 0) {
    return { ok: false, reason: "publish rate must be a positive number", requested: requestedHz };
  }
  if (requestedHz > PUBLISH_RATE_MAX_HZ) {
    return {
      ok: false,
      reason: `publish rate ${requestedHz} Hz exceeds the ${PUBLISH_RATE_MAX_HZ} Hz cap`,
      requested: requestedHz,
    };
  }
  return { ok: true, hz: requestedHz };
}
