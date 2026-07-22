// CG-G-S12e (render half): intrusion and imminent contacts are highlighted;
// clear contacts are not. The highlight is driven by the backend's signed depth,
// carried through contactSeverity.

import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ContactList } from "./ContactList";
import type { ContactRecord } from "./source";

function contact(id: string, distMeters: number): ContactRecord {
  return {
    id,
    geom1: "link_col",
    geom2: "wall_col",
    distMeters,
    marginMeters: 0.02,
    point: [0, 0, 0],
  };
}

describe("CG-G-S12e: intrusion/imminent highlight", () => {
  it("highlights a penetrating contact as intrusion", () => {
    const { container } = render(<ContactList contacts={[contact("a", -0.003)]} />);
    const row = container.querySelector('[data-contact="a"]')!;
    expect(row.getAttribute("data-severity")).toBe("intrusion");
    expect(row.className).toContain("oa-contact__row--intrusion");
  });

  it("highlights a contact inside the margin as imminent", () => {
    const { container } = render(<ContactList contacts={[contact("b", 0.01)]} />);
    const row = container.querySelector('[data-contact="b"]')!;
    expect(row.getAttribute("data-severity")).toBe("imminent");
    expect(row.className).toContain("oa-contact__row--imminent");
  });

  it("does not highlight a contact beyond the margin", () => {
    const { container } = render(<ContactList contacts={[contact("c", 0.09)]} />);
    const row = container.querySelector('[data-contact="c"]')!;
    expect(row.getAttribute("data-severity")).toBe("clear");
    expect(row.className).not.toContain("oa-contact__row--intrusion");
    expect(row.className).not.toContain("oa-contact__row--imminent");
  });
});
