// The theme the operator picked has to land where the stylesheets look for it.
//
// The shell stamped `data-theme` on its own div while every rule reading it is written
// `:root[data-theme="dark"]` — and `:root` is `<html>`. The attribute and the selector never met,
// so picking light or dark changed nothing on any screen and every one of them fell through to
// `prefers-color-scheme`, which is the operating system's choice and not the operator's.
//
// `system` writes no attribute at all, on purpose: that is the state in which the OS preference
// is meant to win, and an attribute would be a third answer sitting on top of it.

import { render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { DOCUMENT_THEME_ATTRIBUTE, DocumentTheme } from "./documentTheme";

afterEach(() => {
  document.documentElement.removeAttribute(DOCUMENT_THEME_ATTRIBUTE);
});

describe("DocumentTheme", () => {
  it("puts an explicit choice on the document element", () => {
    render(<DocumentTheme mode="dark" />);

    expect(document.documentElement.getAttribute(DOCUMENT_THEME_ATTRIBUTE)).toBe("dark");
  });

  it("puts light there too, so the toggle wins in both directions", () => {
    // Choosing light on a machine whose OS is dark has to override it. Writing the attribute
    // only for dark would make light mean "follow the OS", which is what `system` means.
    render(<DocumentTheme mode="light" />);

    expect(document.documentElement.getAttribute(DOCUMENT_THEME_ATTRIBUTE)).toBe("light");
  });

  it("writes nothing for system, leaving the OS preference to decide", () => {
    render(<DocumentTheme mode="system" />);

    expect(document.documentElement.hasAttribute(DOCUMENT_THEME_ATTRIBUTE)).toBe(false);
  });

  it("clears a previous choice when the operator goes back to system", () => {
    // A left-behind attribute is the worst of the three states: the screen shows a theme the
    // settings page says is not selected.
    const view = render(<DocumentTheme mode="dark" />);
    view.rerender(<DocumentTheme mode="system" />);

    expect(document.documentElement.hasAttribute(DOCUMENT_THEME_ATTRIBUTE)).toBe(false);
  });

  it("removes the attribute when the shell unmounts", () => {
    // The attribute outlives React otherwise: it is on a node React does not own.
    render(<DocumentTheme mode="dark" />).unmount();

    expect(document.documentElement.hasAttribute(DOCUMENT_THEME_ATTRIBUTE)).toBe(false);
  });
});
