// Test-only support: resolve a path to a file at the repository root, so the
// contract-mirror tests can read the frozen backend contracts (contracts/**)
// they mirror. Imported only from *.test.ts files, so it never enters the built
// bundle. The root is found by walking up from this module until the directory
// that contains `contracts/` is reached, which keeps the tests independent of how
// deep under `frontend/src/global/` the caller sits.

import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

function findRepoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
  // The repo root is the first ancestor that has a `contracts` directory.
  for (let depth = 0; depth < 12; depth += 1) {
    if (existsSync(join(dir, "contracts")) && existsSync(join(dir, "frontend"))) {
      return dir;
    }
    const parent = resolve(dir, "..");
    if (parent === dir) {
      break;
    }
    dir = parent;
  }
  throw new Error("could not locate repository root from " + fileURLToPath(import.meta.url));
}

const REPO_ROOT = findRepoRoot();

export function repoFile(relativePath: string): string {
  return join(REPO_ROOT, relativePath);
}
