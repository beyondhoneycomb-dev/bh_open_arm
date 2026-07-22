// The static-scan gates for WP-G-01. These read the ws source tree as text and
// assert structural invariants that a runtime test cannot: no backend-Robot
// re-attach symbol (CG-G-01d), decode only on the worker side of the boundary
// (CG-G-01f), exactly one realtime transport with no parallel stack (single-WS),
// and no hardcoded instrumentation count/channel (CG-G-01e static). Comments are
// stripped first, so prose that names the forbidden concepts to explain the
// invariants does not trip the scan.

import { readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const WS_DIR = dirname(fileURLToPath(import.meta.url));

function isTestFile(name: string): boolean {
  return /\.test\.ts$/.test(name);
}

function isWorkerFile(name: string): boolean {
  return /\.worker\.ts$/.test(name);
}

function productionFiles(): string[] {
  return readdirSync(WS_DIR)
    .filter((name) => name.endsWith(".ts") && !isTestFile(name))
    .map((name) => join(WS_DIR, name));
}

function stripComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//g, "").replace(/(?<!:)\/\/.*$/gm, "");
}

function readStripped(path: string): string {
  return stripComments(readFileSync(path, "utf-8"));
}

describe("CG-G-01d no backend-Robot re-attach symbol in GUI code", () => {
  it("names no reconnect / connect / disconnect symbol in production source", () => {
    const forbidden: RegExp[] = [/\breconnect\b/i, /\bdisconnect\b/i, /\bconnect\b/, /재연결/];
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      const text = readStripped(path);
      for (const pattern of forbidden) {
        if (pattern.test(text)) {
          offenders.push(`${path}: ${pattern}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("CG-G-01f zero main-thread decode (Web Worker boundary)", () => {
  it("imports the decoder only from a .worker.ts file", () => {
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      if (isWorkerFile(path)) {
        continue;
      }
      if (/from\s+["']\.\/decoder["']/.test(readStripped(path))) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("calls decodeFrame only in the decoder definition and the worker", () => {
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      const name = path.split("/").pop() ?? "";
      if (isWorkerFile(path) || name === "decoder.ts") {
        continue;
      }
      if (/\bdecodeFrame\s*\(/.test(readStripped(path))) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("single realtime WebSocket, no parallel stack (D-2)", () => {
  it("instantiates exactly one WebSocket in the whole ws tree", () => {
    let count = 0;
    for (const path of productionFiles()) {
      count += (readStripped(path).match(/new\s+WebSocket\s*\(/g) ?? []).length;
    }
    expect(count).toBe(1);
  });

  it("imports no webrtc / foxglove / rosbridge / grpc-web / socket.io stack", () => {
    const forbiddenImport = /from\s+["'][^"']*(webrtc|foxglove|rosbridge|grpc-web|socket\.io)[^"']*["']/;
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      if (forbiddenImport.test(readStripped(path))) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("opens no alternative realtime transport (RTCPeerConnection / EventSource)", () => {
    const forbidden = /new\s+(RTCPeerConnection|EventSource)\s*\(/;
    const offenders: string[] = [];
    for (const path of productionFiles()) {
      if (forbidden.test(readStripped(path))) {
        offenders.push(path);
      }
    }
    expect(offenders).toEqual([]);
  });
});

describe("CG-G-01e static: the meter hardcodes no instrumentation count or channel", () => {
  it("the stream meter derives its targets from inputs, with no baked-in count or key", () => {
    const meter = readStripped(join(WS_DIR, "streamMeter.ts"));
    // No observation dimension baked in (48 bimanual / 24 single-arm).
    expect(meter).not.toMatch(/\b(48|24)\b/);
    // No hardcoded observation channel-name string literal.
    expect(meter).not.toMatch(/["']observation\./);
  });
});
