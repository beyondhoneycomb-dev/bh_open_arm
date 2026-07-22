"""The startup loop-period vs RID9 check (`FR-TEL-080`, `PG-RID-001`).

The Damiao driver drops the motor enable — and the arm falls, there is no brake — if
it receives no CAN command within its RID9 comm-loss `TIMEOUT`. So the teleop loop
period (`1/fps`) must be strictly shorter than that timeout, and this is verified at
startup: a loop that cannot beat the timeout must not start torque (`FR-TEL-080`).

RID9 = 0 is not a period. It is the Damiao "HW comm-loss fallback disabled" flag
(`PG-RID-001` negative branch): with no motor-side timeout the period cannot under-run
it, so the check reports the disabled fallback rather than a timing verdict. Any
non-zero timeout that is not strictly greater than the loop period blocks torque-on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from backend.teleop.safety_gate.constants import RID9_HW_FALLBACK_DISABLED_SENTINEL


class Rid9Verdict(Enum):
    """The outcome of the startup loop-period vs RID9 check.

    Attributes:
        OK: The loop period is strictly shorter than the RID9 timeout; torque-on is
            permitted.
        HW_FALLBACK_DISABLED: RID9 is zero — the motor-side comm-loss fallback is off,
            so there is no timeout to under-run.
        TORQUE_ON_BLOCKED: The loop period is not shorter than the RID9 timeout; every
            frame would risk an enable drop, so torque-on is blocked.
    """

    OK = "ok"
    HW_FALLBACK_DISABLED = "hw_fallback_disabled"
    TORQUE_ON_BLOCKED = "torque_on_blocked"

    @property
    def permits_torque_on(self) -> bool:
        """Whether this verdict allows starting torque."""
        return self is not Rid9Verdict.TORQUE_ON_BLOCKED


class LoopPeriodError(RuntimeError):
    """Raised when the teleop loop period is not shorter than the RID9 timeout.

    `FR-TEL-080`: a loop that cannot beat the motor comm-loss timeout must not start
    teleop, because every frame would risk the enable dropping and the arm falling.
    """


@dataclass(frozen=True)
class Rid9CheckResult:
    """The verdict of the startup check with the values it was judged on.

    Attributes:
        verdict: The startup verdict.
        loop_period_sec: The teleop loop period checked, seconds.
        rid9_timeout_sec: The Damiao RID9 comm-loss timeout checked, seconds.
    """

    verdict: Rid9Verdict
    loop_period_sec: float
    rid9_timeout_sec: float

    @property
    def permits_torque_on(self) -> bool:
        """Whether the result permits starting torque."""
        return self.verdict.permits_torque_on


def evaluate_loop_period(loop_period_sec: float, rid9_timeout_sec: float) -> Rid9CheckResult:
    """Judge a loop period against the RID9 timeout without raising.

    Args:
        loop_period_sec: The teleop loop period (`1/fps`), seconds; must be positive.
        rid9_timeout_sec: The Damiao RID9 comm-loss timeout, seconds. Zero is the
            disabled-fallback sentinel, not a duration.

    Returns:
        (Rid9CheckResult) The verdict and the values judged.

    Raises:
        ValueError: If `loop_period_sec` is not positive or `rid9_timeout_sec` is
            negative.
    """
    if loop_period_sec <= 0.0:
        raise ValueError(f"loop period must be positive, got {loop_period_sec}")
    if rid9_timeout_sec < 0.0:
        raise ValueError(f"RID9 timeout cannot be negative, got {rid9_timeout_sec}")

    if rid9_timeout_sec == RID9_HW_FALLBACK_DISABLED_SENTINEL:
        verdict = Rid9Verdict.HW_FALLBACK_DISABLED
    elif rid9_timeout_sec > loop_period_sec:
        verdict = Rid9Verdict.OK
    else:
        verdict = Rid9Verdict.TORQUE_ON_BLOCKED
    return Rid9CheckResult(
        verdict=verdict, loop_period_sec=loop_period_sec, rid9_timeout_sec=rid9_timeout_sec
    )


def verify_loop_period_under_rid9_timeout(
    loop_period_sec: float, rid9_timeout_sec: float
) -> Rid9CheckResult:
    """Verify the loop period beats the RID9 timeout, blocking torque-on otherwise.

    The gating form of `evaluate_loop_period`, called at teleop startup: it raises
    when the timing verdict blocks torque, so a caller cannot begin a session whose
    loop cannot keep the motor enabled.

    Args:
        loop_period_sec: The teleop loop period (`1/fps`), seconds.
        rid9_timeout_sec: The Damiao RID9 comm-loss timeout, seconds.

    Returns:
        (Rid9CheckResult) The result, when torque-on is permitted (OK or the
        disabled-fallback flag).

    Raises:
        LoopPeriodError: When the loop period is not strictly shorter than a non-zero
            RID9 timeout (`FR-TEL-080`).
    """
    result = evaluate_loop_period(loop_period_sec, rid9_timeout_sec)
    if not result.permits_torque_on:
        raise LoopPeriodError(
            f"teleop loop period {loop_period_sec} s is not shorter than the Damiao RID9 "
            f"comm-loss timeout {rid9_timeout_sec} s; torque-on is blocked (FR-TEL-080). "
            "Raise the send rate or block torque-on (PG-RID-001)."
        )
    return result
