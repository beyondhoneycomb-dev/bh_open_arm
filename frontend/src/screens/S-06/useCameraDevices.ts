// The live device set behind S-06's assignment panel.
//
// The screen renders from a `source` prop with an offline fixture default, which
// is what makes it verifiable with no backend. This hook is the other half: when
// the screen is mounted for real, the discovered list and the three assignment
// intents come from here instead.
//
// **A failed scan shows no cameras, never the fixture.** Falling back to the
// fixture would put three plausible rows on screen while the backend is gone,
// and the operator would assign slots against cameras that are not there. The
// error is rendered instead, which is the only outcome they can act on.

import { useCallback, useEffect, useState } from "react";
import {
  CameraRequestError,
  assignDevice,
  releaseSlot,
  scanDevices,
  type CameraScan,
} from "./deviceClient";
import type { DiscoveredCamera } from "./source";

export interface LiveCameraDevices {
  // Null until the first scan lands. The panel keeps rendering the fixture until
  // then; a scan is one request and the gap is short.
  readonly scan: CameraScan | null;
  // The reason the last call failed, or null. Rendered, never swallowed.
  readonly error: string | null;
  readonly rescan: () => void;
  readonly assign: (portPath: string, slot: string) => void;
  readonly release: (portPath: string) => void;
}

function messageOf(failure: unknown): string {
  if (failure instanceof CameraRequestError) {
    return failure.message;
  }
  // A rejected fetch means the request never reached a backend at all — a
  // different diagnosis from a backend that answered a refusal, so it is said
  // differently rather than folded into the same line.
  return failure instanceof Error
    ? `백엔드에 닿지 않는다: ${failure.message}`
    : "백엔드에 닿지 않는다";
}

// Which slot a device fills, from the scan the backend last answered. The panel
// releases by port; the backend keys the record by slot, and this is the crossing.
function slotOf(scan: CameraScan | null, portPath: string): string | null {
  const device = scan?.devices.find((candidate: DiscoveredCamera) => candidate.portPath === portPath);
  return device?.assignedSlot ?? null;
}

export function useCameraDevices(enabled: boolean): LiveCameraDevices {
  const [scan, setScan] = useState<CameraScan | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = useCallback(
    (call: () => Promise<CameraScan>) => {
      if (!enabled) {
        return;
      }
      call().then(
        (next) => {
          setScan(next);
          setError(null);
        },
        (failure: unknown) => {
          // The scan is cleared, not kept. A stale list after a failed call is a
          // list of cameras that may no longer be there, presented as current.
          setScan(null);
          setError(messageOf(failure));
        },
      );
    },
    [enabled],
  );

  useEffect(() => {
    run(scanDevices);
  }, [run]);

  const rescan = useCallback(() => run(scanDevices), [run]);

  const assign = useCallback(
    (portPath: string, slot: string) => run(() => assignDevice(portPath, slot)),
    [run],
  );

  const release = useCallback(
    (portPath: string) => {
      const slot = slotOf(scan, portPath);
      if (slot === null) {
        return;
      }
      run(() => releaseSlot(slot));
    },
    [run, scan],
  );

  return { scan, error, rescan, assign, release };
}
