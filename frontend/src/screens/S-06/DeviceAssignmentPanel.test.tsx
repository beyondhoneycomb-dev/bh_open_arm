// The assignment panel, judged on the one thing it exists for: making two
// cameras with the same name pickable.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { DeviceAssignmentPanel } from "./DeviceAssignmentPanel";
import type { DiscoveredCamera } from "./source";

const WRIST_A_PORT = "usb-0000:00:0d.0-1.1.3.3";
const WRIST_B_PORT = "usb-0000:00:0d.0-1.1.4";
const ARDUCAM_CARD = "Arducam B0495 (USB3 2.3MP)";

const LEFT_WRIST_SLOT = "left_wrist";
const RIGHT_WRIST_SLOT = "right_wrist";
const SLOTS = [LEFT_WRIST_SLOT, RIGHT_WRIST_SLOT];

function device(
  portPath: string,
  assignedSlot: string | null = null,
  card: string = ARDUCAM_CARD,
): DiscoveredCamera {
  return { portPath, card, devicePath: "/dev/video0", assignedSlot };
}

function renderPanel(
  discovered: readonly DiscoveredCamera[],
  handlers: Partial<{
    onRescanDevices: () => void;
    onAssignDevice: (portPath: string, slot: string) => void;
    onReleaseDevice: (portPath: string) => void;
  }> = {},
) {
  return render(
    <DeviceAssignmentPanel
      discovered={discovered}
      slots={SLOTS}
      onRescanDevices={handlers.onRescanDevices ?? (() => {})}
      onAssignDevice={handlers.onAssignDevice ?? (() => {})}
      onReleaseDevice={handlers.onReleaseDevice ?? (() => {})}
    />,
  );
}

describe("telling identical cameras apart", () => {
  it("renders each device's port, not only its name", () => {
    // Both rows say "Arducam B0495". The port is the ONLY text that differs, so
    // a panel that dropped it would be unusable on exactly this hardware.
    renderPanel([device(WRIST_A_PORT), device(WRIST_B_PORT)]);

    expect(screen.getByText(WRIST_A_PORT)).toBeTruthy();
    expect(screen.getByText(WRIST_B_PORT)).toBeTruthy();
  });

  it("renders a preview for every discovered device, assigned or not", () => {
    // The unassigned one is precisely what the operator has to look at to decide.
    renderPanel([device(WRIST_A_PORT, LEFT_WRIST_SLOT), device(WRIST_B_PORT)]);

    expect(screen.getByTestId(`preview-${WRIST_A_PORT}`)).toBeTruthy();
    expect(screen.getByTestId(`preview-${WRIST_B_PORT}`)).toBeTruthy();
  });

  it("says so when two devices share a name", () => {
    renderPanel([device(WRIST_A_PORT), device(WRIST_B_PORT)]);

    expect(screen.getAllByText(/같은 이름의 장치가 하나 더 있다/)).toHaveLength(2);
  });

  it("does not cry ambiguity over a single device", () => {
    renderPanel([device(WRIST_A_PORT, null, "ZED-M: ZED-M")]);

    expect(screen.queryByText(/같은 이름의 장치가 하나 더 있다/)).toBeNull();
  });
});

describe("the row set is derived, not fixed", () => {
  it("renders one row per discovered device", () => {
    const { container } = renderPanel([device(WRIST_A_PORT), device(WRIST_B_PORT)]);

    expect(container.querySelectorAll(".oa-cam-assign__row")).toHaveLength(2);
  });

  it("renders nothing but an empty notice when no camera answered", () => {
    const { container } = renderPanel([]);

    expect(container.querySelectorAll(".oa-cam-assign__row")).toHaveLength(0);
    expect(screen.getByText(/붙어 있는 카메라가 없다/)).toBeTruthy();
  });
});

describe("assigning", () => {
  it("sends the port and the slot the operator chose", () => {
    const onAssignDevice = vi.fn();
    renderPanel([device(WRIST_A_PORT), device(WRIST_B_PORT)], { onAssignDevice });

    const rows = screen.getAllByRole("combobox");
    fireEvent.change(rows[1], { target: { value: RIGHT_WRIST_SLOT } });

    expect(onAssignDevice).toHaveBeenCalledWith(WRIST_B_PORT, RIGHT_WRIST_SLOT);
  });

  it("refuses a slot another device holds, and sends nothing", () => {
    const onAssignDevice = vi.fn();
    const devices = [device(WRIST_A_PORT, LEFT_WRIST_SLOT), device(WRIST_B_PORT)];
    renderPanel(devices, { onAssignDevice });

    fireEvent.change(screen.getAllByRole("combobox")[1], {
      target: { value: LEFT_WRIST_SLOT },
    });

    expect(onAssignDevice).not.toHaveBeenCalled();
    expect(screen.getByRole("alert").textContent).toContain(WRIST_A_PORT);
  });

  it("marks an occupied slot in the picker rather than offering it silently", () => {
    renderPanel([device(WRIST_A_PORT, LEFT_WRIST_SLOT), device(WRIST_B_PORT)]);

    const options = screen.getAllByRole("option").map((option) => option.textContent);

    expect(options).toContain(`${LEFT_WRIST_SLOT} (사용 중)`);
  });

  it("offers only the slots it was given", () => {
    // A hardcoded slot here would offer one the robot does not have.
    renderPanel([device(WRIST_A_PORT)]);

    const values = screen
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);

    expect(values).toEqual(["", LEFT_WRIST_SLOT, RIGHT_WRIST_SLOT]);
  });

  it("disables the picker for a device with no port", () => {
    renderPanel([device("")]);

    expect((screen.getByRole("combobox") as HTMLSelectElement).disabled).toBe(true);
  });
});

describe("releasing and rescanning", () => {
  it("offers release only for a device that fills a slot", () => {
    renderPanel([device(WRIST_A_PORT, LEFT_WRIST_SLOT), device(WRIST_B_PORT)]);

    expect(screen.getAllByRole("button", { name: "해제" })).toHaveLength(1);
  });

  it("sends the port when release is pressed", () => {
    const onReleaseDevice = vi.fn();
    renderPanel([device(WRIST_A_PORT, LEFT_WRIST_SLOT)], { onReleaseDevice });

    fireEvent.click(screen.getByRole("button", { name: "해제" }));

    expect(onReleaseDevice).toHaveBeenCalledWith(WRIST_A_PORT);
  });

  it("asks the backend to look again", () => {
    // A camera plugged in after load is invisible until somebody asks.
    const onRescanDevices = vi.fn();
    renderPanel([], { onRescanDevices });

    fireEvent.click(screen.getByRole("button", { name: "다시 스캔" }));

    expect(onRescanDevices).toHaveBeenCalled();
  });
});
