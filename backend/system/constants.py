"""Named parameters of the system report (`14` FR-OPS-023, `13` S-13).

Every path this report reads and every literal it compares against is named here, so the one
place a host fact is located is the one place it is read.
"""

from __future__ import annotations

from pathlib import Path

# The REST path S-13 fetches. Owned here rather than restated at the route, and mirrored by
# `frontend/src/screens/S-13/dataSource.ts`'s `SYSTEM_REPORT_ENDPOINT`.
SYSTEM_REPORT_ROUTE = "/api/system/report"

# Where the kernel says whether it is a realtime build. `/sys/kernel/realtime` exists only on
# PREEMPT_RT kernels and reads `1`; on every other kernel the file is simply absent, which is
# the answer rather than an error.
REALTIME_MARKER_PATH = Path("/sys/kernel/realtime")
REALTIME_MARKER_VALUE = "1"

# `/proc/<pid>/status`'s locked-memory line. `14` FR-OPS-023 names this as the evidence that
# mlockall took effect — the syscall's own return value is not evidence, because it succeeds
# under a limit that locked nothing.
PROC_STATUS_VMLCK_PREFIX = "VmLck:"
PROC_ROOT = Path("/proc")

# The listening-socket tables. Both are read: a server bound to `::` appears only in the v6
# table, and reporting it missing is how a compare view invents a port conflict.
PROC_NET_TCP_PATHS = (PROC_ROOT / "net" / "tcp", PROC_ROOT / "net" / "tcp6")
# `/proc/net/tcp`'s state column for a listening socket, hex, as the kernel writes it.
TCP_STATE_LISTEN = "0A"

# The scheduling policies, named as `chrt` prints them. A process on SCHED_OTHER has no
# realtime priority at all, which is what `OA-SYS-003` is about.
SCHED_POLICY_NAMES = {
    0: "SCHED_OTHER",
    1: "SCHED_FIFO",
    2: "SCHED_RR",
    3: "SCHED_BATCH",
    5: "SCHED_IDLE",
    6: "SCHED_DEADLINE",
}
REALTIME_POLICIES = frozenset({"SCHED_FIFO", "SCHED_RR", "SCHED_DEADLINE"})

# The code the report attaches when nothing in this process holds a realtime policy.
NO_RT_PRIVILEGE_CODE = "OA-SYS-003"

__all__ = [
    "NO_RT_PRIVILEGE_CODE",
    "PROC_NET_TCP_PATHS",
    "PROC_ROOT",
    "PROC_STATUS_VMLCK_PREFIX",
    "REALTIME_MARKER_PATH",
    "REALTIME_MARKER_VALUE",
    "REALTIME_POLICIES",
    "SCHED_POLICY_NAMES",
    "SYSTEM_REPORT_ROUTE",
    "TCP_STATE_LISTEN",
]
