// The decode worker: the only place the envelope decoder runs. It receives raw
// frames posted by the main-thread WsClient and posts decoded frames back, so the
// main thread performs zero decode work (CG-G-01f). Binary payloads are
// transferred (zero-copy) back and forth to keep camera frames off the heap path.

import { decodeFrame } from "./decoder";
import type { DecodedFrame, RawFrame } from "./types";

const workerScope = self as unknown as {
  onmessage: ((event: { data: RawFrame }) => void) | null;
  postMessage(message: DecodedFrame, transfer?: Transferable[]): void;
};

workerScope.onmessage = (event) => {
  const decoded = decodeFrame(event.data);
  if (decoded.payload === "binary") {
    workerScope.postMessage(decoded, [decoded.bytes.buffer]);
  } else {
    workerScope.postMessage(decoded);
  }
};
