"""The RT-promotion switch — `chrt -f` + `mlockall`, and the honesty around it.

`15` §2.10 condition 6 asks whether promoting the control thread to a real-time
scheduler helps, and `NFR-PRF-040` predicts it will NOT, because in Python
PREEMPT_RT cannot fix GIL contention — a load thread that holds the GIL is not
preempted by raising the victim's scheduler priority. Acceptance ⑤ therefore treats
"no gain" as a fully valid published result and forbids hiding a negative.

Two failure modes must never be conflated, and both are recorded verbatim:

  * RT was applied and produced no gain — the informative result `NFR-PRF-040`
    predicts.
  * RT could not be applied at all (no `CAP_SYS_NICE`, no locked-memory limit — the
    normal case in unprivileged CI) — a null result, not a no-gain result.

This module never pretends the scheduler changed when it did not: `applied` reflects
the real `os.sched_getscheduler` readback, and `mlockall` reports the real libc
return and errno. `THE ONE RULE` forbids faking an acceptance; claiming RT was in
force when it was refused would be exactly that.
"""

from __future__ import annotations

import contextlib
import ctypes
import ctypes.util
import os
from dataclasses import dataclass
from typing import Any

# Linux `mlockall` flags (bits/mman.h): lock currently-mapped and future pages.
_MCL_CURRENT = 1
_MCL_FUTURE = 2

# A low SCHED_FIFO priority: enough to sit above normal tasks for the experiment,
# far below anything that could wedge the box even if a restore were missed.
_FIFO_PRIORITY = 1

_SCHED_POLICY_NAMES: dict[int, str] = {}
for _name in ("SCHED_OTHER", "SCHED_FIFO", "SCHED_RR", "SCHED_BATCH", "SCHED_IDLE"):
    _value = getattr(os, _name, None)
    if _value is not None:
        _SCHED_POLICY_NAMES[int(_value)] = _name


def _policy_name(policy: int) -> str:
    """Name a scheduler policy number for the artifact.

    Args:
        policy: A scheduler policy integer from `os.sched_getscheduler`.

    Returns:
        (str) The policy's symbolic name, or its number when unknown.
    """
    return _SCHED_POLICY_NAMES.get(policy, f"policy_{policy}")


@dataclass(frozen=True)
class RtPromotionResult:
    """What actually happened when RT promotion was attempted.

    Attributes:
        supported: Whether this platform exposes SCHED_FIFO at all.
        policy_before: Scheduler policy name before the attempt.
        policy_after: Scheduler policy name after the attempt (the real readback).
        requested_policy: The policy name promotion asked for.
        priority: The SCHED_FIFO priority requested.
        sched_applied: Whether the scheduler policy actually changed to the request.
        sched_errno: errno if the scheduler change was refused, else 0.
        mlockall_return: Raw libc `mlockall` return (0 on success).
        mlockall_errno: errno if `mlockall` failed, else 0.
        mlockall_applied: Whether memory was actually locked.
        applied: True only when BOTH the scheduler change and `mlockall` succeeded.
        reason: Human-readable account of the outcome.
    """

    supported: bool
    policy_before: str
    policy_after: str
    requested_policy: str
    priority: int
    sched_applied: bool
    sched_errno: int
    mlockall_return: int
    mlockall_errno: int
    mlockall_applied: bool
    applied: bool
    reason: str

    def as_record(self) -> dict[str, Any]:
        """Serialize the promotion outcome for the artifact.

        Returns:
            (dict[str, Any]) Every field, so a reader can tell "applied, no gain" from
            "could not apply" without ambiguity (acceptance ⑤).
        """
        return {
            "supported": self.supported,
            "policy_before": self.policy_before,
            "policy_after": self.policy_after,
            "requested_policy": self.requested_policy,
            "priority": self.priority,
            "sched_applied": self.sched_applied,
            "sched_errno": self.sched_errno,
            "mlockall_return": self.mlockall_return,
            "mlockall_errno": self.mlockall_errno,
            "mlockall_applied": self.mlockall_applied,
            "applied": self.applied,
            "reason": self.reason,
        }


def _libc() -> ctypes.CDLL:
    """Load libc with errno tracking enabled.

    Returns:
        (ctypes.CDLL) The C library handle for `mlockall`/`munlockall`.
    """
    name = ctypes.util.find_library("c") or "libc.so.6"
    return ctypes.CDLL(name, use_errno=True)


def _try_mlockall() -> tuple[int, int]:
    """Attempt to lock all current and future pages into RAM.

    Returns:
        (tuple[int, int]) The libc return code and the errno (0 when it succeeded).
    """
    libc = _libc()
    ctypes.set_errno(0)
    result = libc.mlockall(_MCL_CURRENT | _MCL_FUTURE)
    errno = ctypes.get_errno()
    return int(result), (0 if result == 0 else errno)


def promote_realtime(priority: int = _FIFO_PRIORITY) -> RtPromotionResult:
    """Attempt to promote the calling thread to SCHED_FIFO and lock memory.

    Intended to run inside an isolated child process (see `conditions`), so a
    successful promotion cannot alter the parent harness or the test runner.

    Args:
        priority: The SCHED_FIFO priority to request.

    Returns:
        (RtPromotionResult) The real outcome, with `applied` reflecting the
        `os.sched_getscheduler` readback and the libc return — never an assumption.
    """
    if not hasattr(os, "sched_setscheduler") or not hasattr(os, "SCHED_FIFO"):
        return RtPromotionResult(
            supported=False,
            policy_before="unknown",
            policy_after="unknown",
            requested_policy="SCHED_FIFO",
            priority=priority,
            sched_applied=False,
            sched_errno=0,
            mlockall_return=-1,
            mlockall_errno=0,
            mlockall_applied=False,
            applied=False,
            reason="platform does not expose SCHED_FIFO; RT promotion not attempted",
        )

    policy_before = os.sched_getscheduler(0)
    sched_errno = 0
    try:
        os.sched_setscheduler(0, os.SCHED_FIFO, os.sched_param(priority))
    except (PermissionError, OSError) as error:
        sched_errno = error.errno or 0
    policy_after = os.sched_getscheduler(0)
    sched_applied = policy_after == os.SCHED_FIFO

    mlockall_return, mlockall_errno = _try_mlockall()
    mlockall_applied = mlockall_return == 0
    applied = sched_applied and mlockall_applied

    if applied:
        reason = "RT promotion applied: SCHED_FIFO in force and memory locked"
    elif not sched_applied and not mlockall_applied:
        reason = (
            f"RT promotion refused (no privilege): sched errno={sched_errno}, "
            f"mlockall errno={mlockall_errno} — null result, not a no-gain result"
        )
    else:
        reason = (
            f"RT promotion partial: sched_applied={sched_applied}, "
            f"mlockall_applied={mlockall_applied}"
        )

    return RtPromotionResult(
        supported=True,
        policy_before=_policy_name(policy_before),
        policy_after=_policy_name(policy_after),
        requested_policy="SCHED_FIFO",
        priority=priority,
        sched_applied=sched_applied,
        sched_errno=sched_errno,
        mlockall_return=mlockall_return,
        mlockall_errno=mlockall_errno,
        mlockall_applied=mlockall_applied,
        applied=applied,
        reason=reason,
    )


def restore_normal() -> None:
    """Best-effort return to SCHED_OTHER and unlock memory.

    Called on the child before it exits; a missed restore cannot escape the child,
    but leaving the child in SCHED_FIFO for its brief remaining life is still avoided.
    """
    if hasattr(os, "sched_setscheduler") and hasattr(os, "SCHED_OTHER"):
        with contextlib.suppress(OSError):
            os.sched_setscheduler(0, os.SCHED_OTHER, os.sched_param(0))
    with contextlib.suppress(OSError):
        _libc().munlockall()
