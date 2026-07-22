// Port-map comparison (CG-G-S13a, CG-G-S13d). The port-map canon is NOT S-13's:
// 13 §2.7 fixes it as the union of 01 §2.17 + 14 §2.1, the backend serves it, and
// this module only DIFFS a backend-served canon against the backend-served actual
// bindings. There is deliberately not one port literal in this file — a hardcoded
// port number here would be the third canon 13 §2.7 forbids. Every number this
// module reasons about arrives as a parameter.

import type { ActualBinding, CanonPortEntry } from "./types";

// A row's verdict after lining the canon up against what is really bound.
export type PortRowStatus =
  | "match" // canon expects a port and exactly that port is bound
  | "mismatch" // canon expects a port but a different one is bound
  | "unbound" // canon expects a port and nothing is bound
  | "unexpected" // something is bound for a component the canon does not list
  | "no_port"; // canon declares no network port for this component

export interface PortComparisonRow {
  component: string;
  protocol: string | null;
  canonPort: number | null;
  actualPort: number | null;
  status: PortRowStatus;
}

// Two or more components bound to one port at once — the FR-OPS-066 / OA-SYS-006
// conflict the backend must resolve before start (14 §2.1 notes the web backend
// and openpi both default to the same port).
export interface PortClash {
  port: number;
  components: string[];
}

export interface PortComparison {
  rows: PortComparisonRow[];
  clashes: PortClash[];
  hasMismatch: boolean;
}

function bindingFor(actual: ActualBinding[], component: string): ActualBinding | null {
  return actual.find((binding) => binding.component === component) ?? null;
}

function canonRow(entry: CanonPortEntry, actual: ActualBinding[]): PortComparisonRow {
  const binding = bindingFor(actual, entry.component);
  const actualPort = binding ? binding.port : null;
  let status: PortRowStatus;
  if (entry.port === null) {
    status = "no_port";
  } else if (binding === null) {
    status = "unbound";
  } else if (binding.port === entry.port) {
    status = "match";
  } else {
    status = "mismatch";
  }
  return {
    component: entry.component,
    protocol: entry.protocol,
    canonPort: entry.port,
    actualPort,
    status,
  };
}

function unexpectedRows(canon: CanonPortEntry[], actual: ActualBinding[]): PortComparisonRow[] {
  const known = new Set(canon.map((entry) => entry.component));
  return actual
    .filter((binding) => !known.has(binding.component))
    .map((binding) => ({
      component: binding.component,
      protocol: null,
      canonPort: null,
      actualPort: binding.port,
      status: "unexpected" as const,
    }));
}

// Clashes are computed over what is really LISTENING, not over the canon: the
// canon lists the same default port for two components on purpose (14 §2.1), and
// that is only a fault once both actually bind it at runtime.
function detectClashes(actual: ActualBinding[]): PortClash[] {
  const byPort = new Map<number, Set<string>>();
  for (const binding of actual) {
    if (!binding.listening) {
      continue;
    }
    const owners = byPort.get(binding.port) ?? new Set<string>();
    owners.add(binding.component);
    byPort.set(binding.port, owners);
  }
  const clashes: PortClash[] = [];
  for (const [port, owners] of byPort) {
    if (owners.size > 1) {
      clashes.push({ port, components: [...owners].sort() });
    }
  }
  return clashes.sort((left, right) => left.port - right.port);
}

// Diff the backend-served canon against the backend-served bindings. A mismatch,
// an unexpected binding, or a runtime clash all count as a surfaced discrepancy.
export function comparePorts(canon: CanonPortEntry[], actual: ActualBinding[]): PortComparison {
  const rows = [...canon.map((entry) => canonRow(entry, actual)), ...unexpectedRows(canon, actual)];
  const clashes = detectClashes(actual);
  const hasMismatch =
    rows.some((row) => row.status === "mismatch" || row.status === "unexpected") ||
    clashes.length > 0;
  return { rows, clashes, hasMismatch };
}

// The row statuses a reader must be able to see as a problem (drives styling and
// the summary count). Kept as data so the view never re-decides which are faults.
export const DISCREPANT_STATUSES: readonly PortRowStatus[] = ["mismatch", "unbound", "unexpected"];

export function isDiscrepant(status: PortRowStatus): boolean {
  return DISCREPANT_STATUSES.includes(status);
}
