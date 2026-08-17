// The shell's control-lease surface, fed from the one realtime client.
//
// First thing in this build to draw live realtime state. What it must not do is render an absent
// channel as a quiet one: `client: null` and "connected, holding no lease yet" produce the same
// empty lease, and only one of them means asking for control could work at all. So the absent
// case gets its own line rather than an empty lease view.
//
// The snapshot is polled rather than subscribed. The dead-man margin counts down between frames,
// so this surface has to re-render on a clock whatever the socket does — a subscription would
// still need the same timer, and would add a second path for the same redraw.

import { useEffect, useState } from "react";

import { ControlLeaseView } from "../mode/ControlLeaseView";
import type { LeaseSnapshot } from "../ws/leaseRenewer";
import {
  leaseFromSnapshot,
  rejectReasonFromSnapshot,
  roleFromSnapshot,
  verdictFromSnapshot,
} from "./leaseView";
import { useRealtime } from "./RealtimeContext";

// How often the lease surface redraws. The dead-man margin is the thing that moves between
// frames and it is read in milliseconds, so a redraw a few times a second shows it falling
// without spending a frame budget on a `<dl>`.
const LEASE_POLL_MS = 250;

const NO_CHANNEL_NOTICE =
  "실시간 채널이 없습니다 — 리스 상태를 읽을 수 없고, 제어권을 요청할 수도 없습니다.";

export function ControlLeaseHost() {
  const { client, status, reason } = useRealtime();
  const [snapshot, setSnapshot] = useState<LeaseSnapshot | null>(null);

  useEffect(() => {
    const lease = client?.lease;
    if (!lease) {
      setSnapshot(null);
      return undefined;
    }
    const read = () => setSnapshot(lease.snapshot());
    read();
    const timer = window.setInterval(read, LEASE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [client]);

  if (status !== "open" || snapshot === null) {
    return (
      <p className="oa-lease__absent" role="status" data-testid="realtime-absent">
        {NO_CHANNEL_NOTICE}
        {reason !== null ? ` (${reason})` : null}
      </p>
    );
  }

  // The clock the view judges against. Expiry is the server's, and the browser never authors it;
  // reading the local clock for the server field would draw a margin computed across two
  // unrelated origins, so the display is against the moment the snapshot was taken.
  const now = performance.now();
  const rejected = rejectReasonFromSnapshot(snapshot);
  return (
    <>
      <ControlLeaseView
        lease={leaseFromSnapshot(snapshot)}
        clock={{ nowMonoServer: now, nowMonoClient: now }}
        role={roleFromSnapshot(snapshot)}
        lastVerdict={verdictFromSnapshot(snapshot)}
      />
      {rejected !== null && verdictFromSnapshot(snapshot) === null ? (
        // A refusal the view has no label for. Shown in the server's own words rather than
        // dropped — `rejected_latched` is one of these, and it is the one that tells the
        // operator the arm is held and a re-arm handshake is owed.
        <p className="oa-lease__verdict" role="alert">
          거부 사유: {rejected}
        </p>
      ) : null}
    </>
  );
}
