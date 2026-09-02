"""What the host says about this process's realtime posture.

`14` FR-OPS-023 asks the diagnostic bundle for the kernel, whether it is a PREEMPT_RT build,
the scheduling class, the CPU affinity, `VmLck` and the Python version. S-13 renders the same
facts live, so both read them from here.

Everything is read, nothing is asserted. A kernel with no realtime marker reports `False`
rather than raising, an unreadable `VmLck` reports as unread rather than as zero, and a process
that vanished between the listing and the read is dropped. A diagnostic that refuses to answer
because one file was missing is a diagnostic nobody can use on the machine that needs it.

The one judgement here is `OA-SYS-003`: no process in this report holds a realtime policy. It
is attached to the report rather than raised, because a rig that has not been promoted yet is
a normal state — it is the operator's to fix, not this module's to refuse.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass

from backend.system.constants import (
    NO_RT_PRIVILEGE_CODE,
    PROC_ROOT,
    PROC_STATUS_VMLCK_PREFIX,
    REALTIME_MARKER_PATH,
    REALTIME_MARKER_VALUE,
    REALTIME_POLICIES,
    SCHED_POLICY_NAMES,
)

UNKNOWN_POLICY = "unknown"
NO_RT_PRIVILEGE_NOTE = (
    "no process in this report holds SCHED_FIFO, SCHED_RR or SCHED_DEADLINE; "
    "the control loop runs at the same priority as everything else on this host"
)


@dataclass(frozen=True)
class RtEnvironment:
    """The kernel and interpreter this process is running on.

    Attributes:
        kernel_release: `uname -r`.
        preempt_rt: Whether the kernel exposes the realtime marker. False on a stock kernel,
            which is a fact rather than a failure.
        python_version: The interpreter's version.
    """

    kernel_release: str
    preempt_rt: bool
    python_version: str


@dataclass(frozen=True)
class ProcessRtStatus:
    """One process's scheduling and locked-memory posture.

    Attributes:
        pid: The process id.
        name: What `/proc/<pid>/comm` calls it.
        sched_policy: The policy as `chrt` names it, or `unknown` when the kernel returned a
            value this build has no name for.
        sched_priority: The realtime priority; zero on a non-realtime policy.
        cpu_affinity: The CPUs it may run on, ascending.
        vmlck_kb: Locked memory in kilobytes, or None when `/proc/<pid>/status` could not be
            read. None rather than 0: zero is a real reading and means mlockall did nothing.
        mlockall_returned_ok: Whether the mlockall syscall reported success, or None when this
            process never called it. `14` FR-OPS-023 keeps this beside `VmLck` precisely so the
            two can be shown disagreeing; nothing in this repository calls mlockall today, so
            the honest value is that it was never attempted.
    """

    pid: int
    name: str
    sched_policy: str
    sched_priority: int
    cpu_affinity: tuple[int, ...]
    vmlck_kb: int | None
    mlockall_returned_ok: bool | None


@dataclass(frozen=True)
class RtFinding:
    """A deficiency the report names with its registry code.

    Attributes:
        code: The `OA-*` code. S-13 looks its remedy up in the frozen registry rather than
            carrying its own copy of the text.
        note: What was observed, or None when the code says everything.
    """

    code: str
    note: str | None


def read_environment() -> RtEnvironment:
    """Read the kernel and interpreter facts.

    Returns:
        (RtEnvironment) What this host is.
    """
    try:
        marker = REALTIME_MARKER_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        marker = ""
    return RtEnvironment(
        kernel_release=platform.release(),
        preempt_rt=marker == REALTIME_MARKER_VALUE,
        python_version=platform.python_version(),
    )


def _locked_memory_kb(pid: int) -> int | None:
    """Read `VmLck` for one process, or None when its status file cannot be read."""
    try:
        status = (PROC_ROOT / str(pid) / "status").read_text(encoding="utf-8")
    except OSError:
        return None
    for line in status.splitlines():
        if line.startswith(PROC_STATUS_VMLCK_PREFIX):
            fields = line.split()
            if len(fields) >= 2 and fields[1].isdigit():
                return int(fields[1])
    return None


def _process_name(pid: int) -> str:
    """Read `/proc/<pid>/comm`, or fall back to the pid when it cannot be read."""
    try:
        return (PROC_ROOT / str(pid) / "comm").read_text(encoding="utf-8").strip()
    except OSError:
        return f"pid {pid}"


def read_process(pid: int) -> ProcessRtStatus | None:
    """Read one process's realtime posture.

    Args:
        pid: The process to read.

    Returns:
        (ProcessRtStatus | None) Its posture, or None when the process is gone. A process that
        exited between being listed and being read is not an error to report — it is a process
        that is not there any more.
    """
    try:
        policy = os.sched_getscheduler(pid)
        priority = os.sched_getparam(pid).sched_priority
        affinity = sorted(os.sched_getaffinity(pid))
    except (OSError, PermissionError):
        return None
    return ProcessRtStatus(
        pid=pid,
        name=_process_name(pid),
        sched_policy=SCHED_POLICY_NAMES.get(policy, UNKNOWN_POLICY),
        sched_priority=priority,
        cpu_affinity=tuple(affinity),
        vmlck_kb=_locked_memory_kb(pid),
        # Never attempted: nothing in this repository calls mlockall. Reporting False would
        # say the syscall failed, which is a different thing from not having been made.
        mlockall_returned_ok=None,
    )


def findings_for(processes: tuple[ProcessRtStatus, ...]) -> tuple[RtFinding, ...]:
    """Name the realtime deficiencies these readings show.

    Args:
        processes: The postures read.

    Returns:
        (tuple[RtFinding, ...]) One finding per deficiency; empty when there is none.
    """
    if any(process.sched_policy in REALTIME_POLICIES for process in processes):
        return ()
    return (RtFinding(code=NO_RT_PRIVILEGE_CODE, note=NO_RT_PRIVILEGE_NOTE),)


__all__ = [
    "NO_RT_PRIVILEGE_NOTE",
    "UNKNOWN_POLICY",
    "ProcessRtStatus",
    "RtEnvironment",
    "RtFinding",
    "findings_for",
    "read_environment",
    "read_process",
]
