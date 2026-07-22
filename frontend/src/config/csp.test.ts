// CG-G-00a CSP manifest: the policy must block every external origin and the
// build must be able to inject it into index.html.

import { describe, expect, it } from "vitest";

import {
  CSP_DIRECTIVES,
  CSP_POLICY,
  injectCspIntoHtml,
  isExternalOriginToken,
  policyBlocksExternalOrigins,
  serializeCsp,
} from "./csp";

describe("CG-G-00a CSP manifest", () => {
  it("defaults to same-origin only", () => {
    expect(CSP_DIRECTIVES["default-src"]).toEqual(["'self'"]);
  });

  it("names no external origin in any directive", () => {
    expect(policyBlocksExternalOrigins(CSP_DIRECTIVES)).toBe(true);
  });

  it("classifies a CDN host as external and self/none/data/blob as not", () => {
    expect(isExternalOriginToken("https://cdn.example.com")).toBe(true);
    expect(isExternalOriginToken("*.example.com")).toBe(true);
    expect(isExternalOriginToken("'self'")).toBe(false);
    expect(isExternalOriginToken("'none'")).toBe(false);
    expect(isExternalOriginToken("data:")).toBe(false);
    expect(isExternalOriginToken("blob:")).toBe(false);
  });

  it("forbids inline script and plaintext external connect", () => {
    expect(CSP_DIRECTIVES["script-src"]).not.toContain("'unsafe-inline'");
    expect(CSP_DIRECTIVES["connect-src"]).toEqual(["'self'"]);
  });

  it("serializes to a single-line policy string", () => {
    expect(serializeCsp(CSP_DIRECTIVES)).toBe(CSP_POLICY);
    expect(CSP_POLICY).toContain("default-src 'self'");
  });

  it("injects the policy into a built index.html, idempotently", () => {
    const html = "<!doctype html>\n<html>\n  <head>\n    <title>x</title>\n  </head>\n</html>";
    const once = injectCspIntoHtml(html);
    expect(once).toContain('http-equiv="Content-Security-Policy"');
    expect(once).toContain(CSP_POLICY);
    expect(injectCspIntoHtml(once)).toBe(once);
  });

  it("injects even when a comment merely names the policy", () => {
    const html =
      "<!doctype html>\n<html>\n  <head>\n    <!-- Content-Security-Policy is build-injected -->\n    <title>x</title>\n  </head>\n</html>";
    const injected = injectCspIntoHtml(html);
    expect(injected).toContain('http-equiv="Content-Security-Policy"');
    expect(injected).toContain(CSP_POLICY);
  });
});
