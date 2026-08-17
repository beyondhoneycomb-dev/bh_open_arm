// Put the operator's theme choice where the stylesheets look for it.
//
// Every rule in this build that reads the choice is written `:root[data-theme="dark"]`, and
// `:root` is `<html>` — a node React does not render. So the attribute is written imperatively
// here rather than as a prop on a shell div, which is where it used to sit and where no selector
// could ever see it.
//
// `system` writes nothing. That is the state in which `prefers-color-scheme` is meant to decide,
// and an attribute would be a third answer stacked on top of the two that already exist.

import { useEffect } from "react";

import type { ThemeConfig } from "../config/schema";

export const DOCUMENT_THEME_ATTRIBUTE = "data-theme";

const SYSTEM_MODE = "system";

interface DocumentThemeProps {
  mode: ThemeConfig["mode"];
}

// Renders nothing. It exists to own the attribute's lifetime: the node it writes to outlives
// React, so the removal has to be tied to something React does unmount.
export function DocumentTheme({ mode }: DocumentThemeProps) {
  useEffect(() => {
    const root = document.documentElement;
    if (mode === SYSTEM_MODE) {
      root.removeAttribute(DOCUMENT_THEME_ATTRIBUTE);
      return undefined;
    }
    root.setAttribute(DOCUMENT_THEME_ATTRIBUTE, mode);
    return () => root.removeAttribute(DOCUMENT_THEME_ATTRIBUTE);
  }, [mode]);

  return null;
}
