// OA-* error-code lookup (CG-G-S13f). The canon is 14 §2.10, frozen as
// contracts/errors/error_registry.yaml (CTR-ERR@v1). S-13 authors no code table:
// the backend serves the registry and this module resolves a code against it,
// reusing the browser mirror of the CTR-ERR grammar (isValidErrorCode) rather
// than re-deriving it. A well-formed but unknown code and a malformed code both
// resolve to null so the view can tell "no such code" from "not a code".

import { SEVERITY_NAMES, isValidErrorCode, type SeverityName } from "../../global";
import type { ErrorRegistry, ErrorRegistryEntry } from "./types";

export function lookupError(registry: ErrorRegistry, code: string): ErrorRegistryEntry | null {
  if (!isValidErrorCode(code)) {
    return null;
  }
  return registry[code] ?? null;
}

// The severity name for a registry entry's numeric severity (OK/WARN/ERROR/STALE).
// Reuses the frozen CTR-ERR severity axis; an out-of-range value yields null so a
// bad registry payload is visible rather than mislabelled.
export function severityName(entry: ErrorRegistryEntry): SeverityName | null {
  return SEVERITY_NAMES[entry.severity] ?? null;
}

// Whether a typed query is even a candidate code, for input validation before a
// lookup is attempted.
export function isLookupCandidate(code: string): boolean {
  return isValidErrorCode(code);
}
