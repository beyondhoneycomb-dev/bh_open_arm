// CG-G-S12d (render half): a wall edit reaches the scene only through the geom
// injector callback, and the editor never adds the wall to its own rendered list
// (that list is backend truth). The static half — zero self-collision decision in
// the source — is in staticChecks.test.ts.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VirtualWallEditor } from "./VirtualWallEditor";
import type { VirtualWall } from "./source";

function wall(): VirtualWall {
  return {
    id: "vwall_a",
    label: "금지영역 A",
    shape: "box",
    center: [0, 0, 0.5],
    halfExtents: [0.1, 0.1, 0.1],
    normal: [0, 0, 1],
    enabled: true,
  };
}

describe("CG-G-S12d: wall edits reflect only via the geom injector", () => {
  it("sends the draft to onInjectWall on inject", () => {
    const onInjectWall = vi.fn();
    const { container } = render(
      <VirtualWallEditor walls={[]} onInjectWall={onInjectWall} onRemoveWall={() => {}} />,
    );
    fireEvent.click(container.querySelector('[data-action="inject-wall"]')!);
    expect(onInjectWall).toHaveBeenCalledTimes(1);
    const spec = onInjectWall.mock.calls[0][0];
    expect(spec).toMatchObject({ shape: "box", enabled: true });
    expect(spec.center).toHaveLength(3);
  });

  it("does not add the injected wall to its own list — the list is backend truth", () => {
    const onInjectWall = vi.fn();
    const { container } = render(
      <VirtualWallEditor walls={[]} onInjectWall={onInjectWall} onRemoveWall={() => {}} />,
    );
    fireEvent.click(container.querySelector('[data-action="inject-wall"]')!);
    // The backend has not re-supplied walls, so nothing new is rendered locally.
    expect(container.querySelectorAll("[data-wall]")).toHaveLength(0);
  });

  it("renders the backend walls and removes via intent", () => {
    const onRemoveWall = vi.fn();
    const { container } = render(
      <VirtualWallEditor walls={[wall()]} onInjectWall={() => {}} onRemoveWall={onRemoveWall} />,
    );
    expect(container.querySelectorAll("[data-wall]")).toHaveLength(1);
    fireEvent.click(container.querySelector('[data-action="remove-wall"]')!);
    expect(onRemoveWall).toHaveBeenCalledWith("vwall_a");
  });
});
