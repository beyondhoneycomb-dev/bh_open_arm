// Text/binary envelope decode against the synthetic 3A fixtures. This test file
// imports the decoder directly (a test file, never shipped), so the decode logic
// still lives only on the worker side of the boundary in production (CG-G-01f).

import { describe, expect, it } from "vitest";

import { decodeFrame } from "./decoder";
import {
  cameraRaw,
  errorEnvelopeFrame,
  leaseGrantFrame,
  telemetryFrame,
  textRaw,
} from "./synthetic";

describe("envelope decoder — text frames", () => {
  it("decodes a telemetry text frame to its typed body", () => {
    const decoded = decodeFrame(textRaw(telemetryFrame(1)));
    expect(decoded.payload).toBe("text");
    if (decoded.payload === "text") {
      expect(decoded.frameType).toBe("telemetry");
      expect(decoded.body.sequence).toBe(1);
    }
  });

  it("decodes a lease_grant text frame", () => {
    const grant = leaseGrantFrame({
      sessionId: "s1",
      generation: 2,
      sequence: 5,
      expiryMonoServer: 9999,
      issuedMonoClient: 10,
    });
    const decoded = decodeFrame(textRaw(grant));
    expect(decoded.payload).toBe("text");
    if (decoded.payload === "text") {
      expect(decoded.frameType).toBe("lease_grant");
      expect(decoded.body.lease_generation).toBe(2);
    }
  });

  it("decodes a server error envelope to an error frame", () => {
    const decoded = decodeFrame(textRaw(errorEnvelopeFrame("OA-TEL-001", "stream stalled", "STALE")));
    expect(decoded.payload).toBe("error");
    if (decoded.payload === "error") {
      expect(decoded.error.code).toBe("OA-TEL-001");
      expect(decoded.error.severity).toBe("STALE");
    }
  });

  it("flags non-JSON, unknown-type, and mistyped frames as malformed", () => {
    expect(decodeFrame({ kind: "text", text: "not json" }).payload).toBe("malformed");
    expect(decodeFrame({ kind: "text", text: JSON.stringify({ type: "nope" }) }).payload).toBe(
      "malformed",
    );
    // camera is a binary frame; a text frame claiming type camera is malformed.
    expect(decodeFrame({ kind: "text", text: JSON.stringify({ type: "camera" }) }).payload).toBe(
      "malformed",
    );
  });
});

describe("envelope decoder — binary camera frames", () => {
  it("round-trips a camera frame's slot, channel and image bytes", () => {
    const image = new Uint8Array([1, 2, 3, 4, 5]);
    const decoded = decodeFrame(cameraRaw("left_wrist", "rgb", image));
    expect(decoded.payload).toBe("binary");
    if (decoded.payload === "binary") {
      expect(decoded.slot).toBe("left_wrist");
      expect(decoded.channel).toBe("rgb");
      expect([...decoded.bytes]).toEqual([1, 2, 3, 4, 5]);
    }
  });

  it("decodes a depth channel", () => {
    const decoded = decodeFrame(cameraRaw("top", "depth", new Uint8Array([9])));
    expect(decoded.payload).toBe("binary");
    if (decoded.payload === "binary") {
      expect(decoded.channel).toBe("depth");
    }
  });

  it("rejects a too-short frame and a bad tag as malformed", () => {
    expect(decodeFrame({ kind: "binary", bytes: new ArrayBuffer(1) }).payload).toBe("malformed");
    // A tag with no channel separator.
    const noSep = new TextEncoder().encode("left_wrist");
    const buf = new ArrayBuffer(2 + noSep.byteLength);
    const view = new DataView(buf);
    view.setUint16(0, noSep.byteLength, false);
    new Uint8Array(buf).set(noSep, 2);
    expect(decodeFrame({ kind: "binary", bytes: buf }).payload).toBe("malformed");
  });

  it("rejects an out-of-grammar slot and an unknown channel", () => {
    // Uppercase slot violates the CTR-PRIM slot grammar.
    expect(decodeFrame(cameraRaw("Left_Wrist" as string, "rgb", new Uint8Array([1]))).payload).toBe(
      "malformed",
    );
    // A channel outside {rgb, depth}.
    expect(
      decodeFrame(cameraRaw("left_wrist", "infrared" as unknown as "rgb", new Uint8Array([1])))
        .payload,
    ).toBe("malformed");
  });
});
