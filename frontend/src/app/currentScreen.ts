// Route path -> screen id, for the one consumer that needs to name the screen the
// operator is on (the safety bar's display context). The registry is the canon; this
// only reads it, so the mapping cannot drift from the 13 §2.6 inventory.

import { SCREENS, type ScreenId } from "../routes/registry";

// The screen owning this path, or null when the path is not one of the 13 screens —
// /viewport and unknown paths have no screen id, and inventing one would report a
// screen the operator is not on.
export function screenIdForPath(pathname: string): ScreenId | null {
  const found = SCREENS.find((screen) => screen.paths.includes(pathname));
  return found ? found.id : null;
}
