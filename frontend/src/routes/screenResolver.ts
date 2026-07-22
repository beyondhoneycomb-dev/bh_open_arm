// Screen plug-in contract for sibling WPs. A screen WP (WP-G-S01..S13) mounts
// its screen by adding `src/screens/<ScreenId>/screen.tsx` that default-exports a
// React component; the shell discovers it at build time and routes to it. Until
// a screen exists its route renders a placeholder. The shell never imports a
// sibling file by name and a sibling never edits the shell — this discovery glob
// is the entire coupling, which keeps the ownership boundary clean (CI-02).

import { lazy, type ComponentType, type LazyExoticComponent } from "react";

import type { ScreenId } from "./registry";

type ScreenModule = { default: ComponentType };
type ModuleLoader = () => Promise<ScreenModule>;

// Empty until a sibling adds a screen module; import.meta.glob resolves to an
// empty map while src/screens/ has no matching files.
const discovered = import.meta.glob("../screens/*/screen.tsx") as unknown as Record<
  string,
  ModuleLoader
>;

const SCREEN_PATH = /\.\.\/screens\/([^/]+)\/screen\.tsx$/;

function screenIdFromModulePath(path: string): string | null {
  const match = path.match(SCREEN_PATH);
  return match ? match[1] : null;
}

const LOADERS: Partial<Record<ScreenId, ModuleLoader>> = {};
for (const [path, loader] of Object.entries(discovered)) {
  const id = screenIdFromModulePath(path);
  if (id) {
    LOADERS[id as ScreenId] = loader;
  }
}

// A sibling's screen component when one is registered, else null so the route
// falls back to the placeholder scaffold.
export function resolveScreen(id: ScreenId): LazyExoticComponent<ComponentType> | null {
  const loader = LOADERS[id];
  return loader ? lazy(loader) : null;
}

export function registeredScreenIds(): ScreenId[] {
  return Object.keys(LOADERS) as ScreenId[];
}
