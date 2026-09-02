// The one realtime client, held by the shell for the life of the page.
//
// `CTR-WS@v2` D-2 permits exactly one realtime channel, so the client is shell state and not
// screen state: a per-screen hook would open a socket per navigation, and a second realtime path
// is also a second stop path — which `WP-3B-15` ⑤ classifies FAIL_BLOCKING. It sits beside
// `ConfigProvider` for the same reason config does, and follows its shape so there is one
// context idiom in this shell rather than two.
//
// The status is three-valued on purpose. A consumer has to be able to tell a socket that is open
// and quiet from one that was never built, because the two render identically from the data: an
// empty lease, no telemetry, nothing moving. A provider that reported "open" for a client it
// could not construct would let a screen show an idle rig it is not connected to.

import type { LinkRefusal } from "../ws/closeCodes";
import { readTelemetry, type TelemetryView } from "../ws/telemetryView";
import type { DecodedTextFrame } from "../ws/types";
import type { LeaseSnapshot } from "../ws/leaseRenewer";
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

// The part of the client this shell drives. Narrower than `WsClient` so the provider can be
// exercised without the real Worker and the browser WebSocket, and so nothing here reaches a
// send path — sending is a screen's business, through the client it reads off this context.
export interface RealtimeLifecycle {
  start(): void;
  dispose(): void;
  // The lease the renewer tracks. Optional because this provider drives the lifetime and a
  // double that only needs to be started and disposed should not have to carry one.
  readonly lease?: { snapshot(): LeaseSnapshot };
}

export type RealtimeStatus = "open" | "unavailable";

// What the provider hands the factory. The one thing the shell needs back from a client it
// otherwise only starts and disposes: the server refused this connection and will refuse the
// next one, so nothing below can go on drawing a channel.
export interface RealtimeClientHooks {
  onLinkRefused: (refusal: LinkRefusal) => void;
  // Every telemetry frame, as it arrives. The provider keeps the last one so a screen
  // mounted mid-stream renders the current state rather than waiting for the next frame.
  onTelemetry: (frame: DecodedTextFrame) => void;
}

export interface RealtimeContextValue<TClient extends RealtimeLifecycle = RealtimeLifecycle> {
  // The live client, or null when one could not be built. Null is not "not yet" — the provider
  // builds it synchronously on mount — it is "there is no realtime channel on this page".
  client: TClient | null;
  status: RealtimeStatus;
  // Why there is no client, for the surface that tells the operator. Null while one exists.
  reason: string | null;
  // The last telemetry frame read, or null when none has arrived. Null is "the server has
  // sent nothing", which is what a process holding no arm does — not "the arm reads zero".
  telemetry: TelemetryView | null;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

interface RealtimeProviderProps<TClient extends RealtimeLifecycle> {
  children: ReactNode;
  // How to build the client. Injected rather than imported so this provider can be rendered in a
  // lane with no Worker global, and so a host that wants a different role or session supplies it
  // at the one place the client is made. The hooks are passed in rather than read back off the
  // client because a refusal happens once and never changes: a reader would have to be polled
  // to catch it, and the poll would run for the whole life of a page to observe one event.
  createClient: (hooks: RealtimeClientHooks) => TClient;
}

export function RealtimeProvider<TClient extends RealtimeLifecycle>({
  children,
  createClient,
}: RealtimeProviderProps<TClient>) {
  // Built once and kept, never rebuilt on re-render: `useState`'s initialiser runs on mount
  // only, so a parent re-rendering cannot open a second socket. That is the D-2 guarantee, and
  // it is structural here rather than a rule someone has to remember.
  const [refused, setRefused] = useState<LinkRefusal | null>(null);
  const [built] = useState<{ client: TClient | null; reason: string | null }>(() => {
    try {
      return {
        client: createClient({
          onLinkRefused: setRefused,
          // A frame that does not parse leaves the last one standing: replacing a good
          // reading with a blank is how a screen reports a healthy arm as absent.
          onTelemetry: (frame) => {
            const view = readTelemetry(frame);
            if (view !== null) {
              setTelemetry(view);
            }
          },
        }),
        reason: null,
      };
    } catch (error) {
      return { client: null, reason: String(error) };
    }
  });
  const [failed, setFailed] = useState<string | null>(null);
  const [telemetry, setTelemetry] = useState<TelemetryView | null>(null);

  useEffect(() => {
    const client = built.client;
    if (!client) {
      return undefined;
    }
    try {
      client.start();
    } catch (error) {
      // A start that throws leaves no channel, and saying "open" here is the failure this
      // status exists to prevent.
      setFailed(String(error));
      return undefined;
    }
    return () => client.dispose();
  }, [built]);

  const value = useMemo<RealtimeContextValue<TClient>>(() => {
    const reason = built.reason ?? failed ?? refusalReason(refused);
    return {
      client: reason === null ? built.client : null,
      status: reason === null && built.client !== null ? "open" : "unavailable",
      reason,
      // Cleared with the channel: a frame kept after the link went away is a reading the
      // screen would go on showing while nothing is arriving to replace it.
      telemetry: reason === null ? telemetry : null,
    };
  }, [built, failed, refused, telemetry]);

  return (
    <RealtimeContext.Provider value={value as RealtimeContextValue}>
      {children}
    </RealtimeContext.Provider>
  );
}

// The refusal in the server's own words, prefixed with its close code. Both halves are kept:
// the reason is what a person can act on, and the code is what they can match against the
// server log. An empty reason is a server that sent none, not a reason worth inventing.
function refusalReason(refusal: LinkRefusal | null): string | null {
  if (refusal === null) {
    return null;
  }
  return refusal.reason === "" ? String(refusal.code) : `${refusal.code}: ${refusal.reason}`;
}

export function useRealtime(): RealtimeContextValue {
  const value = useContext(RealtimeContext);
  if (!value) {
    throw new Error("useRealtime must be used within a RealtimeProvider");
  }
  return value;
}
