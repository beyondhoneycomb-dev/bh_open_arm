// CG-G-S04g: during Freedrive a banner shows across ALL screens. The banner's
// visibility is a pure function of backend Freedrive state, invariant to which
// screen is active — so wherever the always-on global surface (WP-G-03) hoists it,
// it renders identically. This test asserts that invariance by rendering the
// banner for every ScreenId in the canonical registry: active => banner on every
// screen, inactive => nothing.
//
// (S-04 owns the intent and the banner element; it cannot paint pixels on a
// sibling route from its own subtree, so "all screens" is proven as the route
// independence the global mount relies on, not by mounting into siblings.)

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SCREENS } from "../../routes/registry";
import { FreedriveBanner } from "./FreedriveBanner";
import type { FreedriveStatus } from "./manualSource";

const ACTIVE: FreedriveStatus = {
  active: true,
  side: "right",
  gravityCompensated: false,
  frictionCompensated: false,
  path: "B_low_impedance",
};

const INACTIVE: FreedriveStatus = { ...ACTIVE, active: false };

describe("CG-G-S04g Freedrive banner is shown across all screens", () => {
  it("renders on every registered screen while Freedrive is active", () => {
    for (const screen of SCREENS) {
      const { container, unmount } = render(
        <FreedriveBanner status={ACTIVE} currentScreen={screen.id} />,
      );
      const banner = container.querySelector('[data-freedrive="active"]');
      expect(banner, `banner missing on ${screen.id}`).not.toBeNull();
      unmount();
    }
  });

  it("renders nothing when Freedrive is inactive", () => {
    const { container } = render(<FreedriveBanner status={INACTIVE} currentScreen="S-04" />);
    expect(container.querySelector('[data-freedrive="active"]')).toBeNull();
    expect(container).toBeEmptyDOMElement();
  });

  it("surfaces the gravity-uncompensated warning while active", () => {
    const { getByText } = render(<FreedriveBanner status={ACTIVE} currentScreen="S-04" />);
    expect(getByText(/중력 미보상/)).toBeInTheDocument();
  });
});
