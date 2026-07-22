import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DummyModeBanner } from "./DummyModeBanner";

describe("DummyModeBanner (FR-GUI-070)", () => {
  it("shows a clear alert banner in dummy mode", () => {
    render(<DummyModeBanner dummyMode />);
    const banner = screen.getByRole("alert");
    expect(banner).toHaveTextContent(/더미 모드/);
    expect(banner).toHaveTextContent(/하드웨어 없음/);
  });

  it("renders nothing when hardware is present", () => {
    const { container } = render(<DummyModeBanner dummyMode={false} />);
    expect(container).toBeEmptyDOMElement();
  });
});
