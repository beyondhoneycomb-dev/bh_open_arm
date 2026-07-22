"""The torque-ON authorization gate: raise on any blocked precondition, never warn.

This is where WP-2A-09's contract — preflight is *the precondition of torque-ON*, and a
failed precondition *blocks* — becomes enforceable. A torque-ON caller must route
through `authorize_torque_on` before it emits any MIT torque frame; the function returns
only when every precondition passed and raises `TorqueOnBlockedError` otherwise. Because it
raises, a blocked preflight cannot be "logged and stepped over": there is no return path
that both reports a failure and permits the send.

The gate itself sends nothing and holds no CAN handle. It authorizes-or-raises; the
actual MIT frame lives behind it in the actuation path, and never runs when this raises.
"""

from __future__ import annotations

from backend.preflight.preflight import PreflightReport


class TorqueOnBlockedError(RuntimeError):
    """Torque-ON was refused because at least one preflight precondition failed.

    Carries the report so the caller (and the operator) can see every blocking
    precondition and its evidence, not merely that torque was refused.

    Attributes:
        report: The preflight report whose failures caused the refusal.
    """

    def __init__(self, report: PreflightReport) -> None:
        """Build the refusal from the blocking report.

        Args:
            report: The report whose `may_enable_torque` was false.
        """
        super().__init__(report.blocking_summary())
        self.report = report


def authorize_torque_on(report: PreflightReport) -> None:
    """Permit torque-ON only when every precondition passed, else raise.

    Args:
        report: The jog-session preflight report.

    Raises:
        TorqueOnBlockedError: When any precondition failed. The MIT torque frame the caller
            guards with this call is never reached on a raise.
    """
    if not report.may_enable_torque:
        raise TorqueOnBlockedError(report)
