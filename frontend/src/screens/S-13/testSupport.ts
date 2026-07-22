// Test-only loaders that pull S-13's canon from the frozen sources on disk so the
// lane consumes the real contracts, not values re-authored in the screen:
// contracts/errors/error_registry.yaml (CTR-ERR@v1, canon 14 §2.10) and the port
// tables of docs/spec/01 §2.17 + docs/spec/14 §2.1. Regex parsing keeps a YAML
// dependency out of the frontend, matching errors.contract.test.ts. Imported only
// by *.test.tsx; never part of the shipped bundle.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { CanonPortEntry, ErrorRegistry, ErrorRegistryEntry } from "./types";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");

export function repoFile(relativePath: string): string {
  return readFileSync(resolve(REPO_ROOT, relativePath), "utf-8");
}

function scalar(block: string, key: string): string {
  const quoted = new RegExp(`\\n\\s+${key}:\\s*"([^"]*)"`).exec(block);
  if (quoted) {
    return quoted[1];
  }
  const bare = new RegExp(`\\n\\s+${key}:\\s*([^\\n#]+)`).exec(block);
  return bare ? bare[1].trim() : "";
}

// Parse the frozen error registry into the wire shape the backend would serve.
export function loadErrorRegistry(): ErrorRegistry {
  const text = repoFile("contracts/errors/error_registry.yaml");
  const starts = [...text.matchAll(/\n\s+-\s+code:\s*(OA-[A-Z0-9-]+)/g)];
  const registry: ErrorRegistry = {};
  for (let index = 0; index < starts.length; index += 1) {
    const from = starts[index].index ?? 0;
    const to = index + 1 < starts.length ? (starts[index + 1].index ?? text.length) : text.length;
    const block = text.slice(from, to);
    const code = starts[index][1];
    const entry: ErrorRegistryEntry = {
      code,
      severity: Number(scalar(block, "severity")),
      messageKo: scalar(block, "message_ko"),
      messageEn: scalar(block, "message_en"),
      recoveryHint: scalar(block, "recovery_hint"),
      docUrl: scalar(block, "doc_url"),
      subsystem: scalar(block, "subsystem"),
    };
    registry[code] = entry;
  }
  return registry;
}

function pipeCells(line: string): string[] {
  return line
    .split("|")
    .slice(1, -1)
    .map((cell) => cell.replace(/\*\*/g, "").trim());
}

function portOf(cell: string): number | null {
  const match = /\b(\d{2,5})\b/.exec(cell);
  return match ? Number(match[1]) : null;
}

// Parse a component/protocol/port markdown table that begins after `heading`,
// taking those three columns. Used to reconstruct the port-map canon from the
// spec exactly as the backend would serve it.
function parsePortTable(text: string, heading: string): CanonPortEntry[] {
  const lines = text.split("\n");
  const start = lines.findIndex((line) => line.includes(heading));
  if (start < 0) {
    return [];
  }
  const entries: CanonPortEntry[] = [];
  let inRows = false;
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim().startsWith("|")) {
      if (inRows) {
        break;
      }
      continue;
    }
    if (/^\s*\|\s*-{2,}/.test(line) || line.includes("컴포넌트")) {
      inRows = true;
      continue;
    }
    if (!inRows) {
      continue;
    }
    const cells = pipeCells(line);
    if (cells.length < 3) {
      continue;
    }
    entries.push({ component: cells[0], protocol: cells[1], port: portOf(cells[2]) });
  }
  return entries;
}

// The port-map canon = union of 01 §2.17 + 14 §2.1 (13 §2.7). Deduped by
// component so a component named in both tables yields one canon row.
export function loadPortCanon(): CanonPortEntry[] {
  const fromArch = parsePortTable(repoFile("docs/spec/01-시스템-아키텍처.md"), "### 2.17 포트 맵");
  const fromOps = parsePortTable(
    repoFile("docs/spec/14-시스템-운영.md"),
    "프로세스·포트 맵 (운영이 감독해야 할 전부)",
  );
  const byComponent = new Map<string, CanonPortEntry>();
  for (const entry of [...fromArch, ...fromOps]) {
    if (!byComponent.has(entry.component)) {
      byComponent.set(entry.component, entry);
    }
  }
  return [...byComponent.values()];
}

// The verbatim FR-OPS-023 requirement text, for the diagnostic-bundle drift guard.
export function loadFrOps023Text(): string {
  const text = repoFile("docs/spec/14-시스템-운영.md");
  const line = text.split("\n").find((candidate) => candidate.includes("FR-OPS-023"));
  return line ?? "";
}
