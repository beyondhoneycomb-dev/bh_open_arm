// Shared shapes for the WP-5-04 GUI completion audit. The audit is the cumulative,
// cross-screen final pass over the committed 13-screen tree (02c §4.4): it BUILDS NO
// SCREEN and EDITS NO SCREEN — it only reads the committed sources and the frozen
// route/mode canons and reports where they diverge from 13 §2.6 and the SPINE §2-2
// invariants. Every check is a pure function over inputs (scanned sources or canon
// data) so the same function proves zero findings over the real tree AND genuinely
// fires on a synthetic violation.

// One audit finding. `check` is the CG id it belongs to, `where` is the offending
// path or screen id, `detail` is the human-readable reason. A check returns an empty
// array when it holds.
export interface AuditViolation {
  check: string;
  where: string;
  detail: string;
}

// A source file after comment stripping, ready to scan. `path` is kept for the
// finding location; `code` is the comment-free text so a token named only in a
// comment (documentation) is never mistaken for a runtime occurrence — Vite drops
// comments from the built bundle, so a token inside one is neither shipped nor run.
export interface ScannedSource {
  path: string;
  code: string;
}

// A labelled scan pattern. The label names what the pattern detects so a finding
// reads as a reason, not a bare regex.
export interface NamedPattern {
  label: string;
  pattern: RegExp;
}
