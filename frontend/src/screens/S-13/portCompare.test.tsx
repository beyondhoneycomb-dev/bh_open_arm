// CG-G-S13a: the shown port map is compared against the 01 §2.17 + 14 §2.1 canon
// and a mismatch is surfaced, with zero canon of S-13's own.
// CG-G-S13d: a port-clash injection raises a warning.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PortCompareView } from "./PortCompareView";
import { comparePorts } from "./portCompare";
import { loadPortCanon } from "./testSupport";
import type { ActualBinding, CanonPortEntry } from "./types";

// The canon comes from the spec, parsed at test time — never authored here.
const CANON: CanonPortEntry[] = loadPortCanon();

// One clean binding per DISTINCT canon port. The union canon deliberately lists
// some ports twice (14 §2.1 notes the web backend and openpi both default to
// 8000); binding both at once would itself be a runtime clash, so the clean
// baseline is one listener per port.
function bindingsMatching(canon: CanonPortEntry[]): ActualBinding[] {
  const seen = new Set<number>();
  const bindings: ActualBinding[] = [];
  for (const entry of canon) {
    if (entry.port === null || seen.has(entry.port)) {
      continue;
    }
    seen.add(entry.port);
    bindings.push({ component: entry.component, port: entry.port, pid: 1000 + bindings.length, listening: true });
  }
  return bindings;
}

describe("port canon is sourced from the spec, not the screen", () => {
  it("parses the 01 §2.17 + 14 §2.1 union and includes the web-backend port", () => {
    expect(CANON.length).toBeGreaterThanOrEqual(5);
    const ports = CANON.map((entry) => entry.port).filter((port): port is number => port !== null);
    // 8000 is the web backend anchor: if the parser missed the real table this fails.
    expect(ports).toContain(8000);
  });
});

describe("comparePorts (CG-G-S13a)", () => {
  it("reports no discrepancy when every binding matches the canon", () => {
    const comparison = comparePorts(CANON, bindingsMatching(CANON));
    expect(comparison.hasMismatch).toBe(false);
  });

  it("surfaces a mismatch when a binding deviates from the canon port", () => {
    const actual = bindingsMatching(CANON);
    actual[0] = { ...actual[0], port: actual[0].port + 1 };
    const comparison = comparePorts(CANON, actual);
    expect(comparison.hasMismatch).toBe(true);
    const deviated = comparison.rows.find((row) => row.component === actual[0].component);
    expect(deviated?.status).toBe("mismatch");
  });

  it("marks a binding for an unlisted component as unexpected", () => {
    const actual = [
      ...bindingsMatching(CANON),
      { component: "rogue_service", port: 9, pid: 42, listening: true },
    ];
    const comparison = comparePorts(CANON, actual);
    expect(comparison.hasMismatch).toBe(true);
    expect(comparison.rows.find((row) => row.component === "rogue_service")?.status).toBe(
      "unexpected",
    );
  });
});

describe("port clash (CG-G-S13d)", () => {
  it("detects two components listening on the same port", () => {
    const actual: ActualBinding[] = [
      { component: "web_backend", port: 7, pid: 1, listening: true },
      { component: "openpi", port: 7, pid: 2, listening: true },
    ];
    const comparison = comparePorts([], actual);
    expect(comparison.clashes).toHaveLength(1);
    expect(comparison.clashes[0].components).toEqual(["openpi", "web_backend"]);
    expect(comparison.hasMismatch).toBe(true);
  });

  it("does not count a shared port when only one side is actually listening", () => {
    const actual: ActualBinding[] = [
      { component: "web_backend", port: 7, pid: 1, listening: true },
      { component: "openpi", port: 7, pid: null, listening: false },
    ];
    expect(comparePorts([], actual).clashes).toHaveLength(0);
  });
});

describe("PortCompareView render (CG-G-S13a, CG-G-S13d)", () => {
  it("renders a mismatch alert and flags the discrepant row", () => {
    const actual = bindingsMatching(CANON);
    const wrongComponent = actual[0].component;
    actual[0] = { ...actual[0], port: actual[0].port + 1 };
    render(<PortCompareView canon={CANON} actual={actual} />);
    expect(screen.getByTestId("port-mismatch-alert")).toBeInTheDocument();
    expect(screen.getByTestId(`port-row-${wrongComponent}`)).toHaveAttribute(
      "data-status",
      "mismatch",
    );
    expect(screen.getByTestId("port-compare")).toHaveAttribute("data-has-mismatch", "true");
  });

  it("renders a clash warning when two bindings share a port", () => {
    const actual: ActualBinding[] = [
      { component: "web_backend", port: 7, pid: 1, listening: true },
      { component: "openpi", port: 7, pid: 2, listening: true },
    ];
    render(<PortCompareView canon={CANON} actual={actual} />);
    expect(screen.getByTestId("port-clashes")).toBeInTheDocument();
    expect(screen.getByTestId("port-clash-7")).toHaveTextContent("openpi");
  });
});
