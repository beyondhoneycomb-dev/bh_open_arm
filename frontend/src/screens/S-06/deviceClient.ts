// The camera device panel's backend calls: scan, assign, release.
//
// Every call answers the WHOLE scan, not just the field that changed. The panel
// then renders what actually reached disk rather than what it asked for — and on
// this rig that difference is load-bearing: an assignment can move a camera out
// of another slot, and a panel that patched its own state locally would show the
// displaced slot as still filled.
//
// Nothing here decides anything. The backend owns the record and the refusals;
// this is the wire.

import {
  CAMERA_DEVICES_ENDPOINT,
  cameraSlotEndpoint,
} from "../../config/endpoints";
import type { DiscoveredCamera } from "./source";

export interface CameraScan {
  readonly devices: readonly DiscoveredCamera[];
  // The slots the rig has, in the order the panel offers them. From the backend
  // so the panel never offers a slot the robot does not have.
  readonly slots: readonly string[];
  // Ports present that no slot claims. Not a failure — a fourth camera on this
  // host is not this rig's problem — but worth showing while assigning.
  readonly unboundPorts: readonly string[];
}

// A refusal the backend sent, carrying its own reason. Thrown rather than
// returned as a null scan: a caller that ignored it would leave the panel
// showing the assignment it asked for while the disk holds the old one.
export class CameraRequestError extends Error {
  readonly status: number;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "CameraRequestError";
    this.status = status;
  }
}

async function readScan(response: Response): Promise<CameraScan> {
  if (!response.ok) {
    // FastAPI puts the reason in `detail`; a body that is not JSON at all means
    // something answered that is not the backend, so the status is all there is.
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body: unknown = await response.json();
      if (body !== null && typeof body === "object" && "detail" in body) {
        detail = String((body as { detail: unknown }).detail);
      }
    } catch {
      // Keep the status line.
    }
    throw new CameraRequestError(response.status, detail);
  }
  return (await response.json()) as CameraScan;
}

// Re-scan the bus. The device set is whatever answered, so a camera plugged in
// after the page loaded appears only once somebody asks again.
export async function scanDevices(): Promise<CameraScan> {
  return readScan(await fetch(CAMERA_DEVICES_ENDPOINT, { method: "GET" }));
}

// Put the camera on `portPath` into `slot`, persisted before this resolves.
export async function assignDevice(portPath: string, slot: string): Promise<CameraScan> {
  return readScan(
    await fetch(cameraSlotEndpoint(slot), {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ portPath }),
    }),
  );
}

// Empty `slot`. Keyed on the slot because that is what the record holds; the
// panel knows which slot a device fills and sends that.
export async function releaseSlot(slot: string): Promise<CameraScan> {
  return readScan(await fetch(cameraSlotEndpoint(slot), { method: "DELETE" }));
}
