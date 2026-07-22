// The envelope decoder: raw text/binary WS messages -> typed decoded frames. This
// logic runs ONLY inside the decode worker (decode.worker.ts); the main-thread
// client posts raw frames to the worker and receives decoded frames back, so no
// decode work ever runs on the main thread (CG-G-01f). It fabricates no OA-* code
// on failure — an un-parseable frame is a browser-side malformed event.
//
// Binary camera framing (this GUI's synthetic-fixture layout):
//   [tag length: uint16 big-endian][tag: utf-8 `<slot>:<channel>`][image bytes]
// The `<slot>:<channel>` tag GRAMMAR is the frozen CTR-PRIM@v1 one; only the byte
// layout that carries it is the fixture's.

import { isErrorEnvelope, type ErrorEnvelope, type SeverityName } from "./errors";
import { FRAME_TABLE, isWsFrameType, parseCameraFrameTag } from "./envelope";
import type { DecodedFrame, RawFrame } from "./types";

const TAG_LENGTH_BYTES = 2;

function malformed(reason: string): DecodedFrame {
  return { payload: "malformed", reason };
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function decodeText(text: string): DecodedFrame {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return malformed("text frame is not valid JSON");
  }
  if (!isPlainObject(parsed)) {
    return malformed("text frame is not a JSON object");
  }
  if (isErrorEnvelope(parsed)) {
    const envelope: ErrorEnvelope = {
      code: parsed.code as string,
      reason: parsed.reason as string,
      severity: parsed.severity as SeverityName,
    };
    return { payload: "error", error: envelope };
  }
  const frameType = parsed.type;
  if (!isWsFrameType(frameType)) {
    return malformed("text frame carries no known 'type'");
  }
  if (FRAME_TABLE[frameType].payload !== "text") {
    return malformed(`frame '${frameType}' is not a text frame`);
  }
  return { payload: "text", frameType, body: parsed };
}

function decodeBinary(bytes: ArrayBuffer): DecodedFrame {
  if (bytes.byteLength < TAG_LENGTH_BYTES) {
    return malformed("binary frame shorter than its tag-length prefix");
  }
  const view = new DataView(bytes);
  const tagLength = view.getUint16(0, false);
  const tagEnd = TAG_LENGTH_BYTES + tagLength;
  if (tagLength === 0 || tagEnd > bytes.byteLength) {
    return malformed("binary frame tag length is out of range");
  }
  const tag = new TextDecoder().decode(new Uint8Array(bytes, TAG_LENGTH_BYTES, tagLength));
  const parsedTag = parseCameraFrameTag(tag);
  if (!parsedTag) {
    return malformed(`binary frame tag '${tag}' is not a '<slot>:<channel>' camera tag`);
  }
  return {
    payload: "binary",
    frameType: "camera",
    slot: parsedTag.slot,
    channel: parsedTag.channel,
    // Copy out so the decoded frame does not retain the whole transport buffer.
    bytes: new Uint8Array(bytes.slice(tagEnd)),
  };
}

// Decode one raw frame. Total function: it always returns a DecodedFrame and never
// throws, so a single bad frame cannot break the decode worker.
export function decodeFrame(raw: RawFrame): DecodedFrame {
  return raw.kind === "text" ? decodeText(raw.text) : decodeBinary(raw.bytes);
}
