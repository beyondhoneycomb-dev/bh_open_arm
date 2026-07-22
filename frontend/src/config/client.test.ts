// REST config client: get/set go over HTTP against the same-origin endpoint, an
// injected fetch stands in for the backend, and blast-radius isolation applies to
// the GET response the same as a local parse.

import { describe, expect, it, vi } from "vitest";

import { ConfigRequestError, fetchConfig, saveSubobject, type FetchLike } from "./client";
import { CONFIG_ENDPOINT } from "./endpoints";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const asFetch = (mock: ReturnType<typeof vi.fn>): FetchLike => mock as unknown as FetchLike;

describe("REST config client", () => {
  it("GETs and parses the whole config", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({
        layout: { sidebarCollapsed: true, density: "compact" },
        theme: { mode: "dark" },
        presets: { viewPresets: {} },
      }),
    );

    const { config, defaulted } = await fetchConfig(asFetch(fetchImpl));

    expect(fetchImpl).toHaveBeenCalledWith(
      CONFIG_ENDPOINT,
      expect.objectContaining({ method: "GET" }),
    );
    expect(defaulted).toEqual([]);
    expect(config.theme.mode).toBe("dark");
    expect(config.layout.density).toBe("compact");
  });

  it("isolates a malformed subobject in the GET response", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ layout: { sidebarCollapsed: false, density: "comfortable" }, theme: 7 }),
    );

    const { config, defaulted } = await fetchConfig(asFetch(fetchImpl));

    expect(defaulted).toEqual(["theme"]);
    expect(config.layout.density).toBe("comfortable");
  });

  it("PATCHes exactly one subobject", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({
        layout: { sidebarCollapsed: true, density: "comfortable" },
        theme: { mode: "system" },
        presets: { viewPresets: {} },
      }),
    );

    await saveSubobject(
      "layout",
      { sidebarCollapsed: true, density: "comfortable" },
      asFetch(fetchImpl),
    );

    const [, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body as string)).toEqual({
      layout: { sidebarCollapsed: true, density: "comfortable" },
    });
  });

  it("throws ConfigRequestError on a non-ok response", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 500));
    await expect(fetchConfig(asFetch(fetchImpl))).rejects.toBeInstanceOf(ConfigRequestError);
  });
});
