// CG-G-S09e: the ghost overlay makes sim and real visually unmistakable — both
// layers appear in the legend with distinct labels, and their swatches differ on
// colour, opacity and outline style so the two never blur together.

import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GhostOverlay } from "./GhostOverlay";
import { defaultViewportSource } from "../../viewport";

// The embedded viewport canvas takes the WebGL-absent fallback in jsdom; stub
// getContext to null so that branch is deterministic and quiet.
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockImplementation(() => null);
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("GhostOverlay (CG-G-S09e)", () => {
  it("labels both a sim ghost layer and a real layer distinctly", async () => {
    render(<GhostOverlay viewport={defaultViewportSource()} />);
    expect(await screen.findByText(/실기 \(REAL\)/)).toBeInTheDocument();
    expect(screen.getByText(/시뮬 고스트 \(SIM\)/)).toBeInTheDocument();
  });

  it("gives the two swatches different colour, opacity and outline", () => {
    render(<GhostOverlay viewport={defaultViewportSource()} />);
    const sim = document.querySelector('.oa-sim__ghost-swatch[data-layer="sim"]') as HTMLElement;
    const real = document.querySelector('.oa-sim__ghost-swatch[data-layer="real"]') as HTMLElement;
    expect(sim).not.toBeNull();
    expect(real).not.toBeNull();
    expect(sim.style.backgroundColor).not.toBe(real.style.backgroundColor);
    expect(sim.style.opacity).not.toBe(real.style.opacity);
    expect(sim.style.borderStyle).not.toBe(real.style.borderStyle);
  });
});
