// CG-G-S05g: the WebXR entry point is served over HTTPS and on a port SEPARATE from
// the SPA. The screen renders the backend entry config and the separation check; it
// serves nothing itself.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DEFAULT_BACKEND_PORT } from "../../config/endpoints";
import { WebxrEntryPanel } from "./WebxrEntryPanel";
import { resolveVrEntry } from "./gates";
import { defaultTeleopSource } from "./teleopSource";

describe("WebxrEntryPanel (CG-G-S05g)", () => {
  it("renders an HTTPS entry URL on a port distinct from the SPA", () => {
    const { webxr, vrGate } = defaultTeleopSource();
    render(<WebxrEntryPanel webxr={webxr} resolution={resolveVrEntry(vrGate)} />);
    const url = screen.getByText(/https:\/\//);
    expect(url).toHaveTextContent(`https://${webxr.host}:${webxr.port}`);
    expect(webxr.port).not.toBe(DEFAULT_BACKEND_PORT);
  });

  it("reports the separation as satisfied", () => {
    const { webxr, vrGate } = defaultTeleopSource();
    render(<WebxrEntryPanel webxr={webxr} resolution={resolveVrEntry(vrGate)} />);
    const separation = screen.getByText(/VR 수신 전용/);
    expect(separation).toHaveAttribute("data-separate", "true");
    expect(separation).toHaveTextContent(String(webxr.port));
  });

  it("exposes the configurable TLS certificate and key paths", () => {
    const { webxr, vrGate } = defaultTeleopSource();
    render(<WebxrEntryPanel webxr={webxr} resolution={resolveVrEntry(vrGate)} />);
    expect(screen.getByText(webxr.tlsCertPath)).toBeInTheDocument();
    expect(screen.getByText(webxr.tlsKeyPath)).toBeInTheDocument();
  });
});
