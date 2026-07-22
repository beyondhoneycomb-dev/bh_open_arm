import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PreflightBanner } from "./PreflightBanner";
import { PREFLIGHT_ITEM_IDS, type PreflightItem } from "./preflight";

function allPassing(): PreflightItem[] {
  return PREFLIGHT_ITEM_IDS.map((id) => ({ id, passed: true }));
}

describe("PreflightBanner (CG-G-03f render): hard gate, no proceed-anyway", () => {
  it("lists all six items and enables start only when all pass", () => {
    const onStart = vi.fn();
    const { container } = render(
      <PreflightBanner items={allPassing()} sessionLabel="수집" onStart={onStart} />,
    );
    for (const id of PREFLIGHT_ITEM_IDS) {
      expect(container.querySelector(`[data-preflight-item="${id}"]`)).not.toBeNull();
    }
    const start = screen.getByRole("button", { name: /수집 시작/ });
    expect(start).toBeEnabled();
    fireEvent.click(start);
    expect(onStart).toHaveBeenCalledTimes(1);
  });

  it("disables start and shows a blocked note when any item fails", () => {
    const items = allPassing().map((item) =>
      item.id === "disk" ? { ...item, passed: false, detail: "잔여 < 1시간" } : item,
    );
    const onStart = vi.fn();
    render(<PreflightBanner items={items} sessionLabel="텔레옵" onStart={onStart} />);
    const start = screen.getByRole("button", { name: /텔레옵 시작/ });
    expect(start).toBeDisabled();
    fireEvent.click(start);
    expect(onStart).not.toHaveBeenCalled();
    // The banner offers no override affordance — only a blocked note.
    expect(screen.getByText(/시작 차단됨/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /그래도|무시|진행/ })).toBeNull();
  });
});
