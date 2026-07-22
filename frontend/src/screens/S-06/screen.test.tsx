// Integration checks for the whole /cameras screen against the offline fixtures.
// Each CG-G-S06* gate's render half is exercised here; the static/structural
// halves live in staticChecks.test.ts and contract.test.ts.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CameraScreen from "./screen";
import { imageFeatureKey } from "../../ws/envelope";
import { defaultCameraScreenSource, type CameraScreenSource } from "./source";

function withGates(overrides: Partial<CameraScreenSource["gates"]>): CameraScreenSource {
  const base = defaultCameraScreenSource();
  return { ...base, gates: { ...base.gates, ...overrides } };
}

describe("S-06 /cameras screen", () => {
  it("renders offline with no backend and shows every panel", () => {
    const { container } = render(<CameraScreen />);
    expect(container.querySelector(".oa-cam")).not.toBeNull();
    expect(container.querySelector("#oa-cam-tiles-title")).not.toBeNull();
    expect(container.querySelector("#oa-cam-stats-title")).not.toBeNull();
    expect(container.querySelector("#oa-cam-preview-title")).not.toBeNull();
    expect(container.querySelector("#oa-cam-handeye-title")).not.toBeNull();
    expect(container.querySelector("#oa-cam-frustum-title")).not.toBeNull();
  });

  it("CG-G-S06a: tile count is runtime-derived and follows a camera add/remove", () => {
    const base = defaultCameraScreenSource();
    const three = render(<CameraScreen source={base} />);
    expect(three.container.querySelectorAll("[data-tile-slot]")).toHaveLength(3);
    expect(three.container.querySelector("[data-tile-count]")?.getAttribute("data-tile-count")).toBe(
      "3",
    );

    const added: CameraScreenSource = {
      ...base,
      observationFeatures: [...base.observationFeatures, imageFeatureKey("overhead", "rgb")],
    };
    const four = render(<CameraScreen source={added} />);
    expect(four.container.querySelectorAll("[data-tile-slot]")).toHaveLength(4);

    const removed: CameraScreenSource = {
      ...base,
      observationFeatures: base.observationFeatures.filter(
        (key) => key !== imageFeatureKey("front", "rgb"),
      ),
    };
    const two = render(<CameraScreen source={removed} />);
    expect(two.container.querySelectorAll("[data-tile-slot]")).toHaveLength(2);
  });

  it("CG-G-S06b: every tile shows BOTH the UI label and the dataset key", () => {
    const { container } = render(<CameraScreen />);
    const tiles = container.querySelectorAll("[data-tile-slot]");
    expect(tiles.length).toBeGreaterThan(0);
    for (const tile of tiles) {
      const label = tile.querySelector("[data-tile-label]");
      const key = tile.querySelector("[data-dataset-key]");
      expect(label).not.toBeNull();
      expect(key).not.toBeNull();
      expect(key?.textContent).toMatch(/^observation\.images\./);
    }
    // The arm prefix is auto-attached and made visible for a per-arm camera.
    expect(container.querySelector('[data-arm-prefix-note="left_wrist"]')).not.toBeNull();
  });

  it("CG-G-S06c: preview OFF does not change the record drop and recording continues", () => {
    const base = defaultCameraScreenSource();
    // right_wrist ships with preview OFF; its tile still renders and records.
    const { container } = render(<CameraScreen source={base} />);
    expect(container.querySelector('[data-preview-off="right_wrist"]')).not.toBeNull();

    const dropWith = container
      .querySelector('[data-record-drop="right_wrist"]')
      ?.textContent?.trim();

    const previewOn: CameraScreenSource = {
      ...base,
      cameras: {
        ...base.cameras,
        right_wrist: { ...base.cameras.right_wrist, previewEnabled: true },
      },
    };
    const { container: onContainer } = render(<CameraScreen source={previewOn} />);
    const dropOn = onContainer
      .querySelector('[data-record-drop="right_wrist"]')
      ?.textContent?.trim();

    // Toggling the preview switch leaves the backend record drop rate identical.
    expect(dropWith).toBe(dropOn);
  });

  it("CG-G-S06d: a depth camera renders a colormap; an RGB-only camera does not", () => {
    const { container } = render(<CameraScreen />);
    const depth = container.querySelector('[data-depth-colormap="right_wrist"]');
    expect(depth).not.toBeNull();
    expect(depth?.querySelectorAll("[data-depth-cell]").length).toBe(48);
    expect(container.querySelector('[data-depth-colormap="left_wrist"]')).toBeNull();
  });

  it("CG-G-S06e: the three metrics show and a sub-95% stream reads WARN", () => {
    const { container } = render(<CameraScreen />);
    const frontRow = container.querySelector(
      `[data-metric-channel="${imageFeatureKey("front", "rgb")}"]`,
    );
    expect(frontRow?.getAttribute("data-metric-level")).toBe("warn");
    const leftRow = container.querySelector(
      `[data-metric-channel="${imageFeatureKey("left_wrist", "rgb")}"]`,
    );
    expect(leftRow?.getAttribute("data-metric-level")).toBe("ok");
  });

  it("CG-G-S06f: hand-eye shows five methods and no single-method-adopt control", () => {
    const { container } = render(<CameraScreen />);
    const cards = container.querySelectorAll("[data-handeye-slot]");
    expect(cards.length).toBeGreaterThan(0);
    for (const card of cards) {
      expect(card.querySelectorAll("[data-handeye-method]")).toHaveLength(5);
    }
    expect(container.querySelectorAll('[data-action="adopt-method"]')).toHaveLength(0);
  });

  it("CG-G-S06g: the frustum reads stale exactly when the hand-eye is stale", () => {
    const { container } = render(<CameraScreen />);
    expect(
      container
        .querySelector('[data-frustum-slot="front"]')
        ?.getAttribute("data-frustum-stale"),
    ).toBe("true");
    expect(
      container
        .querySelector('[data-frustum-slot="right_wrist"]')
        ?.getAttribute("data-frustum-stale"),
    ).toBe("false");
  });

  it("PG-CAM-001 pending: tiles render with a pending note and none are blocked", () => {
    const { container } = render(<CameraScreen />);
    expect(container.querySelectorAll("[data-tile-blocked]")).toHaveLength(0);
    expect(container.querySelector("[data-tile-pending]")).not.toBeNull();
    expect(container.querySelector('[data-tile-disposition="pending"]')).not.toBeNull();
  });

  it("PG-CAM-001 DEGRADED_ACCEPTED: only the degraded config tile is blocked", () => {
    const source = withGates({ pgCam001: "degraded_accepted", blockedSlots: ["front"] });
    const { container } = render(<CameraScreen source={source} />);
    expect(container.querySelector('[data-tile-blocked="front"]')).not.toBeNull();
    expect(
      container
        .querySelector('[data-tile-slot="left_wrist"]')
        ?.getAttribute("data-tile-disposition"),
    ).toBe("normal");
  });

  it("PG-DEPTH-001 failure: RGB-only reduction removes the depth colormap and frustum depth", () => {
    const source = withGates({ pgDepth001: "fail_blocking" });
    const { container } = render(<CameraScreen source={source} />);
    expect(container.querySelector("[data-depth-colormap]")).toBeNull();
    expect(container.querySelector("[data-depth-gate-note]")).not.toBeNull();
    expect(container.querySelector("[data-frustum-depth-removed]")).not.toBeNull();
  });
});
