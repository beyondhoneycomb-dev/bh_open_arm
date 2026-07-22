// The default S-13 data source: one same-origin REST read of the backend's
// system report. The path is relative, so the browser never names an external
// origin (air-gap, FR-GUI-008) and never a port (the port map is the backend's,
// not a literal here). `fetch` is injectable so the screen's loading/error paths
// are driven deterministically in the lane, with no real backend reached.

import type { SystemData, SystemDataSource } from "./types";

export type FetchLike = typeof fetch;

// Same-origin REST endpoint the FastAPI backend serves the S-13 report from.
// Relative by construction — served by the one backend on the SPA-serving port.
export const SYSTEM_REPORT_ENDPOINT = "/api/system/report";

export class SystemReportError extends Error {
  readonly status: number;

  constructor(status: number, statusText: string) {
    super(`system report request failed: ${status} ${statusText}`);
    this.name = "SystemReportError";
    this.status = status;
  }
}

export function createDefaultSource(fetchImpl: FetchLike = fetch): SystemDataSource {
  return {
    async load(): Promise<SystemData> {
      const response = await fetchImpl(SYSTEM_REPORT_ENDPOINT, {
        method: "GET",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) {
        throw new SystemReportError(response.status, response.statusText);
      }
      return (await response.json()) as SystemData;
    },
  };
}
