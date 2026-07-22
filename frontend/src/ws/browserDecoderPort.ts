// The production DecoderPort: a real Web Worker running the envelope decoder. It
// is wired only by the app entry (defaults.ts); the vitest lane injects a fake
// DecoderPort instead, so this module — and the Worker global it needs — never
// enters the test import graph.

import type { DecodedFrame, DecoderPort, RawFrame } from "./types";

class WorkerDecoderPort implements DecoderPort {
  private mWorker: Worker;
  private mHandler: ((frame: DecodedFrame) => void) | null;

  constructor(worker: Worker) {
    this.mWorker = worker;
    this.mHandler = null;
    this.mWorker.onmessage = (event: MessageEvent<DecodedFrame>) => {
      if (this.mHandler) {
        this.mHandler(event.data);
      }
    };
  }

  decode(raw: RawFrame): void {
    if (raw.kind === "binary") {
      this.mWorker.postMessage(raw, [raw.bytes]);
    } else {
      this.mWorker.postMessage(raw);
    }
  }

  onDecoded(handler: (frame: DecodedFrame) => void): void {
    this.mHandler = handler;
  }

  dispose(): void {
    this.mHandler = null;
    this.mWorker.terminate();
  }
}

// Build the Worker-backed decode port. The `new URL(..., import.meta.url)` form is
// what Vite bundles the worker from at build time — self-hosted, no external
// origin (CG-G-00a air-gap).
export function createBrowserDecoderPort(): DecoderPort {
  const worker = new Worker(new URL("./decode.worker.ts", import.meta.url), { type: "module" });
  return new WorkerDecoderPort(worker);
}
