import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { PushToHubBadge, PushToHubConfirm } from "./PushToHubBadge";
import { PUSH_TO_HUB_UPLOAD_WARNING, type PushToHubState } from "./flags";

const ON: PushToHubState = { enabled: true, private: false, tags: ["openarm"] };
const OFF: PushToHubState = { enabled: false, private: true, tags: [] };

describe("PushToHubBadge (CG-G-03d render)", () => {
  it("shows the upload warning in a danger tone when on", () => {
    render(<PushToHubBadge state={ON} />);
    const badge = screen.getByRole("status");
    expect(badge.className).toContain("oa-badge--danger");
    expect(badge).toHaveTextContent(PUSH_TO_HUB_UPLOAD_WARNING);
  });

  it("shows no warning when off", () => {
    render(<PushToHubBadge state={OFF} />);
    expect(screen.getByRole("status")).not.toHaveTextContent(PUSH_TO_HUB_UPLOAD_WARNING);
  });
});

describe("PushToHubConfirm forces an explicit confirmation (CG-G-03d)", () => {
  it("renders a confirmation gate when push_to_hub is on", () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<PushToHubConfirm state={ON} onConfirm={onConfirm} onCancel={onCancel} />);
    const dialog = screen.getByRole("alertdialog");
    expect(dialog).toHaveTextContent(PUSH_TO_HUB_UPLOAD_WARNING);
    // The only way forward is an affirmative click — no auto-proceed.
    fireEvent.click(screen.getByRole("button", { name: /계속/ }));
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("renders nothing when push_to_hub is off (no gate needed)", () => {
    const { container } = render(
      <PushToHubConfirm state={OFF} onConfirm={() => {}} onCancel={() => {}} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
