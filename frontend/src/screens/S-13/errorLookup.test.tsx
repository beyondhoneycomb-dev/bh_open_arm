// CG-G-S13f: OA-* codes are looked up with {severity, cause, recovery, doc link}
// against the frozen CTR-ERR registry (canon 14 §2.10). The registry is read from
// disk so a code table authored in the screen would diverge and fail here.

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { ErrorLookupView } from "./ErrorLookupView";
import { lookupError, severityName } from "./errorLookup";
import { loadErrorRegistry } from "./testSupport";

const REGISTRY = loadErrorRegistry();

describe("registry is the frozen CTR-ERR canon", () => {
  it("loaded a non-trivial set of codes with all four rendered fields", () => {
    const codes = Object.keys(REGISTRY);
    expect(codes.length).toBeGreaterThan(20);
    const sample = REGISTRY["OA-SYS-003"];
    expect(sample).toBeDefined();
    expect(sample.messageKo).not.toBe("");
    expect(sample.recoveryHint).not.toBe("");
    expect(sample.docUrl).toContain("14");
  });
});

describe("lookupError (CG-G-S13f)", () => {
  it("resolves a real code to its frozen entry", () => {
    const entry = lookupError(REGISTRY, "OA-CAN-001");
    expect(entry).not.toBeNull();
    expect(entry).toEqual(REGISTRY["OA-CAN-001"]);
  });

  it("returns null for a well-formed but unregistered code", () => {
    expect(lookupError(REGISTRY, "OA-CAN-999")).toBeNull();
  });

  it("returns null for a malformed code", () => {
    expect(lookupError(REGISTRY, "MOT-008")).toBeNull();
    expect(lookupError(REGISTRY, "not-a-code")).toBeNull();
  });

  it("names severity on the frozen four-level axis", () => {
    expect(severityName(REGISTRY["OA-CAN-001"])).toBe("ERROR");
  });
});

describe("ErrorLookupView render (CG-G-S13f)", () => {
  it("shows severity, cause, recovery and doc link for a typed code", async () => {
    const user = userEvent.setup();
    render(<ErrorLookupView registry={REGISTRY} />);
    await user.type(screen.getByTestId("error-query"), "OA-SYS-003");

    const entry = REGISTRY["OA-SYS-003"];
    expect(screen.getByTestId("error-severity")).toHaveTextContent("WARN");
    expect(screen.getByTestId("error-cause")).toHaveTextContent(entry.messageKo);
    expect(screen.getByTestId("error-recovery")).toHaveTextContent(entry.recoveryHint);
    expect(screen.getByTestId("error-doc")).toHaveAttribute("href", entry.docUrl);
  });

  it("rejects a malformed query without inventing an entry", async () => {
    const user = userEvent.setup();
    render(<ErrorLookupView registry={REGISTRY} />);
    await user.type(screen.getByTestId("error-query"), "nope");
    expect(screen.getByTestId("error-invalid")).toBeInTheDocument();
    expect(screen.queryByTestId(/error-entry-/)).toBeNull();
  });

  it("reports a well-formed unknown code as not in the registry", async () => {
    const user = userEvent.setup();
    render(<ErrorLookupView registry={REGISTRY} />);
    await user.type(screen.getByTestId("error-query"), "OA-CAN-999");
    expect(screen.getByTestId("error-unknown")).toBeInTheDocument();
  });
});
