// The command intents project onto the FROZEN CTR-WS command frame (a
// client_to_server control frame). This locks the carry-through: the wire body
// carries the frozen `type: "command"` discriminator and the intent fields
// verbatim — the screen restates no contract, it forwards intent.

import { describe, expect, it } from "vitest";

import { commandToWire, type ManualCommand } from "./commands";

describe("manual command intents project onto the frozen CTR-WS command frame", () => {
  it("wraps a jog intent as a command frame without altering its fields", () => {
    const jog: ManualCommand = {
      op: "jog_joint",
      side: "right",
      jointIndex: 4,
      direction: "positive",
      mode: "step",
      stepSizeDeg: 5,
      speedScalePct: 10,
    };
    expect(commandToWire(jog)).toEqual({
      type: "command",
      op: "jog_joint",
      side: "right",
      jointIndex: 4,
      direction: "positive",
      mode: "step",
      stepSizeDeg: 5,
      speedScalePct: 10,
    });
  });

  it("carries the stop-hold intent as a command frame (Cat 2 is the backend's)", () => {
    expect(commandToWire({ op: "stop_hold", side: "left" })).toEqual({
      type: "command",
      op: "stop_hold",
      side: "left",
    });
  });
});
