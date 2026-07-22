// The consume-the-frozen-contract proof for the S-03 ERR view. It reads the frozen
// contracts/errors/error_registry.yaml and asserts that (a) the browser's
// nibble→OA-MOT mirror equals the registry's damiao_err_nibble_map, and (b) every
// one of the seven fault codes the screen renders carries a non-empty recovery_hint
// in the registry. So "reuse the CTR-ERR registry" (CG-G-S03g) is enforced, not
// assumed: a registry edit to the nibble map or a dropped hint fails this test
// rather than letting the ERR view drift (CR-2 staleness). No YAML dependency is
// pulled in — the registry is read with a targeted line scan, as the foundation's
// errors.contract.test.ts does.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { MOT_FAULT_NIBBLES, motErrCodeForNibble } from "./motorDomain";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..", "..");
const registryText = readFileSync(
  resolve(REPO_ROOT, "contracts/errors/error_registry.yaml"),
  "utf-8",
);
const lines = registryText.split("\n");

// The nibble→code pairs declared under damiao_err_nibble_map.
function nibbleMapFromRegistry(): Record<string, string> {
  const start = lines.findIndex((line) => line.trim() === "damiao_err_nibble_map:");
  const map: Record<string, string> = {};
  let nibble: string | null = null;
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() !== "" && !/^\s/.test(line)) {
      break; // dedented back to a top-level key
    }
    const nibbleMatch = /^\s*-\s*nibble:\s*"([^"]+)"/.exec(line);
    if (nibbleMatch) {
      nibble = nibbleMatch[1].toUpperCase();
      continue;
    }
    const codeMatch = /^\s*code:\s*(OA-MOT-[0-9A-F]{3})/.exec(line);
    if (codeMatch && nibble) {
      map[nibble] = codeMatch[1];
      nibble = null;
    }
  }
  return map;
}

// The recovery_hint declared for a given code in the codes: block.
function recoveryHintForCode(code: string): string | null {
  const codeLine = lines.findIndex((line) => new RegExp(`^\\s*-\\s*code:\\s*${code}\\s*$`).test(line));
  if (codeLine < 0) {
    return null;
  }
  for (let index = codeLine + 1; index < lines.length; index += 1) {
    if (/^\s*-\s*code:\s*/.test(lines[index])) {
      break; // reached the next code entry
    }
    const hint = /^\s*recovery_hint:\s*"?(.+?)"?\s*$/.exec(lines[index]);
    if (hint) {
      return hint[1];
    }
  }
  return null;
}

describe("S-03 ERR mirror equals the frozen CTR-ERR registry", () => {
  const registryNibbleMap = nibbleMapFromRegistry();

  it("maps the seven fault nibbles exactly as the registry does", () => {
    for (const nibble of MOT_FAULT_NIBBLES) {
      expect(motErrCodeForNibble(nibble)).toBe(registryNibbleMap[nibble]);
    }
  });

  it("mirrors the same fault-nibble set the registry marks as motor faults", () => {
    // Registry fault nibbles = every mapped nibble except the normal states 0 and 1.
    const registryFaults = Object.keys(registryNibbleMap)
      .filter((nibble) => nibble !== "0" && nibble !== "1")
      .sort();
    expect(registryFaults).toEqual([...MOT_FAULT_NIBBLES].sort());
  });

  it("carries a non-empty recovery hint for every fault code the screen renders", () => {
    for (const nibble of MOT_FAULT_NIBBLES) {
      const code = motErrCodeForNibble(nibble) as string;
      const hint = recoveryHintForCode(code);
      expect(hint, code).not.toBeNull();
      expect((hint as string).length).toBeGreaterThan(0);
    }
  });
});
