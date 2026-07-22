// Mounts a route's screen: the sibling WP's component when one is registered,
// otherwise the placeholder scaffold. Suspense covers the lazy sibling import.

import { Suspense } from "react";

import { resolveScreen } from "../routes/screenResolver";
import type { ScreenDescriptor } from "../routes/registry";
import { ScreenScaffold } from "./ScreenScaffold";

interface ScreenMountProps {
  screen: ScreenDescriptor;
}

export function ScreenMount({ screen }: ScreenMountProps) {
  const Screen = resolveScreen(screen.id);
  if (!Screen) {
    return <ScreenScaffold screen={screen} />;
  }
  return (
    <Suspense fallback={<ScreenScaffold screen={screen} />}>
      <Screen />
    </Suspense>
  );
}
