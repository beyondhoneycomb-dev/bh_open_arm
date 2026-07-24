"""The load preflight: the first-line gate run BEFORE a policy loads (FR-INF-070/037).

`LoadPreflight.check(checkpoint, robot_config) -> LoadVerdict` is the `02c` §2.3
interface. It refuses a load when any of three things is wrong:

- FR-INF-037: the single-arm side is unset — LeRobot would leave `joint_limits` at
  +/-5 degrees and the arm would not move, so the load must not start.
- FR-INF-070 dimension: the checkpoint's input/output width disagrees with the
  robot's observation/action width, OR the policy family's ceiling can never reach
  the robot's width (bimanual 48 against the 32-capped SmolVLA is structurally
  impossible — the ceiling is READ from the installed config via the committed
  WP-4B-01 capability, not hardcoded).
- FR-INF-070 mirror: the bimanual left gripper is not the sign-mirror of the right —
  the WRONG-SUCCESS case a permissive verdict would let 4C misread as a grasp failure.

The engine's job is to REFUSE; a missing refusal is the failure mode, not a missing
pass. The two-place limit consistency (the limit loader) and the command-wrap /
velocity guards live in their own modules — this gate composes the mirror validator
and reuses WP-4B-01's ceilings, restating neither.
"""

from __future__ import annotations

from backend.inference.load_preflight.mirror import check_gripper_mirror_from_limits
from backend.inference.load_preflight.profiles import CheckpointProfile, RobotProfile
from backend.inference.load_preflight.verdict import LoadVerdict, Refusal, RefusalCode

_RULE_DIMENSION = "FR-INF-070"
_RULE_SIDE = "FR-INF-037"


class LoadPreflight:
    """The load-time gate: dimension match, left-gripper mirror, and required side.

    Stateless; one instance serves any number of checks. It is the FIRST line of
    defense (FR-INF-035) — LeRobot's `send_action` clip is the last — so every
    refusal here is a hard stop that keeps the policy from loading at all.
    """

    def check(self, checkpoint: CheckpointProfile, robot_config: RobotProfile) -> LoadVerdict:
        """Run the load preflight and return its verdict.

        Args:
            checkpoint: The checkpoint's trained widths and policy family.
            robot_config: The robot's shape switches and per-arm limits.

        Returns:
            (LoadVerdict) Allowed only when no refusal applies.
        """
        refusals: list[Refusal] = []
        self._check_side(robot_config, refusals)
        self._check_dimensions(checkpoint, robot_config, refusals)
        self._check_gripper_mirror(robot_config, refusals)
        return LoadVerdict(allowed=not refusals, refusals=tuple(refusals))

    def _check_side(self, robot_config: RobotProfile, refusals: list[Refusal]) -> None:
        """Refuse a single-arm load whose side is unset (FR-INF-037; +/-5 degree lock)."""
        if robot_config.bimanual or robot_config.side is not None:
            return
        refusals.append(
            Refusal(
                code=RefusalCode.SIDE_UNSPECIFIED,
                rule_id=_RULE_SIDE,
                detail=(
                    "robot side is unset; LeRobot would lock joint_limits to +/-5 degrees "
                    "and the arm would not move — inference must not start (FR-INF-037)"
                ),
                observed="side=None",
                expected="side=left or side=right",
            )
        )

    def _check_dimensions(
        self,
        checkpoint: CheckpointProfile,
        robot_config: RobotProfile,
        refusals: list[Refusal],
    ) -> None:
        """Refuse a checkpoint whose widths do not match the robot's (FR-INF-070)."""
        observation_dim = robot_config.observation_dim()
        action_dim = robot_config.action_dim()

        if checkpoint.input_dim != observation_dim:
            refusals.append(
                Refusal(
                    code=RefusalCode.DIMENSION_MISMATCH,
                    rule_id=_RULE_DIMENSION,
                    detail=(
                        "checkpoint input width does not match the robot observation width "
                        "(FR-INF-070)"
                    ),
                    observed=f"input_features={checkpoint.input_dim}",
                    expected=f"observation_features={observation_dim}",
                )
            )
        if checkpoint.output_dim != action_dim:
            refusals.append(
                Refusal(
                    code=RefusalCode.DIMENSION_MISMATCH,
                    rule_id=_RULE_DIMENSION,
                    detail=(
                        "checkpoint output width does not match the robot action width (FR-INF-070)"
                    ),
                    observed=f"output_features={checkpoint.output_dim}",
                    expected=f"action_features={action_dim}",
                )
            )
        self._check_policy_ceiling(checkpoint, observation_dim, refusals)

    def _check_policy_ceiling(
        self,
        checkpoint: CheckpointProfile,
        observation_dim: int,
        refusals: list[Refusal],
    ) -> None:
        """Refuse when the policy family's state ceiling can never reach the robot width.

        The ceiling is READ from the installed LeRobot config through the committed
        WP-4B-01 capability (never hardcoded), so a pin that moves a ceiling moves this
        check with it. Bimanual 48 against SmolVLA's max_state_dim=32 is the canonical
        structurally-impossible pairing.
        """
        if checkpoint.policy_id is None:
            return
        cap = _policy_state_ceiling(checkpoint.policy_id)
        if cap is None or observation_dim <= cap:
            return
        refusals.append(
            Refusal(
                code=RefusalCode.POLICY_DIM_UNREACHABLE,
                rule_id=_RULE_DIMENSION,
                detail=(
                    f"policy {checkpoint.policy_id} caps observation.state at {cap}; the robot "
                    f"presents {observation_dim} — structurally impossible (FR-INF-070)"
                ),
                observed=f"observation_features={observation_dim}",
                expected=f"max_state_dim={cap}",
            )
        )

    def _check_gripper_mirror(self, robot_config: RobotProfile, refusals: list[Refusal]) -> None:
        """Refuse a bimanual load whose left gripper is not the mirror of the right."""
        if not robot_config.bimanual:
            return
        left = robot_config.left_joint_limits
        right = robot_config.right_joint_limits
        if left is None or right is None:
            return
        verdict = check_gripper_mirror_from_limits(left, right)
        if verdict.ok:
            return
        refusals.append(
            Refusal(
                code=RefusalCode.GRIPPER_MIRROR,
                rule_id=_RULE_DIMENSION,
                detail=verdict.detail(),
                observed=f"left_gripper={verdict.left}",
                expected=f"left_gripper={verdict.expected_left}",
            )
        )


def _policy_state_ceiling(policy_id: str) -> int | None:
    """Read a policy family's `max_state_dim` via the committed WP-4B-01 capability.

    Lazy so the pure checks (dimension equality, side, mirror) do not pull the LeRobot
    policy stack in. An unknown family is treated as no ceiling — the dimension
    equality check already refuses a mismatched checkpoint, so a mistyped family never
    passes silently.

    Args:
        policy_id: The policy family id.

    Returns:
        (int | None) The introspected `max_state_dim`, or None when uncapped/unknown.
    """
    from backend.compat.policy_matrix.capability import introspect_capability

    try:
        return introspect_capability(policy_id).max_state_dim
    except KeyError:
        return None
