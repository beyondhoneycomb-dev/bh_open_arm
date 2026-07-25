// Generic, token-free scanning primitives for the completion audit. This module
// holds NO forbidden literal (no reconnect symbol, no connect() call form, no
// external-origin URL): those pattern definitions live in the *.test.ts files that
// drive these primitives, exactly as every existing static-scan in this codebase
// keeps its patterns in test files (config/airgap.test.ts, mode/invariants.test.ts,
// screens/*/staticChecks.test.ts). Keeping this module pattern-free is what lets the
// GUI-wide CG-G-00a / CG-G-04a scans read the audit source without flagging the
// auditor's own detection logic.

import type { AuditViolation, NamedPattern, ScannedSource } from "./types";

// Hosts that are not an external origin: the backend on this machine and the XML/SVG
// namespace identifiers a renderer never fetches. The same allowlist config/airgap.ts
// uses; anything else with a scheme://host is a CDN/font/telemetry fetch (CG-5-04c).
export const DEFAULT_ALLOWED_HOSTS: ReadonlySet<string> = new Set([
  "localhost",
  "127.0.0.1",
  "www.w3.org",
]);

// Strip block and line comments (and HTML comments) before scanning. A forbidden
// token named in a comment documents an invariant; it is not shipped and not run.
// The `://` guard keeps a URL inside a code string from being read as a line comment.
export function stripComments(path: string, text: string): string {
  let out = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/<!--[\s\S]*?-->/g, "");
  if (/\.(ts|tsx|js|mjs)$/.test(path)) {
    out = out.replace(/(?<!:)\/\/.*$/gm, "");
  }
  return out;
}

// Report every source whose comment-free code matches any pattern. Used by the
// reconnect (CG-5-04d) and mode-switch (CG-5-04e) scans, whose patterns carry the
// forbidden tokens and therefore live in their test files.
export function scanForPatterns(
  sources: readonly ScannedSource[],
  patterns: readonly NamedPattern[],
  check: string,
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  for (const source of sources) {
    for (const named of patterns) {
      const match = named.pattern.exec(source.code);
      if (match) {
        violations.push({
          check,
          where: source.path,
          detail: `${named.label}: ${match[0]}`,
        });
      }
    }
  }
  return violations;
}

// Extract the host of every http(s) URL literal in a source's code. The regex form
// `https?://` does not itself match this literal (after "https" comes "?" here, not
// ":"), so this scanner does not flag its own source.
const URL_PATTERN = /https?:\/\/([a-zA-Z0-9.-]+)/g;

// Report every external-origin URL literal (CG-5-04c air-gap). A host not in the
// allowlist is a CDN/font/mesh/telemetry fetch that breaks on an isolated network.
export function findDisallowedUrls(
  sources: readonly ScannedSource[],
  allowedHosts: ReadonlySet<string> = DEFAULT_ALLOWED_HOSTS,
): AuditViolation[] {
  const violations: AuditViolation[] = [];
  for (const source of sources) {
    for (const match of source.code.matchAll(URL_PATTERN)) {
      const host = match[1];
      if (!allowedHosts.has(host)) {
        violations.push({
          check: "CG-5-04c",
          where: source.path,
          detail: `external-origin URL: ${match[0]}`,
        });
      }
    }
  }
  return violations;
}

// Report an off-origin <script>/<link> tag in an HTML document (CG-5-04c). A CDN
// script or stylesheet tag defeats the air-gap even when no bare URL literal is
// scanned as source.
export function findOffOriginTags(htmlPath: string, html: string): AuditViolation[] {
  const tag = /<(?:script|link)\b[^>]*(?:src|href)\s*=\s*["']https?:\/\/[^"']+["']/i;
  const match = tag.exec(html);
  return match
    ? [{ check: "CG-5-04c", where: htmlPath, detail: `off-origin tag: ${match[0]}` }]
    : [];
}
