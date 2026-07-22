// Runtime CG-G-S02a/b/e on the /connection route. Rendered against fixtures; no
// backend, no router (ConnectionScreen takes an explicit route prop).

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConnectionScreen } from "./ConnectionScreen";
import { defaultConnectionSource, type ConnectionSource } from "./connectionSource";

function withCanVerified(overrides: Partial<ConnectionSource> = {}): ConnectionSource {
  const base = defaultConnectionSource();
  return {
    ...base,
    canInterfaces: base.canInterfaces.map((iface) => ({ ...iface, canFdConfigured: true })),
    ...overrides,
  };
}

describe("CG-G-S02a side unselected => progress impossible", () => {
  it("shows the ±5° silent-lock warning and disables bringup until a side is chosen", () => {
    const { container } = render(
      <ConnectionScreen route="/connection" source={withCanVerified()} />,
    );

    // Side unchosen: the warning is present and the bringup is gated.
    expect(container.querySelector('[data-warning="side-unset"]')).not.toBeNull();
    const advance = container.querySelector<HTMLButtonElement>('[data-action="advance-bringup"]');
    expect(advance?.disabled).toBe(true);
    expect(container.querySelector('[data-gate="blocked"]')?.textContent).toContain("side 미선택");

    // Choose a side: warning clears, gate clears, bringup enables.
    fireEvent.click(container.querySelector('input[value="left"]') as HTMLInputElement);
    expect(container.querySelector('[data-warning="side-unset"]')).toBeNull();
    expect(container.querySelector('[data-gate="blocked"]')).toBeNull();
    expect(
      container.querySelector<HTMLButtonElement>('[data-action="advance-bringup"]')?.disabled,
    ).toBe(false);
  });
});

describe("CG-G-S02b first bringup call is connect_readonly", () => {
  it("emits connect_readonly as the first action when the operator advances", () => {
    const onBringupAction = vi.fn();
    const { container } = render(
      <ConnectionScreen
        route="/connection"
        source={withCanVerified()}
        onBringupAction={onBringupAction}
      />,
    );

    fireEvent.click(container.querySelector('input[value="left"]') as HTMLInputElement);
    fireEvent.click(container.querySelector('[data-action="advance-bringup"]') as HTMLButtonElement);

    expect(onBringupAction).toHaveBeenCalledTimes(1);
    expect(onBringupAction.mock.calls[0][0]).toBe("connect_readonly");
    expect(container.querySelector('[data-emitted="connect_readonly"]')).not.toBeNull();
  });
});

describe("CG-G-S02e CAN-FD unverified => startup blocked", () => {
  it("blocks startup and the bringup while any interface has CAN-FD unverified", () => {
    // The offline default has CAN-FD unverified on every interface.
    const { container } = render(<ConnectionScreen route="/connection" source={defaultConnectionSource()} />);

    expect(container.querySelector('[data-startup="blocked"]')).not.toBeNull();

    // Even with a side chosen, the bringup stays gated on CAN-FD.
    fireEvent.click(container.querySelector('input[value="left"]') as HTMLInputElement);
    expect(container.querySelector('[data-gate="blocked"]')?.textContent).toContain("CAN-FD 미검증");
    expect(
      container.querySelector<HTMLButtonElement>('[data-action="advance-bringup"]')?.disabled,
    ).toBe(true);
  });

  it("clears startup once every interface has CAN-FD verified", () => {
    const { container } = render(<ConnectionScreen route="/connection" source={withCanVerified()} />);
    expect(container.querySelector('[data-startup="clear"]')).not.toBeNull();
  });
});
