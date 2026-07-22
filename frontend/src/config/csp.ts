// Air-gap CSP manifest (CG-G-00a, FR-GUI-008). Canonical source of the Content
// Security Policy the built bundle enforces. The invariant every directive must
// hold: no external origin. Only the page's own origin ('self'), the safe
// schemes data:/blob: (same-document, not a remote host) and CSP keywords are
// permitted. A single CDN/font/telemetry host here would mean the SPA fails to
// load on an isolated network, so `policyBlocksExternalOrigins` is asserted in
// test and the policy is injected into the built index.html by vite.config.ts.

export type CspDirectives = Readonly<Record<string, readonly string[]>>;

// Non-origin CSP source tokens: keywords and safe schemes. Everything else in a
// directive is treated as a host and rejected by `policyBlocksExternalOrigins`.
const NON_ORIGIN_TOKENS: ReadonlySet<string> = new Set([
  "'self'",
  "'none'",
  "'unsafe-inline'",
  "'wasm-unsafe-eval'",
  "data:",
  "blob:",
]);

// 'unsafe-inline' appears only for style-src: a bundled build and future 3D/
// telemetry libraries inject style attributes, and inline styles cannot reach an
// external origin. Scripts get no such relaxation. wss/ws to the page origin are
// already covered by 'self' (CSP3), so the single realtime WebSocket needs no
// host entry. worker-src blob: is for the WP-G-01 decode Worker.
export const CSP_DIRECTIVES: CspDirectives = {
  "default-src": ["'self'"],
  "script-src": ["'self'"],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:"],
  "font-src": ["'self'"],
  "connect-src": ["'self'"],
  "worker-src": ["'self'", "blob:"],
  "media-src": ["'self'", "blob:"],
  "object-src": ["'none'"],
  "base-uri": ["'self'"],
  "form-action": ["'self'"],
  "frame-ancestors": ["'none'"],
};

export function serializeCsp(directives: CspDirectives): string {
  return Object.entries(directives)
    .map(([name, sources]) => `${name} ${sources.join(" ")}`)
    .join("; ");
}

export const CSP_POLICY: string = serializeCsp(CSP_DIRECTIVES);

// A source token is an external origin when it is neither a known keyword/safe
// scheme nor a relative-only marker. Any host, scheme://host, or wildcard host
// (`*`, `https://cdn...`, `*.example.com`) counts as external.
export function isExternalOriginToken(token: string): boolean {
  if (NON_ORIGIN_TOKENS.has(token)) {
    return false;
  }
  return true;
}

export function policyBlocksExternalOrigins(directives: CspDirectives): boolean {
  return Object.values(directives).every((sources) =>
    sources.every((token) => !isExternalOriginToken(token)),
  );
}

const CSP_META_TAG = `<meta http-equiv="Content-Security-Policy" content="${CSP_POLICY}">`;

// Injected into the built index.html (production only, so dev HMR keeps its
// inline preamble). Idempotent: a document already carrying the enforcing meta
// tag is returned unchanged. The guard matches the tag's `http-equiv`, not the
// bare phrase, so a comment that merely names the policy does not suppress it.
const CSP_META_PRESENT = /http-equiv=["']?Content-Security-Policy/i;

export function injectCspIntoHtml(html: string): string {
  if (CSP_META_PRESENT.test(html)) {
    return html;
  }
  return html.replace(/<head>/i, `<head>\n    ${CSP_META_TAG}`);
}
