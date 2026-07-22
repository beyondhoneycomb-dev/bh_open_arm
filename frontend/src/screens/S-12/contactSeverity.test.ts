// CG-G-S12e (logic half): intrusion vs imminent vs clear is read from the
// backend's signed penetration depth and margin — never computed by the GUI. The
// render half (highlight classes) is in ContactList.test.tsx.

import { describe, expect, it } from "vitest";

import { contactSeverity, isHighlighted } from "./contactSeverity";

const MARGIN = 0.02;

describe("CG-G-S12e: contact severity from backend depth", () => {
  it("classifies a penetrating contact (negative dist) as intrusion", () => {
    expect(contactSeverity(-0.001, MARGIN)).toBe("intrusion");
    expect(isHighlighted(contactSeverity(-0.001, MARGIN))).toBe(true);
  });

  it("classifies a gap within the backend margin as imminent", () => {
    expect(contactSeverity(0.0, MARGIN)).toBe("imminent");
    expect(contactSeverity(MARGIN, MARGIN)).toBe("imminent");
    expect(isHighlighted(contactSeverity(0.01, MARGIN))).toBe(true);
  });

  it("classifies a gap beyond the margin as clear, and clear is not highlighted", () => {
    expect(contactSeverity(0.05, MARGIN)).toBe("clear");
    expect(isHighlighted(contactSeverity(0.05, MARGIN))).toBe(false);
  });

  it("uses the backend margin, not a GUI constant, to place the imminent band", () => {
    // A 0.03 m gap is imminent under a 0.05 m margin but clear under 0.02 m.
    expect(contactSeverity(0.03, 0.05)).toBe("imminent");
    expect(contactSeverity(0.03, 0.02)).toBe("clear");
  });
});
