// The shared canvas degrades honestly where WebGL is unavailable (headless/jsdom):
// it renders an accessible fallback instead of throwing, and still shows the stale
// state, so the surrounding controls stay verifiable without a GPU.

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ViewportCanvas } from "./ViewportCanvas";

// jsdom has no WebGL; stub getContext to null so the WebGL-absent branch is taken
// deterministically (jsdom otherwise throws a "not implemented" the component
// catches, which is the same outcome but noisier).
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("ViewportCanvas headless fallback", () => {
  it("renders an accessible fallback when no WebGL context is available", async () => {
    render(<ViewportCanvas presetId="iso" snapshot={null} robotHandle={null} stale={false} />);
    expect(await screen.findByRole("img", { name: /WebGL 미가용/ })).toBeInTheDocument();
  });

  it("surfaces the stale state over the canvas", async () => {
    render(<ViewportCanvas presetId="iso" snapshot={null} robotHandle={null} stale={true} />);
    expect(await screen.findByText("STALE")).toBeInTheDocument();
  });
});
