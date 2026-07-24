"""The remote-gRPC adapter: validated params, the direct-`send_action` dummy path, deferred e2e.

`NFR-INF-008` fixes the remote path's shape: the `robot_client` calls
`robot.send_action()` **directly** (`robot_client.py:381-383`), not the
`robot_action_processor` pipeline, which is exactly why the safety gateway is a
`send_action` override rather than a pipeline step. This adapter follows that shape —
its offline dummy path hands each decoded action straight to `robot.send_action()`,
never to the mailbox, and never to a CAN handle.

The end-to-end remote rollout (`policy_server` + `robot_client` against a real
OpenArm) is `11` §5-Q8 **[미확인]** and cannot be verified here: there is no real
robot, and `SUPPORTED_ROBOTS` is commented out (`robot_client.py:489-490`) so there
is no hard block to lean on either. Per `02c` §1.7 that e2e is **deferred with a
re-verification hook**, carried as data on this adapter — never faked green. What
runs here is the param validation, the round-trip advisory, and the dummy
`send_action` path; what is deferred is the real gRPC session.
"""

from __future__ import annotations

from dataclasses import dataclass

from lerobot.robots.robot import RobotAction

from backend.inference.adapter.params import RemoteParams, advisory_max_roundtrip_sec
from contracts.action import BIMANUAL_ACTION_DIM
from contracts.plugin.robot_abc import OpenArmRobot

# The Q8 question this band cannot close, and the gate a real fixture must re-run to
# close it. Named as data so a caller can surface "deferred, here is why" instead of
# a silent gap.
Q8_QUESTION_ID = "11#5-Q8"
Q8_REVERIFY_GATE = "remote-gRPC OpenArm e2e rollout (policy_server + robot_client)"


@dataclass(frozen=True)
class ReVerificationHook:
    """A truthfully-recorded deferral: what is unverified, why, and how to close it.

    This is the honest alternative to a faked green. `verified` is False while the
    condition cannot be checked here; `blocked_reason` says what is missing, and
    `reverify_gate` names the gate a real fixture runs to flip it.

    Attributes:
        question_id: The open-question id (e.g. `11#5-Q8`).
        description: What is unverified.
        blocked_reason: Why it cannot be verified in this environment.
        reverify_gate: The gate/rollout that must succeed once, elsewhere, to close it.
        verified: Whether the condition has been verified (always False here).
    """

    question_id: str
    description: str
    blocked_reason: str
    reverify_gate: str
    verified: bool = False


def _q8_hook() -> ReVerificationHook:
    """Build the Q8 remote-e2e deferral hook."""
    return ReVerificationHook(
        question_id=Q8_QUESTION_ID,
        description=(
            "Whether OpenArm actually works end-to-end over remote gRPC "
            "(policy_server + robot_client) is unverified."
        ),
        blocked_reason=(
            "No real robot in this environment, and SUPPORTED_ROBOTS is commented out "
            "(robot_client.py:489-490), so neither an e2e run nor a hard block exists here."
        ),
        reverify_gate=Q8_REVERIFY_GATE,
    )


class RemoteInferenceAdapter:
    """The remote-gRPC backend: params validated, actions routed through `send_action`.

    Ownership: holds validated `RemoteParams`, the robot whose `send_action` override
    is the single enforcement point, and the Q8 deferral hook. It builds no real gRPC
    session — `dummy_rollout_step` is the offline path that proves the direct-
    `send_action` contract; the real session is deferred (Q8).
    """

    def __init__(self, params: RemoteParams, robot: OpenArmRobot) -> None:
        """Bind validated remote params to the robot the client would drive.

        Args:
            params: Remote parameters that have already passed `validate_remote_params`.
                `actions_per_chunk` is therefore present and positive.
            robot: The follower whose `send_action` override enforces safety; the
                offline dummy echoes, a real follower runs the gateway filter.

        Raises:
            ValueError: If `params.actions_per_chunk` is None — the adapter must only
                be built from validated params (defence in depth against a caller that
                skipped `validate_remote_params`).
        """
        if params.actions_per_chunk is None:
            raise ValueError(
                "RemoteInferenceAdapter requires validated params; actions_per_chunk is None. "
                "Call validate_remote_params first (FR-INF-019)."
            )
        self._params = params
        self._robot = robot
        self._reverification = _q8_hook()
        self._ordered_action_keys = tuple(robot.action_features.keys())

    @property
    def params(self) -> RemoteParams:
        """The validated remote parameters."""
        return self._params

    @property
    def reverification_hook(self) -> ReVerificationHook:
        """The Q8 deferral — remote e2e is unverified here, with the gate to close it."""
        return self._reverification

    @property
    def roundtrip_bound_sec(self) -> float:
        """The `NFR-INF-001` async round-trip p99 bound the params imply, in seconds.

        Returns:
            (float) `(chunk_size_threshold * actions_per_chunk) / fps`.
        """
        return advisory_max_roundtrip_sec(
            self._params.chunk_size_threshold,
            # actions_per_chunk is validated non-None in __init__.
            int(self._params.actions_per_chunk),  # type: ignore[arg-type]
            self._params.fps,
        )

    def dummy_rollout_step(self, action_vector: list[float]) -> RobotAction:
        """Route one decoded action through `robot.send_action()` directly (offline path).

        This is the remote contract's shape on the dummy: the client calls
        `send_action` itself (`NFR-INF-008`), so the action does not pass through the
        mailbox. On the dummy it echoes; on a real follower the `send_action` override
        runs the safety filter. No CAN is written by this adapter.

        Args:
            action_vector: A `BIMANUAL_ACTION_DIM`-wide position vector (degrees) as
                the server would return.

        Returns:
            (RobotAction) The accepted action the follower reports.

        Raises:
            ValueError: If `action_vector` is not `BIMANUAL_ACTION_DIM` wide.
        """
        if len(action_vector) != BIMANUAL_ACTION_DIM:
            raise ValueError(
                f"remote action must be {BIMANUAL_ACTION_DIM}-wide; got {len(action_vector)}"
            )
        action: RobotAction = {
            key: float(value)
            for key, value in zip(self._ordered_action_keys, action_vector, strict=True)
        }
        return self._robot.send_action(action)
