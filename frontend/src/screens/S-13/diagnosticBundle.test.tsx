// CG-G-S13c: the diagnostic bundle carries EVERY FR-OPS-023 item; one missing
// blocks generation. CG-G-S13e: video/PII inclusion is user-chosen and defaults
// to NOT included.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { DiagnosticBundleView } from "./DiagnosticBundleView";
import {
  DEFAULT_INCLUDE_PII,
  DEFAULT_INCLUDE_VIDEO,
  REQUIRED_DIAGNOSTIC_ITEMS,
  REQUIRED_ITEM_IDS,
  bundleGenerationBlocked,
  defaultPrivacySelections,
  missingRequiredItems,
} from "./diagnosticBundle";
import { loadFrOps023Text } from "./testSupport";
import type { BundleManifest } from "./types";

function completeManifest(overrides: Partial<BundleManifest> = {}): BundleManifest {
  return {
    includedItemIds: [...REQUIRED_ITEM_IDS],
    includeVideo: false,
    includePii: false,
    ...overrides,
  };
}

describe("required item set mirrors FR-OPS-023 (no cherry-pick)", () => {
  it("keeps every required item anchored in the frozen FR-OPS-023 text", () => {
    const specLine = loadFrOps023Text();
    expect(specLine).toContain("FR-OPS-023");
    for (const item of REQUIRED_DIAGNOSTIC_ITEMS) {
      expect(specLine.includes(item.specPhrase)).toBe(true);
    }
  });

  it("enumerates the ten FR-OPS-023 content categories", () => {
    expect(REQUIRED_DIAGNOSTIC_ITEMS).toHaveLength(10);
  });
});

describe("completeness gate (CG-G-S13c)", () => {
  it("does not block when all items are present", () => {
    expect(bundleGenerationBlocked(completeManifest())).toBe(false);
    expect(missingRequiredItems(completeManifest())).toEqual([]);
  });

  it("blocks and names the gap when one item is missing", () => {
    const manifest = completeManifest({
      includedItemIds: REQUIRED_ITEM_IDS.filter((id) => id !== "bound_port_map"),
    });
    expect(bundleGenerationBlocked(manifest)).toBe(true);
    expect(missingRequiredItems(manifest)).toContain("bound_port_map");
  });

  it("disables the generate button and lists the missing item in the view", () => {
    const manifest = completeManifest({
      includedItemIds: REQUIRED_ITEM_IDS.filter((id) => id !== "error_histogram"),
    });
    render(<DiagnosticBundleView manifest={manifest} />);
    expect(screen.getByTestId("bundle-generate")).toBeDisabled();
    expect(screen.getByTestId("bundle-block")).toHaveTextContent("error_histogram");
    expect(screen.getByTestId("bundle-item-error_histogram")).toHaveAttribute(
      "data-present",
      "false",
    );
    expect(screen.getByTestId("diagnostic-bundle")).toHaveAttribute("data-blocked", "true");
  });

  it("enables generation when the manifest is complete", () => {
    render(<DiagnosticBundleView manifest={completeManifest()} />);
    expect(screen.getByTestId("bundle-generate")).toBeEnabled();
    expect(screen.queryByTestId("bundle-block")).toBeNull();
  });
});

describe("video/PII default off (CG-G-S13e)", () => {
  it("defaults both inclusions to false", () => {
    expect(DEFAULT_INCLUDE_VIDEO).toBe(false);
    expect(DEFAULT_INCLUDE_PII).toBe(false);
    expect(defaultPrivacySelections()).toEqual({ includeVideo: false, includePii: false });
  });

  it("renders both toggles unchecked initially and no inclusion warning", () => {
    render(<DiagnosticBundleView manifest={completeManifest()} />);
    expect(screen.getByTestId("bundle-include-video")).not.toBeChecked();
    expect(screen.getByTestId("bundle-include-pii")).not.toBeChecked();
    expect(screen.queryByTestId("bundle-privacy-warn")).toBeNull();
  });

  it("includes video/PII only when the user turns them on", async () => {
    const user = userEvent.setup();
    const included: Array<{ includeVideo: boolean; includePii: boolean }> = [];
    render(
      <DiagnosticBundleView
        manifest={completeManifest()}
        onGenerate={(selections) => included.push(selections)}
      />,
    );
    await user.click(screen.getByTestId("bundle-include-pii"));
    expect(screen.getByTestId("bundle-privacy-warn")).toBeInTheDocument();
    await user.click(screen.getByTestId("bundle-generate"));
    expect(included).toEqual([{ includeVideo: false, includePii: true }]);
  });
});
