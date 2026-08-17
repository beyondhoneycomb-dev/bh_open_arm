// The one realtime client's lifetime, and what the shell shows while there is none.
//
// D-2 permits exactly one realtime socket, so the client is shell state rather than screen
// state: a per-screen hook would open a second socket on every navigation, and the second one
// would be a second stop path. It lives beside `ConfigProvider` for the same reason config does.
//
// What is asserted here is the lifetime and the honesty of the status, not the protocol —
// `wsClient.test.ts` owns the protocol. The status matters because every consumer of this
// context has to be able to tell "connected and quiet" from "never connected", and a provider
// that reported one for the other would let a screen render a lease it does not have.

import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RealtimeProvider, useRealtime } from "./RealtimeContext";

function Probe() {
  const { status, client } = useRealtime();
  return (
    <div>
      <span data-testid="status">{status}</span>
      <span data-testid="has-client">{client ? "yes" : "no"}</span>
    </div>
  );
}

function fakeClient() {
  return { start: vi.fn(), dispose: vi.fn() };
}

describe("RealtimeProvider", () => {
  it("starts the client it was given", () => {
    const client = fakeClient();

    render(
      <RealtimeProvider createClient={() => client}>
        <Probe />
      </RealtimeProvider>,
    );

    expect(client.start).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("status").textContent).toBe("open");
    expect(screen.getByTestId("has-client").textContent).toBe("yes");
  });

  it("opens exactly one socket for the shell", () => {
    // `CTR-WS@v2` D-2 permits one realtime channel. A second would also be a second stop path,
    // which `WP-3B-15` classifies FAIL_BLOCKING.
    const created: unknown[] = [];
    const createClient = () => {
      const client = fakeClient();
      created.push(client);
      return client;
    };

    const view = render(
      <RealtimeProvider createClient={createClient}>
        <Probe />
      </RealtimeProvider>,
    );
    view.rerender(
      <RealtimeProvider createClient={createClient}>
        <Probe />
      </RealtimeProvider>,
    );

    expect(created).toHaveLength(1);
  });

  it("disposes the client when the shell unmounts", () => {
    // A client that outlived the shell would hold a socket and keep renewing a lease for a page
    // nobody is looking at — and the lease is what keeps the arm live.
    const client = fakeClient();

    const view = render(
      <RealtimeProvider createClient={() => client}>
        <Probe />
      </RealtimeProvider>,
    );
    view.unmount();

    expect(client.dispose).toHaveBeenCalledTimes(1);
  });

  it("reports absence rather than a silent failure when the client cannot be built", () => {
    // The browser refuses a plaintext socket from a TLS page, and `realtimeUrl` refuses a
    // missing session id. Either throws here, and a provider that swallowed it would leave every
    // consumer reading an empty lease that looks like an idle rig.
    const client = fakeClient();
    client.start.mockImplementation(() => {
      throw new Error("no socket");
    });

    render(
      <RealtimeProvider createClient={() => client}>
        <Probe />
      </RealtimeProvider>,
    );

    expect(screen.getByTestId("status").textContent).toBe("unavailable");
    expect(screen.getByTestId("has-client").textContent).toBe("no");
  });

  it("refuses a consumer outside the provider", () => {
    // The same guard `useConfig` carries: a hook returning a null client would let a screen
    // render as though the socket were merely quiet.
    expect(() => render(<Probe />)).toThrow(/RealtimeProvider/);
  });
});
