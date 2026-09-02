"""The one system report S-13 renders (`13` S-13, `14` FR-OPS-023).

The screen is a facade: it holds none of the canon and re-sources nothing. So everything it
draws is assembled here — the declared port map, what is really bound, this process's realtime
posture, the diagnostic-bundle manifest, and the frozen error registry.

The wire names are camelCase because that is what the browser's `SystemData` declares, and they
are constants rather than literals at the call site so the mirror test can read them. There is
no second declaration of any of this: the ports come from `contracts.ports`, the codes from
`contracts.errors`, and the host facts from `/proc`.

Nothing here fails the request. A host read that does not answer contributes an absence — a
process reported without its locked-memory line, a binding whose owner could not be read — and
the report is still served, because a diagnostic that refuses to open on a broken machine is
useless exactly where it was needed.
"""

from __future__ import annotations

import os
from typing import Any

from backend.system.bindings import ActualBinding, read_bindings
from backend.system.bundle import bundle_manifest
from backend.system.rt import (
    ProcessRtStatus,
    RtEnvironment,
    RtFinding,
    findings_for,
    read_environment,
    read_process,
)
from contracts.errors import load_registry
from contracts.ports import CanonPort, load_port_canon, served_component

# Wire field names, mirroring `frontend/src/screens/S-13/types.ts`.
PORTS_FIELD = "ports"
PORTS_CANON_FIELD = "canon"
PORTS_ACTUAL_FIELD = "actual"
RT_FIELD = "rt"
BUNDLE_FIELD = "bundle"
ERROR_REGISTRY_FIELD = "errorRegistry"

CANON_COMPONENT = "component"
CANON_PROTOCOL = "protocol"
CANON_PORT = "port"

ACTUAL_COMPONENT = "component"
ACTUAL_PORT = "port"
ACTUAL_PID = "pid"
ACTUAL_LISTENING = "listening"

RT_ENV_FIELD = "env"
RT_PROCESSES_FIELD = "processes"
RT_FINDINGS_FIELD = "findings"
ENV_KERNEL_RELEASE = "kernelRelease"
ENV_PREEMPT_RT = "preemptRt"
ENV_PYTHON_VERSION = "pythonVersion"
PROCESS_PID = "pid"
PROCESS_NAME = "name"
PROCESS_SCHED_POLICY = "schedPolicy"
PROCESS_SCHED_PRIORITY = "schedPriority"
PROCESS_CPU_AFFINITY = "cpuAffinity"
PROCESS_VMLCK_KB = "vmlckKb"
PROCESS_MLOCKALL_OK = "mlockallReturnedOk"
FINDING_CODE = "code"
FINDING_NOTE = "note"

REGISTRY_CODE = "code"
REGISTRY_SEVERITY = "severity"
REGISTRY_MESSAGE_KO = "messageKo"
REGISTRY_MESSAGE_EN = "messageEn"
REGISTRY_RECOVERY_HINT = "recoveryHint"
REGISTRY_DOC_URL = "docUrl"
REGISTRY_SUBSYSTEM = "subsystem"


def _canon_row(row: CanonPort) -> dict[str, Any]:
    return {
        CANON_COMPONENT: row.component,
        CANON_PROTOCOL: row.protocol,
        CANON_PORT: row.port,
    }


def _binding_row(row: ActualBinding) -> dict[str, Any]:
    return {
        ACTUAL_COMPONENT: row.component,
        ACTUAL_PORT: row.port,
        ACTUAL_PID: row.pid,
        ACTUAL_LISTENING: row.listening,
    }


def _environment(env: RtEnvironment) -> dict[str, Any]:
    return {
        ENV_KERNEL_RELEASE: env.kernel_release,
        ENV_PREEMPT_RT: env.preempt_rt,
        ENV_PYTHON_VERSION: env.python_version,
    }


def _process_row(process: ProcessRtStatus) -> dict[str, Any]:
    return {
        PROCESS_PID: process.pid,
        PROCESS_NAME: process.name,
        PROCESS_SCHED_POLICY: process.sched_policy,
        PROCESS_SCHED_PRIORITY: process.sched_priority,
        PROCESS_CPU_AFFINITY: list(process.cpu_affinity),
        PROCESS_VMLCK_KB: process.vmlck_kb,
        PROCESS_MLOCKALL_OK: process.mlockall_returned_ok,
    }


def _finding_row(finding: RtFinding) -> dict[str, Any]:
    return {FINDING_CODE: finding.code, FINDING_NOTE: finding.note}


def error_registry_body() -> dict[str, dict[str, Any]]:
    """The frozen `OA-*` registry, keyed by code, in the browser's field names.

    Served rather than mirrored into the bundle: `14` §2.10 is the single source, and a copy in
    the browser would be a second table that drifts the first time a recovery hint is reworded.

    Returns:
        (dict) Every registered code.
    """
    registry = load_registry()
    return {
        code.code: {
            REGISTRY_CODE: code.code,
            REGISTRY_SEVERITY: code.severity,
            REGISTRY_MESSAGE_KO: code.message_ko,
            REGISTRY_MESSAGE_EN: code.message_en,
            REGISTRY_RECOVERY_HINT: code.recovery_hint,
            REGISTRY_DOC_URL: code.doc_url,
            REGISTRY_SUBSYSTEM: code.subsystem,
        }
        for code in registry.codes.values()
    }


def system_report() -> dict[str, Any]:
    """Assemble the whole S-13 payload from this host.

    Returns:
        (dict) The report, in the browser's `SystemData` shape.
    """
    canon = load_port_canon()
    declared_ports = frozenset(row.port for row in canon if row.port is not None)
    pid = os.getpid()
    process = read_process(pid)
    processes = () if process is None else (process,)
    return {
        PORTS_FIELD: {
            PORTS_CANON_FIELD: [_canon_row(row) for row in canon],
            PORTS_ACTUAL_FIELD: [
                _binding_row(row) for row in read_bindings(served_component(), pid, declared_ports)
            ],
        },
        RT_FIELD: {
            RT_ENV_FIELD: _environment(read_environment()),
            RT_PROCESSES_FIELD: [_process_row(row) for row in processes],
            RT_FINDINGS_FIELD: [_finding_row(row) for row in findings_for(processes)],
        },
        BUNDLE_FIELD: bundle_manifest(),
        ERROR_REGISTRY_FIELD: error_registry_body(),
    }


__all__ = [
    "ACTUAL_COMPONENT",
    "ACTUAL_LISTENING",
    "ACTUAL_PID",
    "ACTUAL_PORT",
    "BUNDLE_FIELD",
    "CANON_COMPONENT",
    "CANON_PORT",
    "CANON_PROTOCOL",
    "ENV_KERNEL_RELEASE",
    "ENV_PREEMPT_RT",
    "ENV_PYTHON_VERSION",
    "ERROR_REGISTRY_FIELD",
    "FINDING_CODE",
    "FINDING_NOTE",
    "PORTS_ACTUAL_FIELD",
    "PORTS_CANON_FIELD",
    "PORTS_FIELD",
    "PROCESS_CPU_AFFINITY",
    "PROCESS_MLOCKALL_OK",
    "PROCESS_NAME",
    "PROCESS_PID",
    "PROCESS_SCHED_POLICY",
    "PROCESS_SCHED_PRIORITY",
    "PROCESS_VMLCK_KB",
    "REGISTRY_CODE",
    "REGISTRY_DOC_URL",
    "REGISTRY_MESSAGE_EN",
    "REGISTRY_MESSAGE_KO",
    "REGISTRY_RECOVERY_HINT",
    "REGISTRY_SEVERITY",
    "REGISTRY_SUBSYSTEM",
    "RT_ENV_FIELD",
    "RT_FIELD",
    "RT_FINDINGS_FIELD",
    "RT_PROCESSES_FIELD",
    "error_registry_body",
    "system_report",
]
