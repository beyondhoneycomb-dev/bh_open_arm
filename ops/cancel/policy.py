"""Execution classes and the cancel policy each one forces.

`cancel_policy` is not a free field. `00` §3.2a says the execution class determines it, and `05`
§5.2.1 gives the table below with its safety argument: a class that can have the rig energised
must latch before anything else, because the arm has no holding brake and "let the current step
finish" means the arm keeps moving on an invalidated basis.

The derivation is checked in BOTH directions. A rig stage declaring `finish-step` is the safety
defect the plan is written to prevent; an offline stage declaring `latch-to-hold` is
over-application, which `02a` §-2.3 WP-BOOT-04 acceptance ④ also classes as a defect.
"""

from __future__ import annotations

from enum import StrEnum


class ExecClass(StrEnum):
    """Execution class of a work package stage (`00` §4)."""

    AI_OFFLINE = "AI-offline"
    AI_ON_HW = "AI-on-HW"
    HUMAN_ASSISTED_HW = "Human-assisted-HW"
    HUMAN_JUDGMENT = "Human-judgment"


class CancelPolicy(StrEnum):
    """What cancellation does to a stage that is currently running."""

    FINISH_STEP = "finish-step"
    LATCH_TO_HOLD = "latch-to-hold"


# Canonical table lives in the cancellation-discipline section of `05` cited above.
# Human-judgment is labelling and adjudication with no physical actuation, so it cancels like an
# offline stage; the two HW classes latch because a person or a torque-on arm is in the loop.
POLICY_BY_EXEC_CLASS: dict[ExecClass, CancelPolicy] = {
    ExecClass.AI_OFFLINE: CancelPolicy.FINISH_STEP,
    ExecClass.AI_ON_HW: CancelPolicy.LATCH_TO_HOLD,
    ExecClass.HUMAN_ASSISTED_HW: CancelPolicy.LATCH_TO_HOLD,
    ExecClass.HUMAN_JUDGMENT: CancelPolicy.FINISH_STEP,
}


class PolicyMismatchError(Exception):
    """Raised when a declared cancel policy contradicts the one its execution class forces."""

    def __init__(self, exec_class: ExecClass, declared: CancelPolicy) -> None:
        required = POLICY_BY_EXEC_CLASS[exec_class]
        super().__init__(
            f"{exec_class.value} forces cancel_policy={required.value}, "
            f"manifest declares {declared.value}"
        )
        self.exec_class = exec_class
        self.declared = declared
        self.required = required


def derive_cancel_policy(exec_class: ExecClass) -> CancelPolicy:
    """Return the cancel policy an execution class forces.

    Args:
        exec_class: Execution class of the stage.

    Returns:
        (CancelPolicy): The forced policy.
    """
    return POLICY_BY_EXEC_CLASS[exec_class]


def verify_declared_policy(exec_class: ExecClass, declared: CancelPolicy) -> None:
    """Check a manifest's declared cancel policy against its execution class.

    Args:
        exec_class: Execution class of the stage.
        declared: Policy the manifest declares for that stage.

    Raises:
        PolicyMismatchError: The declaration disagrees with the derivation, in either direction.
    """
    if derive_cancel_policy(exec_class) is not declared:
        raise PolicyMismatchError(exec_class, declared)
