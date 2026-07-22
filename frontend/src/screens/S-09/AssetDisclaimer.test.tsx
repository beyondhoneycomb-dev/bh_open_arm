// CG-G-S09a (rendered-text half): the rendered screen surfaces the MJCF asset only as
// a sim-asset fact — the standing "not a hardware-spec basis" disclaimer is visible
// and every fact carries the "sim asset, not a hardware spec" tag.

import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AssetDisclaimer } from "./AssetDisclaimer";
import { MJCF_ASSET_FACTS, SIM_ASSET_TAG } from "./simDomain";

describe("AssetDisclaimer (CG-G-S09a)", () => {
  it("shows the standing not-a-hardware-spec disclaimer", () => {
    render(<AssetDisclaimer />);
    expect(
      screen.getByText(/하드웨어 사양의 교차확인 근거가 아니다/),
    ).toBeInTheDocument();
  });

  it("tags every MJCF fact as a sim asset, not a hardware spec", () => {
    render(<AssetDisclaimer />);
    const tags = screen.getAllByText(SIM_ASSET_TAG);
    expect(tags).toHaveLength(MJCF_ASSET_FACTS.length);
  });

  it("frames the J7 discrepancy as a sim-asset fact with sim-asset-only basis", () => {
    render(<AssetDisclaimer />);
    const j7 = screen.getByText("J7 모터 클래스 불일치").closest("li");
    expect(j7).not.toBeNull();
    expect(j7).toHaveAttribute("data-basis", "sim-asset-only");
    expect(within(j7 as HTMLElement).getByText(SIM_ASSET_TAG)).toBeInTheDocument();
  });
});
