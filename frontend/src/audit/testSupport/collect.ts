// Test-only file collection for the completion audit. Imported solely from the
// audit's *.test.ts files (never from the app), so its node:fs use never enters the
// built bundle — the same arrangement global/testSupport/repoRoot.ts uses. It walks
// the committed tree and returns comment-stripped ScannedSource lists for the pure
// audit functions to judge. It holds no scan pattern and no forbidden token: it only
// reads files and strips their comments.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, extname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { stripComments } from "../scan";
import type { ScannedSource } from "../types";

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

// The frontend root is the first ancestor holding both index.html and src, so the
// helper does not depend on how deep under src/audit/testSupport it sits.
function findFrontendRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  for (let depth = 0; depth < 12; depth += 1) {
    try {
      if (statSync(join(dir, "index.html")).isFile() && statSync(join(dir, "src")).isDirectory()) {
        return dir;
      }
    } catch {
      // keep walking up
    }
    const parent = resolve(dir, "..");
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  throw new Error("could not locate frontend root from " + fileURLToPath(import.meta.url));
}

const FRONTEND_ROOT = findFrontendRoot();

export function frontendPath(relative: string): string {
  return join(FRONTEND_ROOT, relative);
}

// Walk a directory collecting shippable source files. Test files, the audit's own
// testSupport helpers, node_modules and dist are excluded — they are never in the
// built bundle, so scanning them would flag documentation and synthetic fixtures.
function collectFiles(dir: string, acc: string[]): string[] {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === "dist" || name === "testSupport") {
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

function toScanned(paths: readonly string[]): ScannedSource[] {
  return paths.map((path) => ({
    path,
    code: stripComments(path, readFileSync(path, "utf-8")),
  }));
}

// Every shipped SPA source: index.html, the src tree (minus tests/testSupport) and
// public assets. The corpus for the air-gap, reconnect and mode-switch scans.
export function shippedSpaSources(): ScannedSource[] {
  const files = [frontendPath("index.html")];
  collectFiles(frontendPath("src"), files);
  collectFiles(frontendPath("public"), files);
  return toScanned(files);
}

export function screenSubtreeSources(screenId: string): ScannedSource[] {
  return toScanned(collectFiles(frontendPath(join("src/screens", screenId)), []));
}

export function viewportSubtreeSources(): ScannedSource[] {
  return toScanned(collectFiles(frontendPath("src/viewport"), []));
}

// The screen directories that exist on disk, in sorted order (e.g. "S-01"..."S-13").
export function screenDirIds(): string[] {
  const root = frontendPath("src/screens");
  return readdirSync(root)
    .filter((name) => statSync(join(root, name)).isDirectory())
    .sort();
}

export function readHtml(relative: string): { path: string; html: string } {
  const path = frontendPath(relative);
  return { path, html: readFileSync(path, "utf-8") };
}
