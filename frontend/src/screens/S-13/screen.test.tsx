// The default-export screen wires the four views over an injected data source and
// shows honest loading / error / ready states — an unavailable backend is not
// drawn as if it were fine.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import SystemScreen from "./screen";
import { REQUIRED_ITEM_IDS } from "./diagnosticBundle";
import { loadErrorRegistry, loadPortCanon } from "./testSupport";
import type { SystemData, SystemDataSource } from "./types";

function systemData(): SystemData {
  return {
    ports: {
      canon: loadPortCanon(),
      actual: [{ component: "web_backend", port: 1, pid: 1, listening: true }],
    },
    rt: {
      env: { kernelRelease: "6.8.0-rt", preemptRt: true, pythonVersion: "3.11.9" },
      processes: [
        {
          pid: 4242,
          name: "openarm-backend",
          schedPolicy: "SCHED_FIFO",
          schedPriority: 80,
          cpuAffinity: [2, 3],
          vmlckKb: 2048,
          mlockallReturnedOk: true,
        },
      ],
      findings: [],
    },
    bundle: { includedItemIds: [...REQUIRED_ITEM_IDS], includeVideo: false, includePii: false },
    errorRegistry: loadErrorRegistry(),
  };
}

function sourceOf(data: SystemData): SystemDataSource {
  return { load: () => Promise.resolve(data) };
}

describe("SystemScreen composition", () => {
  it("renders all four views once the source resolves", async () => {
    render(<SystemScreen source={sourceOf(systemData())} />);
    expect(await screen.findByTestId("port-compare")).toBeInTheDocument();
    expect(screen.getByTestId("rt-check")).toBeInTheDocument();
    expect(screen.getByTestId("diagnostic-bundle")).toBeInTheDocument();
    expect(screen.getByTestId("error-lookup")).toBeInTheDocument();
  });

  it("shows a loading state while the source is pending", () => {
    const pending: SystemDataSource = { load: () => new Promise<SystemData>(() => {}) };
    render(<SystemScreen source={pending} />);
    expect(screen.getByTestId("system-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("port-compare")).toBeNull();
  });

  it("shows an explicit error state when the source rejects", async () => {
    const failing: SystemDataSource = { load: () => Promise.reject(new Error("backend down")) };
    render(<SystemScreen source={failing} />);
    expect(await screen.findByTestId("system-error")).toHaveTextContent("backend down");
  });
});
