// The consume-the-contract proof for S-08. The screen resolves channels and their
// units through the CTR-REC@v1 convention (.pos->deg, .vel->deg/s, .torque->Nm), which
// the backend viewer mirrors from info.json name suffixes in
// backend/dataset/viewer/constants.py. This test reads that backend constants file and
// asserts the browser mirror equals it — so a convention change fails the lane (CR-2
// staleness) rather than letting the screen drift. It also asserts the browser carries
// no observation.effort notion, matching the backend where that key does not exist.

import { existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import {
  POSITION_SUFFIX,
  POSITION_UNIT,
  SUFFIX_UNITS,
  TORQUE_SUFFIX,
  TORQUE_UNIT,
  VELOCITY_SUFFIX,
  VELOCITY_UNIT,
} from "./channels";

function findRepoRoot(): string {
  let dir = dirname(fileURLToPath(import.meta.url));
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
  throw new Error("could not locate repository root");
}

const REPO_ROOT = findRepoRoot();

function readText(relativePath: string): string {
  return readFileSync(join(REPO_ROOT, relativePath), "utf-8");
}

function pyConst(text: string, name: string): string {
  const match = new RegExp(`${name}\\s*=\\s*"([^"]*)"`).exec(text);
  expect(match, `backend constant ${name} not found`).not.toBeNull();
  return match![1];
}

describe("CTR-REC@v1 unit convention mirrors the backend viewer (CG-G-S08g)", () => {
  const constants = readText("backend/dataset/viewer/constants.py");

  it("mirrors the per-suffix units", () => {
    expect(POSITION_SUFFIX).toBe(pyConst(constants, "POSITION_SUFFIX"));
    expect(VELOCITY_SUFFIX).toBe(pyConst(constants, "VELOCITY_SUFFIX"));
    expect(TORQUE_SUFFIX).toBe(pyConst(constants, "TORQUE_SUFFIX"));
    expect(POSITION_UNIT).toBe(pyConst(constants, "POSITION_UNIT"));
    expect(VELOCITY_UNIT).toBe(pyConst(constants, "VELOCITY_UNIT"));
    expect(TORQUE_UNIT).toBe(pyConst(constants, "TORQUE_UNIT"));
  });

  it("mirrors the full suffix->unit map with the same three entries", () => {
    const mirror = Object.fromEntries(SUFFIX_UNITS);
    expect(mirror).toEqual({
      [pyConst(constants, "POSITION_SUFFIX")]: pyConst(constants, "POSITION_UNIT"),
      [pyConst(constants, "VELOCITY_SUFFIX")]: pyConst(constants, "VELOCITY_UNIT"),
      [pyConst(constants, "TORQUE_SUFFIX")]: pyConst(constants, "TORQUE_UNIT"),
    });
  });
});

describe("observation.effort does not exist in either surface (CG-G-S08b)", () => {
  it("is absent from the backend viewer package", () => {
    const channelsPy = readText("backend/dataset/viewer/channels.py");
    const constantsPy = readText("backend/dataset/viewer/constants.py");
    const signalsPy = readText("backend/dataset/viewer/signals.py");
    for (const body of [channelsPy, constantsPy, signalsPy]) {
      expect(body).not.toMatch(/observation\.effort/);
    }
  });

  it("carries no effort entry in the browser suffix map", () => {
    for (const [suffix] of SUFFIX_UNITS) {
      expect(suffix).not.toMatch(/effort/i);
    }
  });
});
