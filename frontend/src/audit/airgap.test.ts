// CG-5-04c — air-gap: zero external-origin requests across every shipped screen and
// foundation source. Real tree: no source names an off-allowlist http(s) host and
// index.html carries no off-origin <script>/<link>. Synthetic: a CDN fetch string and
// an off-origin tag both make the audit fire. A CDN/font/mesh fetch would make the SPA
// fail to load on an isolated network (FR-GUI-008).

import { describe, expect, it } from "vitest";

import { CSP_DIRECTIVES, policyBlocksExternalOrigins } from "../config/csp";
import { findDisallowedUrls, findOffOriginTags } from "./scan";
import { readHtml, shippedSpaSources } from "./testSupport/collect";

describe("CG-5-04c air-gap: 0 external-origin requests", () => {
  it("no shipped source names an external-origin URL", () => {
    expect(findDisallowedUrls(shippedSpaSources())).toEqual([]);
  });

  it("index.html carries no off-origin script/link tag", () => {
    const { path, html } = readHtml("index.html");
    expect(findOffOriginTags(path, html)).toEqual([]);
  });

  it("fires on a CDN fetch to an external host", () => {
    const findings = findDisallowedUrls([
      { path: "fake/x.ts", code: 'fetch("https://cdn.jsdelivr.net/three.min.js");' },
    ]);
    expect(findings.length).toBeGreaterThan(0);
  });

  it("fires on an external font URL", () => {
    const findings = findDisallowedUrls([
      { path: "fake/x.css", code: '@import url("https://fonts.googleapis.com/css?family=Inter");' },
    ]);
    expect(findings.length).toBeGreaterThan(0);
  });

  it("fires on an off-origin script tag", () => {
    const findings = findOffOriginTags(
      "fake/index.html",
      '<script src="https://cdn.example.com/a.js"></script>',
    );
    expect(findings.length).toBeGreaterThan(0);
  });

  it("does not fault the same-origin backend host", () => {
    const findings = findDisallowedUrls([
      { path: "fake/x.ts", code: 'const dev = "http://localhost:8000/ws";' },
    ]);
    expect(findings).toEqual([]);
  });

  // The runtime air-gap defense that complements the static scan: the committed CSP
  // (WP-G-00, read-only here) permits no external origin, so even a URL that slipped
  // past the scan cannot be fetched on the running page. This verifies the enforcement
  // mechanism exists and is correct — it is not, and does not claim to be, a live
  // network capture (unavailable AI-offline).
  it("the committed CSP policy blocks every external origin at runtime", () => {
    expect(policyBlocksExternalOrigins(CSP_DIRECTIVES)).toBe(true);
  });
});
