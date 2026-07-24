"""The load-preflight verdict and its refusal reasons (FR-INF-070/037/035).

`02c` §2.3 fixes the shape of this gate's output: `LoadPreflight(checkpoint,
robot_config) -> Verdict`. A refusal is only trustworthy when it names the
requirement it enforces and the values it saw, so `Refusal` carries the rule id,
the observed value, and what was expected. These are pure carriers with no checking
logic; the orchestrator (`preflight`) fills them and the block error is minted only
from a refused verdict, so a caller cannot fabricate a block that skipped the check.

The refusal is a hard stop, never advice: FR-INF-035 makes this gate the FIRST line
of defense (LeRobot's `send_action` clip is the last), and the mirror case is the
sharpest reason why — a left gripper that silently clips is a WRONG SUCCESS, not an
error, and a permissive verdict would let 4C misclassify it as a grasp failure.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class RefusalCode(StrEnum):
    """The kind of load-preflight refusal a reason records.

    `DIMENSION_MISMATCH` and `POLICY_DIM_UNREACHABLE` are the two halves of
    FR-INF-070's dimension check: the first is the checkpoint's input/output width
    disagreeing with the robot's observation/action width, the second is a policy
    family whose ceiling the robot's width can never reach (bimanual 48 against the
    32-capped SmolVLA is structurally impossible). `GRIPPER_MIRROR` is the FR-INF-070
    left-gripper sign-mirror block. `SIDE_UNSPECIFIED` is FR-INF-037 (an unset side
    locks the arm to +/-5 degrees). `COMMAND_EXCEEDS_PMAX` is the FR-INF-038 wrap
    guard (a commanded position beyond +/-PMAX).
    """

    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    POLICY_DIM_UNREACHABLE = "POLICY_DIM_UNREACHABLE"
    GRIPPER_MIRROR = "GRIPPER_MIRROR"
    SIDE_UNSPECIFIED = "SIDE_UNSPECIFIED"
    COMMAND_EXCEEDS_PMAX = "COMMAND_EXCEEDS_PMAX"


@dataclass(frozen=True)
class Refusal:
    """One reason a policy load is refused, with the requirement it enforces.

    Attributes:
        code: The kind of refusal.
        rule_id: The requirement the refusal enforces — `FR-INF-070`, `FR-INF-037`,
            `FR-INF-038`, or a folded WP-4B-01 rule id for a policy-ceiling block.
        detail: The operator-facing sentence explaining the refusal.
        observed: The value the checkpoint or robot presented, rendered for display.
        expected: What a loadable pairing would have presented, rendered for display.
    """

    code: RefusalCode
    rule_id: str
    detail: str
    observed: str
    expected: str


@dataclass(frozen=True)
class LoadVerdict:
    """The verdict of one `LoadPreflight(checkpoint, robot_config)` (the `Verdict`).

    `allowed` is true only when no refusal applies. The gate's job is to REFUSE: a
    permissive verdict on a dimension or mirror mismatch lets a policy load and then
    fail in a way that reads as anything but a limit error, so a refused verdict is a
    hard stop.

    Attributes:
        allowed: True only when `refusals` is empty.
        refusals: Every applicable refusal, one per violated rule; empty when loadable.
    """

    allowed: bool
    refusals: tuple[Refusal, ...]

    def raise_if_refused(self) -> None:
        """Raise `LoadRefusedError` when the verdict is not allowed; return otherwise.

        Raises:
            LoadRefusedError: When `allowed` is false.
        """
        if self.allowed:
            return
        raise LoadRefusedError(self)


class LoadRefusedError(RuntimeError):
    """A policy load was refused by the preflight; inference must not start.

    Carries the refused verdict so an operator sees every reason. This is a plain
    domain error rather than an `OaError` code because FR-INF-070's refusal is a
    load-time gate decision, not one of the frozen CTR-ERR runtime error codes.
    """

    def __init__(self, verdict: LoadVerdict) -> None:
        """Build the error from the verdict that refused the load.

        Args:
            verdict: The refused verdict; its reasons are attached for an operator.
        """
        reasons = "; ".join(
            f"{reason.code} ({reason.rule_id}): {reason.detail}" for reason in verdict.refusals
        )
        super().__init__(f"policy load refused: {reasons}")
        self.verdict = verdict
