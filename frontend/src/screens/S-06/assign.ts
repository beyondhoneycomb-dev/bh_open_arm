// Device→slot assignment: what the operator may pick, and what the panel must say.
//
// The rig this exists for is two Arducam B0495 with one serial between them. The
// driver reports the SAME `card` string for both, so no name, model, or resolution
// separates them — only the port the kernel reports, and the picture each is
// sending. That is why assignment is an operator decision taken against a preview
// rather than something the backend can settle by scanning.
//
// These are pure functions over the discovered set. The screen renders what they
// return and the backend enforces the result; nothing here opens a camera.

import type { DiscoveredCamera } from "./source";

// Whether a device carries an identity a slot can be assigned against. A device
// with no port has nothing stable to name it by, so assigning it would pin the
// slot to an enumeration order — the thing `06` FR-CAM-004 refuses.
export function isAssignable(device: DiscoveredCamera): boolean {
  return device.portPath.trim().length > 0;
}

// Whether two devices are indistinguishable by name alone. True on this rig's
// wrist pair, and the reason the panel must render the port and the preview.
export function shareCardName(
  devices: readonly DiscoveredCamera[],
  card: string,
): boolean {
  return devices.filter((device) => device.card === card).length > 1;
}

// The device currently filling a slot, or null when the slot is empty.
export function deviceForSlot(
  devices: readonly DiscoveredCamera[],
  slot: string,
): DiscoveredCamera | null {
  return devices.find((device) => device.assignedSlot === slot) ?? null;
}

export type AssignmentRefusal =
  // The device reported no port, so nothing stable identifies it.
  | { kind: "no_port"; portPath: string }
  // The slot is filled by a different device. Silently replacing it would leave
  // the operator believing both are recording when one was displaced.
  | { kind: "slot_taken"; slot: string; heldBy: string }
  // The device is not in the discovered set — it was unplugged since the scan.
  | { kind: "absent"; portPath: string };

// Judge an assignment before it is sent. Returns null when it may proceed.
//
// Re-assigning a device to the slot it already fills is admitted rather than
// refused as "taken": it is a no-op, and reporting it as a conflict would train
// the operator to click through the message that matters.
export function refuseAssignment(
  devices: readonly DiscoveredCamera[],
  portPath: string,
  slot: string,
): AssignmentRefusal | null {
  const device = devices.find((candidate) => candidate.portPath === portPath);
  if (device === undefined) {
    return { kind: "absent", portPath };
  }
  if (!isAssignable(device)) {
    return { kind: "no_port", portPath };
  }
  const holder = deviceForSlot(devices, slot);
  if (holder !== null && holder.portPath !== portPath) {
    return { kind: "slot_taken", slot, heldBy: holder.portPath };
  }
  return null;
}

// The operator-facing sentence for a refusal. Kept beside the judgment so a new
// refusal kind cannot be added without a message, which is how a refusal ends up
// rendering as an empty box.
export function refusalMessage(refusal: AssignmentRefusal): string {
  switch (refusal.kind) {
    case "no_port":
      return "이 장치는 포트를 보고하지 않는다 — 재연결하면 다른 카메라를 가리키게 되므로 지정할 수 없다";
    case "slot_taken":
      return `${refusal.slot} 슬롯은 ${refusal.heldBy} 가 이미 쓰고 있다 — 먼저 해제해야 한다`;
    case "absent":
      return "이 장치는 마지막 스캔 이후 사라졌다 — 다시 스캔해야 한다";
  }
}
