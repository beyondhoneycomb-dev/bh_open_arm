// Backend-provided system/operations state the S-13 window renders. Every shape
// here is data the FastAPI backend serves (host reads of chrt/VmLck/ip -s link,
// the runtime port bindings, the frozen error registry). S-13 is a facade: it
// holds NONE of the canon. The port map, the RT policy, the error-code table, and the
// diagnostic-bundle contents are all backend-owned; this file only names the
// wire shapes so the browser can render them and never re-source them.

// One row of the port-map CANON. The canon is the union of 01 §2.17 + 14 §2.1
// (13 §2.7); the backend serves it and S-13 must not author a third copy. A null
// port is a component with no network boundary (e.g. the inprocess backend<->HW
// hop), declared so the compare view can show "no port expected" rather than a
// spurious mismatch.
export interface CanonPortEntry {
  component: string;
  protocol: string;
  port: number | null;
}

// One actual socket binding, from the backend's runtime port map (ports.json,
// 14 §2.11) — what is really listening, parsed from the host (WP-0B-02 `ip link`).
export interface ActualBinding {
  component: string;
  port: number;
  pid: number | null;
  listening: boolean;
}

// The kernel/runtime facts the diagnostic bundle reports (14 FR-OPS-023). Read by
// the backend; rendered here. `preemptRt` false is the CG-G-S13g condition.
export interface RtEnvironment {
  kernelRelease: string;
  preemptRt: boolean;
  pythonVersion: string;
}

// One process's realtime posture, from the backend's host reads. `vmlckKb` is the
// /proc/<pid>/status VmLck value — the ONLY trusted evidence that mlockall took
// effect (14 FR-OPS-023). `mlockallReturnedOk` is the raw syscall return, kept
// separately precisely so the browser can show it disagreeing with VmLck.
export interface ProcessRtStatus {
  pid: number;
  name: string;
  schedPolicy: string;
  schedPriority: number;
  cpuAffinity: number[];
  vmlckKb: number;
  mlockallReturnedOk: boolean;
}

// A backend-declared RT deficiency carrying the OA-* code that names it. S-13 does
// not map conditions to codes (that is the backend's judgement); it renders the
// code the backend attached and looks its remedy up in the frozen registry.
export interface RtFinding {
  code: string;
  note: string | null;
}

export interface RtCheckData {
  env: RtEnvironment;
  processes: ProcessRtStatus[];
  findings: RtFinding[];
}

// The manifest of a diagnostic bundle the backend generated or would generate:
// which required items it contains, and the user's video/PII inclusion choices.
export interface BundleManifest {
  includedItemIds: string[];
  includeVideo: boolean;
  includePii: boolean;
}

// One OA-* code as the frozen registry (contracts/errors/error_registry.yaml,
// canon 14 §2.10) defines it. The browser renders these fields and authors none.
export interface ErrorRegistryEntry {
  code: string;
  severity: number;
  messageKo: string;
  messageEn: string;
  recoveryHint: string;
  docUrl: string;
  subsystem: string;
}

export type ErrorRegistry = Record<string, ErrorRegistryEntry>;

// The whole S-13 payload the backend serves in one shot.
export interface SystemData {
  ports: {
    canon: CanonPortEntry[];
    actual: ActualBinding[];
  };
  rt: RtCheckData;
  bundle: BundleManifest;
  errorRegistry: ErrorRegistry;
}

// The data seam. The default implementation fetches same-origin REST; tests
// inject a deterministic source built over the 3A-style fixtures, so no code path
// here reaches a real backend or hardware.
export interface SystemDataSource {
  load(): Promise<SystemData>;
}
