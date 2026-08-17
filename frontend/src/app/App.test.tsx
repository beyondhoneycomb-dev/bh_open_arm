// The composition root holds the one realtime client.
//
// Every piece of the WS stack existed before this and nothing constructed it, so the whole of it
// — the client, the lease renewer, the priority queues, the decode worker — was code with no
// caller. Mounting the provider at the root is what makes it reachable, and the root is where it
// belongs: `CTR-WS@v2` D-2 permits one realtime socket, and a provider inside the router would
// be rebuilt by navigation.
//
// The client factory is injected the same way `ConfigProvider` takes its `fetchImpl`, so this
// asserts the real lifetime rather than the shape of the source.

import { render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { App } from "./App";

function stubConfigFetch() {
  // The shell loads runtime config on mount. What it returns does not matter here; what matters
  // is that no test reaches a real backend.
  return vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({}),
  } as unknown as Response);
}

describe("App", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", stubConfigFetch());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("starts one realtime client for the shell", () => {
    const client = { start: vi.fn(), dispose: vi.fn() };

    render(<App createRealtimeClient={() => client} />);

    expect(client.start).toHaveBeenCalledTimes(1);
  });

  it("disposes it when the shell goes away", () => {
    // A client outliving the page keeps a socket open and keeps renewing a lease nobody is
    // watching — and the lease is what keeps the arm live.
    const client = { start: vi.fn(), dispose: vi.fn() };

    render(<App createRealtimeClient={() => client} />).unmount();

    expect(client.dispose).toHaveBeenCalledTimes(1);
  });
});
