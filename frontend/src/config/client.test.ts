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
        control: { controlTickHz: 120 },
        presets: { viewPresets: {} },
      }),
    );

    const { config, defaulted } = await fetchConfig(asFetch(fetchImpl));

    expect(fetchImpl).toHaveBeenCalledWith(
      CONFIG_ENDPOINT,
      expect.objectContaining({ method: "GET" }),
    );
    expect(defaulted).toEqual([]);
    expect(config.control.controlTickHz).toBe(120);
    expect(config.layout.density).toBe("compact");
  });

  it("isolates a malformed subobject in the GET response", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ layout: { sidebarCollapsed: false, density: "comfortable" }, control: 7 }),
    );

    const { config, defaulted } = await fetchConfig(asFetch(fetchImpl));

    expect(defaulted).toEqual(["control"]);
    expect(config.layout.density).toBe("comfortable");
  });

  it("PUTs exactly one subobject to its own path, then re-reads the canon", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({
        layout: { sidebarCollapsed: true, density: "comfortable" },
        control: { controlTickHz: 100 },
        presets: { viewPresets: {} },
      }),
    );

    await saveSubobject(
      "layout",
      { sidebarCollapsed: true, density: "comfortable" },
      asFetch(fetchImpl),
    );

    const [writeUrl, write] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(writeUrl).toBe(`${CONFIG_ENDPOINT}/layout`);
    expect(write.method).toBe("PUT");
    // The subobject alone — no sibling subobject travels with it.
    expect(JSON.parse(write.body as string)).toEqual({
      sidebarCollapsed: true,
      density: "comfortable",
    });

    const [readUrl, read] = fetchImpl.mock.calls[1] as unknown as [string, RequestInit];
    expect(readUrl).toBe(CONFIG_ENDPOINT);
    expect(read.method).toBe("GET");
  });

  it("throws ConfigRequestError when the write is refused, and does not re-read", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ detail: "unknown tool" }, 400));

    await expect(
      saveSubobject(
        "endEffector",
        {
          left: { toolId: "no_such_tool", toolMassKg: null },
          right: { toolId: "fixed_spatula", toolMassKg: null },
        },
        asFetch(fetchImpl),
      ),
    ).rejects.toBeInstanceOf(ConfigRequestError);
    expect(fetchImpl).toHaveBeenCalledTimes(1);
  });

  it("throws ConfigRequestError on a non-ok response", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({}, 500));
    await expect(fetchConfig(asFetch(fetchImpl))).rejects.toBeInstanceOf(ConfigRequestError);
  });
});
