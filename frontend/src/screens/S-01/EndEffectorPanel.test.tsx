// The wired control against a stand-in backend: the choices come from
// GET /api/config/tools, a pick is written as a PUT of the endEffector subobject
// alone, and a refused write leaves the control showing what the backend holds.

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfigProvider } from "../../app/ConfigContext";
import type { FetchLike } from "../../config/client";
import { CONFIG_ENDPOINT, CONFIG_TOOLS_ENDPOINT } from "../../config/endpoints";
import type { EndEffectorConfig } from "../../config/schema";
import { EndEffectorPanel } from "./EndEffectorPanel";
import { SAVE_FAILED_TEXT } from "./endEffector";

const REGISTRY = [
  { toolId: "fixed_spatula", label: "고정 스페츌러", gripperMotor: false },
  { toolId: "gripper", label: "v2 핀치 그리퍼", gripperMotor: true },
];

const END_EFFECTOR_WRITE_URL = `${CONFIG_ENDPOINT}/endEffector`;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

interface StandInBackend {
  fetchImpl: FetchLike;
  calls: Array<{ url: string; method: string; body: unknown }>;
}

// A backend that serves the config document and the tool registry, and accepts or
// refuses the subobject write. `writeStatus` is what the PUT answers with.
function standInBackend(endEffector: EndEffectorConfig, writeStatus = 200): StandInBackend {
  const document: Record<string, unknown> = {
    layout: { sidebarCollapsed: false, density: "comfortable" },
    presets: { viewPresets: {} },
    endEffector,
  };
  const calls: StandInBackend["calls"] = [];

  const fetchImpl = vi.fn(async (input: unknown, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = typeof init?.body === "string" ? JSON.parse(init.body) : null;
    calls.push({ url, method, body });

    if (url === CONFIG_TOOLS_ENDPOINT) {
      return jsonResponse(REGISTRY);
    }
    if (url === END_EFFECTOR_WRITE_URL && method === "PUT") {
      if (writeStatus === 200) {
        document.endEffector = body;
      }
      return jsonResponse(document, writeStatus);
    }
    if (url === CONFIG_ENDPOINT && method === "GET") {
      return jsonResponse(document);
    }
    return jsonResponse({ detail: "unrouted" }, 404);
  });

  return { fetchImpl: fetchImpl as unknown as FetchLike, calls };
}

function renderPanel(backend: StandInBackend) {
  return render(
    <ConfigProvider fetchImpl={backend.fetchImpl}>
      <EndEffectorPanel fetchImpl={backend.fetchImpl} />
    </ConfigProvider>,
  );
}

function radio(container: HTMLElement, side: string, toolId: string): HTMLInputElement {
  return container.querySelector<HTMLInputElement>(
    `[data-ee-choice="${side}:${toolId}"] input[type="radio"]`,
  )!;
}

const bothSpatula: EndEffectorConfig = {
  left: { toolId: "fixed_spatula", toolMassKg: null },
  right: { toolId: "fixed_spatula", toolMassKg: null },
};

describe("wired end-effector control", () => {
  it("renders the choices the backend registry sent", async () => {
    const backend = standInBackend(bothSpatula);
    renderPanel(backend);

    for (const tool of REGISTRY) {
      expect((await screen.findAllByText(tool.label)).length).toBeGreaterThan(0);
    }
    expect(backend.calls.some((call) => call.url === CONFIG_TOOLS_ENDPOINT)).toBe(true);
  });

  it("writes the chosen tool as the endEffector subobject alone", async () => {
    const backend = standInBackend(bothSpatula);
    const { container } = renderPanel(backend);

    await screen.findByTestId("ee-arm-left");
    fireEvent.click(radio(container, "left", "gripper"));

    await waitFor(() => {
      expect(backend.calls.some((call) => call.url === END_EFFECTOR_WRITE_URL)).toBe(true);
    });
    const write = backend.calls.find((call) => call.url === END_EFFECTOR_WRITE_URL)!;
    expect(write.method).toBe("PUT");
    expect(write.body).toEqual({
      left: { toolId: "gripper", toolMassKg: null },
      right: { toolId: "fixed_spatula", toolMassKg: null },
    });
    // Nothing else was written. Stated as "no other subobject path" rather than by naming
    // one: the panel owns endEffector alone, and a check that lists its siblings stops
    // covering the rule the moment a sibling is added or removed.
    const otherWrites = backend.calls.filter(
      (call) =>
        call.method === "PUT" &&
        call.url.startsWith(`${CONFIG_ENDPOINT}/`) &&
        call.url !== END_EFFECTOR_WRITE_URL,
    );
    expect(otherWrites).toEqual([]);

    await waitFor(() => {
      expect(radio(container, "left", "gripper").checked).toBe(true);
    });
    expect(radio(container, "right", "gripper").checked).toBe(false);
  });

  it("clears the mass when the tool changes, and writes nothing when it does not", async () => {
    const backend = standInBackend({
      left: { toolId: "fixed_spatula", toolMassKg: 0.4 },
      right: { toolId: "fixed_spatula", toolMassKg: null },
    });
    const { container } = renderPanel(backend);

    await screen.findByTestId("ee-arm-left");

    // Re-picking the fitted tool must not discard the measurement.
    fireEvent.click(radio(container, "left", "fixed_spatula"));
    await waitFor(() => {
      expect(screen.getByTestId("ee-mass-left")).toHaveAttribute("data-mass-measured", "true");
    });
    expect(backend.calls.some((call) => call.url === END_EFFECTOR_WRITE_URL)).toBe(false);

    // Swapping the tool invalidates it: the measurement belonged to the old tool.
    fireEvent.click(radio(container, "left", "gripper"));
    await waitFor(() => {
      expect(backend.calls.some((call) => call.url === END_EFFECTOR_WRITE_URL)).toBe(true);
    });
    const write = backend.calls.find((call) => call.url === END_EFFECTOR_WRITE_URL)!;
    expect(write.body).toEqual({
      left: { toolId: "gripper", toolMassKg: null },
      right: { toolId: "fixed_spatula", toolMassKg: null },
    });
  });

  it("keeps showing the stored tool when the write is refused", async () => {
    const backend = standInBackend(bothSpatula, 400);
    const { container } = renderPanel(backend);

    await screen.findByTestId("ee-arm-left");
    fireEvent.click(radio(container, "left", "gripper"));

    expect(await screen.findByTestId("ee-save-notice")).toHaveTextContent(SAVE_FAILED_TEXT);
    expect(radio(container, "left", "gripper").checked).toBe(false);
    expect(radio(container, "left", "fixed_spatula").checked).toBe(true);
  });

  it("offers no choices when the tool registry cannot be read", async () => {
    const backend = standInBackend(bothSpatula);
    const refusingTools = vi.fn(async (input: unknown, init?: RequestInit) => {
      if (String(input) === CONFIG_TOOLS_ENDPOINT) {
        return jsonResponse({ detail: "registry unavailable" }, 503);
      }
      return (backend.fetchImpl as unknown as (i: unknown, n?: RequestInit) => Promise<Response>)(
        input,
        init,
      );
    });

    const { container } = render(
      <ConfigProvider fetchImpl={backend.fetchImpl}>
        <EndEffectorPanel fetchImpl={refusingTools as unknown as FetchLike} />
      </ConfigProvider>,
    );

    await screen.findByTestId("ee-tools-notice");
    expect(container.querySelectorAll('input[type="radio"]').length).toBe(0);
  });
});

// Writing one arm must not disturb the other. Clearing both arms' toolMassKg on a single-arm
// write kept the whole suite green, because every other fixture already carries null on the
// untouched arm — so the fixture here deliberately gives the untouched arm a measured mass and
// a non-default tool. A cleared mass is not cosmetic: it is the number gravity compensation
// subtracts, and losing it reappears as a standing offset in the collision residual.
describe("writing one arm leaves the other arm's record alone", () => {
  it("preserves the sibling arm's tool and its measured mass", async () => {
    const backend = standInBackend({
      left: { toolId: "fixed_spatula", toolMassKg: null },
      right: { toolId: "gripper", toolMassKg: 1.37 },
    });
    const { container } = renderPanel(backend);
    await screen.findByTestId("ee-arm-left");

    fireEvent.click(radio(container, "left", "gripper"));

    await waitFor(() => {
      const put = backend.calls.find((call) => call.method === "PUT");
      expect(put).toBeDefined();
      const sent = put?.body as EndEffectorConfig;
      expect(sent.left.toolId).toBe("gripper");
      expect(sent.right.toolId).toBe("gripper");
      expect(sent.right.toolMassKg).toBe(1.37);
    });
  });
});
