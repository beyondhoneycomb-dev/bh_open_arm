// CG-G-00a (air-gap static scan) and CG-G-00e (no config canon in the browser).
// Scans the production source set — index.html plus every non-test source file —
// for external-origin URLs and for localStorage/sessionStorage persistence. Test
// files are excluded because they never enter the built bundle and legitimately
// contain URL and storage literals (this file included).

import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const FRONTEND_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");

// Not external origins: the backend on this machine (dev proxy) and the SVG/XML
// namespace URIs, which are identifiers a renderer never fetches. Anything else
// with a scheme://host is a CDN/font/telemetry fetch and fails air-gap.
const ALLOWED_HOSTS: ReadonlySet<string> = new Set(["localhost", "127.0.0.1", "www.w3.org"]);

const URL_PATTERN = /https?:\/\/([a-zA-Z0-9.-]+)/g;
const SCANNED_EXTENSIONS: ReadonlySet<string> = new Set([
  ".ts",
  ".tsx",
  ".css",
  ".html",
  ".svg",
  ".json",
]);

function isTestFile(path: string): boolean {
  return /\.test\.(ts|tsx)$/.test(path) || path.endsWith("test-setup.ts");
}

// Strip comments before scanning: comments are documentation (they explain the
// air-gap and no-localStorage invariants by naming them) and Vite removes them
// from the production bundle, so a URL or a storage word inside a comment is not
// a runtime fetch or a persisted canon. The `://` guard keeps `http://localhost`
// in a code string from being mistaken for a line comment.
function stripComments(path: string, text: string): string {
  let out = text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/<!--[\s\S]*?-->/g, "");
  if (/\.(ts|tsx|js|mjs)$/.test(path)) {
    out = out.replace(/(?<!:)\/\/.*$/gm, "");
  }
  return out;
}

function collectFiles(dir: string, acc: string[]): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist") {
      continue;
    }
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      collectFiles(full, acc);
    } else if (SCANNED_EXTENSIONS.has(extname(full)) && !isTestFile(full)) {
      acc.push(full);
    }
  }
  return acc;
}

function productionSources(): string[] {
  const files = [join(FRONTEND_ROOT, "index.html")];
  collectFiles(join(FRONTEND_ROOT, "src"), files);
  collectFiles(join(FRONTEND_ROOT, "public"), files);
  return files;
}

describe("CG-G-00a air-gap static scan", () => {
  it("names no external-origin URL in any production source", () => {
    const offenders: string[] = [];
    for (const file of productionSources()) {
      const text = stripComments(file, readFileSync(file, "utf-8"));
      for (const match of text.matchAll(URL_PATTERN)) {
        const host = match[1];
        if (!ALLOWED_HOSTS.has(host)) {
          offenders.push(`${file}: ${match[0]}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("has no CDN/link/script tag pointing off-origin in index.html", () => {
    const html = readFileSync(join(FRONTEND_ROOT, "index.html"), "utf-8");
    expect(html).not.toMatch(/<(script|link)[^>]+(src|href)=["']https?:\/\//i);
  });
});

describe("CG-G-00e config canon is not held in the browser", () => {
  it("never persists to localStorage or sessionStorage in production source", () => {
    const offenders: string[] = [];
    for (const file of productionSources()) {
      const text = stripComments(file, readFileSync(file, "utf-8"));
      if (/\blocalStorage\b/.test(text) || /\bsessionStorage\b/.test(text)) {
        offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });
});
