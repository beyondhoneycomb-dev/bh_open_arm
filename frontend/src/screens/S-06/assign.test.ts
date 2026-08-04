// Device→slot assignment judgment, over the state that makes it necessary:
// two cameras whose only difference is the port they hang off.

import { describe, expect, it } from "vitest";
import {
  deviceForSlot,
  isAssignable,
  refusalMessage,
  refuseAssignment,
  shareCardName,
} from "./assign";
import type { DiscoveredCamera } from "./source";

const WRIST_A_PORT = "usb-0000:00:0d.0-1.1.3.3";
const WRIST_B_PORT = "usb-0000:00:0d.0-1.1.4";
const ZED_PORT = "usb-0000:80:14.0-4.1";

// Measured off the bench: the string the driver returns for BOTH wrist cameras.
const ARDUCAM_CARD = "Arducam B0495 (USB3 2.3MP)";

const LEFT_WRIST_SLOT = "left_wrist";
const RIGHT_WRIST_SLOT = "right_wrist";

function device(
  portPath: string,
  card: string,
  assignedSlot: string | null = null,
): DiscoveredCamera {
  return { portPath, card, devicePath: "/dev/video0", assignedSlot };
}

// The bench as it actually enumerates: identical wrist cards, distinct ports.
function bench(): DiscoveredCamera[] {
  return [
    device(WRIST_A_PORT, ARDUCAM_CARD, LEFT_WRIST_SLOT),
    device(WRIST_B_PORT, ARDUCAM_CARD),
    device(ZED_PORT, "ZED-M: ZED-M"),
  ];
}

describe("what the operator may pick by", () => {
  it("reports the wrist pair as indistinguishable by name", () => {
    // The premise of the whole panel. If this ever goes false the hardware
    // changed, and a name-only picker would silently become adequate.
    expect(shareCardName(bench(), ARDUCAM_CARD)).toBe(true);
  });

  it("does not call a one-off device name-ambiguous", () => {
    expect(shareCardName(bench(), "ZED-M: ZED-M")).toBe(false);
  });

  it("treats a device with a port as assignable", () => {
    expect(isAssignable(device(WRIST_A_PORT, ARDUCAM_CARD))).toBe(true);
  });

  it("refuses a device that reported no port", () => {
    // Nothing stable names it, so a slot pinned to it is pinned to enumeration
    // order — what FR-CAM-004 refuses.
    expect(isAssignable(device("", ARDUCAM_CARD))).toBe(false);
    expect(isAssignable(device("   ", ARDUCAM_CARD))).toBe(false);
  });
});

describe("assignment judgment", () => {
  it("admits an unassigned device into an empty slot", () => {
    expect(refuseAssignment(bench(), WRIST_B_PORT, RIGHT_WRIST_SLOT)).toBeNull();
  });

  it("refuses a slot another device already fills", () => {
    const refusal = refuseAssignment(bench(), WRIST_B_PORT, LEFT_WRIST_SLOT);

    expect(refusal).toEqual({
      kind: "slot_taken",
      slot: LEFT_WRIST_SLOT,
      heldBy: WRIST_A_PORT,
    });
  });

  it("admits re-assigning a device to the slot it already fills", () => {
    // A no-op. Calling it a conflict trains the operator past the real message.
    expect(refuseAssignment(bench(), WRIST_A_PORT, LEFT_WRIST_SLOT)).toBeNull();
  });

  it("refuses a device that is not in the discovered set", () => {
    const refusal = refuseAssignment(bench(), "usb-0000:99:99.9-9.9", RIGHT_WRIST_SLOT);

    expect(refusal).toEqual({ kind: "absent", portPath: "usb-0000:99:99.9-9.9" });
  });

  it("refuses a discovered device that carries no port", () => {
    const devices = [device("", ARDUCAM_CARD)];

    expect(refuseAssignment(devices, "", RIGHT_WRIST_SLOT)).toEqual({
      kind: "no_port",
      portPath: "",
    });
  });
});

describe("slot occupancy", () => {
  it("names the device filling a slot", () => {
    expect(deviceForSlot(bench(), LEFT_WRIST_SLOT)?.portPath).toBe(WRIST_A_PORT);
  });

  it("returns null for an empty slot rather than the first device", () => {
    expect(deviceForSlot(bench(), RIGHT_WRIST_SLOT)).toBeNull();
  });
});

describe("refusal messages", () => {
  it("gives every refusal kind a sentence that names its cause", () => {
    // A refusal with no message renders as an empty box, which reads as success.
    const messages = [
      refusalMessage({ kind: "no_port", portPath: "" }),
      refusalMessage({ kind: "slot_taken", slot: LEFT_WRIST_SLOT, heldBy: WRIST_A_PORT }),
      refusalMessage({ kind: "absent", portPath: WRIST_B_PORT }),
    ];

    expect(messages.every((message) => message.trim().length > 0)).toBe(true);
    expect(new Set(messages).size).toBe(messages.length);
  });

  it("names the port that is holding the slot", () => {
    const message = refusalMessage({
      kind: "slot_taken",
      slot: LEFT_WRIST_SLOT,
      heldBy: WRIST_A_PORT,
    });

    // "the slot is taken" without saying by what leaves the operator guessing
    // between two cameras with the same name.
    expect(message).toContain(WRIST_A_PORT);
  });
});
