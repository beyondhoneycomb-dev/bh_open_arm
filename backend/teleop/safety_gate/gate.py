"""The teleop safety gate: heartbeat, workspace, velocity and the no-auto-resume latch.

This is the one object that composes the WP-3B-10 pieces onto the state machine slice
this package owns (FOLLOWING / LINK_LOST / IK_FAULT / ALIGNING). Every tick it emits a
command — never a no-command tick (`FR-TEL-079`; a break in the CAN stream drops the
motor enable and the arm falls) — and it enforces the safety-critical invariants:

- a lost heartbeat (STALE = lost) moves FOLLOWING to LINK_LOST and decelerates the EE
  to a hold; the command stream continues throughout (`FR-TEL-081`, S5);
- a hold never resumes following on its own. The only exit is an explicit operator
  re-engage into ALIGNING, forbidden while the VR link is still lost and — the
  superior gate — forbidden while the deadman lease latch is held. Link recovery is
  not re-arming; the `WP-2A-02` re-arm handshake must clear the lease latch first
  (`FR-TEL-082`, `05` §4.2 #1/#3);
- the received pose is sanity-checked (degenerate/non-finite discarded, `FR-TEL-038`),
  projected into the workspace box (`FR-TEL-036`) and velocity-limited (`FR-TEL-037`)
  before it becomes a command.

Ownership of the lease is not taken here: the gate reads a `LeaseLatchView` — the
deadman controller satisfies it structurally — and never renews, latches or clears
the lease. That stays the deadman's single definition (`WP-2A-02`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from backend.deadman import DeadmanController
from backend.teleop.safety_gate.constants import (
    DEFAULT_LINK_LOST_DECEL_M_S2,
    DEFAULT_PERSISTENT_WALL_VIOLATION_TICKS,
)
from backend.teleop.safety_gate.heartbeat import LinkHealth, LinkHeartbeat
from backend.teleop.safety_gate.pose import (
    EEPose,
    Vector3,
    vector_add,
    vector_magnitude,
    vector_scale,
    vector_sub,
)
from backend.teleop.safety_gate.sanity import PoseSanityFilter
from backend.teleop.safety_gate.states import (
    ForbiddenTransitionError,
    LinkNotLiveError,
    RearmRequiredError,
    TeleopLinkState,
)
from backend.teleop.safety_gate.velocity import EEVelocityLimiter
from backend.teleop.safety_gate.workspace import WorkspaceBox
from contracts.teleop import TeleopSample

_ZERO_VELOCITY: Vector3 = (0.0, 0.0, 0.0)


class LeaseLatchView(Protocol):
    """The read-only view of the deadman lease the gate consults before re-engaging.

    `backend.deadman.DeadmanController` satisfies this structurally through its
    `latched` property, so the gate reads the *same* latch the deadman owns without
    importing the concrete class or standing up a second lease. `latched` is True from
    the moment the lease expires until the operator completes the re-arm handshake.
    """

    @property
    def latched(self) -> bool:
        """Whether the deadman lease latch is currently engaged."""
        ...


def deadman_lease_view(controller: DeadmanController) -> LeaseLatchView:
    """Return the `WP-2A-02` deadman controller as the read-only latch view the gate reads.

    The gate depends on the deadman lease latch, never a lease of its own. This is the
    first-class expression of that dependency: it consumes `backend.deadman` — the single
    definition of the lease and its latch — and hands the controller back unchanged as a
    `LeaseLatchView`, so the gate reads the very latch the deadman owns and redefines none
    of it.

    Args:
        controller: The live `WP-2A-02` deadman controller.

    Returns:
        (LeaseLatchView) The controller, viewed through the read-only latch surface.
    """
    return controller


@dataclass(frozen=True)
class GateOutput:
    """The command and safety verdict of one gate tick.

    Attributes:
        command: The EE pose to send this tick. Always present — the gate never
            yields a no-command tick (`FR-TEL-079`).
        state: The link-safety state after this tick.
        link_health: The heartbeat verdict this tick.
        pose_accepted: Whether the received pose passed the sanity check (False when
            a degenerate/non-finite frame was discarded; only meaningful when
            following/aligning).
        wall_violated: Whether the target was outside the workspace box and projected.
        linear_limited: Whether the linear velocity limit clamped the step.
        angular_limited: Whether the angular velocity limit clamped the step.
        decelerating: Whether the gate is still ramping the EE velocity to zero inside
            a lost link (True during the decel phase, False once holding).
    """

    command: EEPose
    state: TeleopLinkState
    link_health: LinkHealth
    pose_accepted: bool
    wall_violated: bool
    linear_limited: bool
    angular_limited: bool
    decelerating: bool


class TeleopSafetyGate:
    """Drives the link-safety state machine and the per-tick command it emits."""

    def __init__(
        self,
        dt_sec: float,
        heartbeat: LinkHeartbeat,
        workspace: WorkspaceBox,
        velocity_limiter: EEVelocityLimiter,
        sanity: PoseSanityFilter,
        lease: LeaseLatchView,
        seed_pose: EEPose,
        decel_m_s2: float = DEFAULT_LINK_LOST_DECEL_M_S2,
        persistent_wall_ticks: int = DEFAULT_PERSISTENT_WALL_VIOLATION_TICKS,
    ) -> None:
        """Compose the gate over its filters, the reused lease view, and a seed pose.

        The gate starts in ALIGNING: FOLLOWING is only ever entered from a converged
        alignment, so a session that has just engaged must align before it follows.

        Args:
            dt_sec: The control period; must be positive.
            heartbeat: The VR link heartbeat (STALE = lost).
            workspace: The cartesian keep-in box.
            velocity_limiter: The EE cartesian velocity limiter.
            sanity: The pose-sanity filter; seeded with `seed_pose` here.
            lease: The read-only deadman lease latch view (`WP-2A-02`), consulted
                before any re-engage.
            seed_pose: The measured EE pose at engage — the initial command and hold
                target, so the gate has a valid command from its first tick.
            decel_m_s2: The linear deceleration applied on link loss before the hold.
            persistent_wall_ticks: Consecutive wall violations tolerated as projection
                before the gate escalates to a fault hold (`05` §4.3, S4 → S7).

        Raises:
            ValueError: If `dt_sec` is not positive.
        """
        if dt_sec <= 0.0:
            raise ValueError(f"control period dt_sec must be positive, got {dt_sec}")
        self._dt_sec = dt_sec
        self._heartbeat = heartbeat
        self._workspace = workspace
        self._velocity = velocity_limiter
        self._sanity = sanity
        self._lease = lease
        self._decel_m_s2 = decel_m_s2
        self._persistent_wall_ticks = persistent_wall_ticks

        self._sanity.seed(seed_pose)
        self._state = TeleopLinkState.ALIGNING
        self._command = seed_pose
        self._last_ee_velocity: Vector3 = _ZERO_VELOCITY
        self._decel_velocity: Vector3 = _ZERO_VELOCITY
        self._wall_streak = 0

    @property
    def state(self) -> TeleopLinkState:
        """The current link-safety state."""
        return self._state

    @property
    def command(self) -> EEPose:
        """The most recently emitted command pose."""
        return self._command

    def step(self, now_ns: int, target: EEPose, sample: TeleopSample | None = None) -> GateOutput:
        """Advance one control tick and return the command with its safety verdict.

        Args:
            now_ns: The current server-clock reading, nanoseconds.
            target: The upstream EE pose target for this tick. Used only while
                following or aligning; ignored while holding (the hold has its own
                command).
            sample: The VR frame that arrived this tick, or None if none did. A frame
                is registered with the heartbeat before the link is judged.

        Returns:
            (GateOutput) The command to send and the tick's safety flags.
        """
        if sample is not None:
            self._heartbeat.record(sample)
        health = self._heartbeat.health(now_ns)

        if not self._state.is_hold and health == LinkHealth.LOST:
            self._enter_link_lost()

        if self._state.is_hold:
            decelerating = self._advance_hold()
            return self._output(health, pose_accepted=True, decelerating=decelerating)
        return self._advance_follow(target, health)

    def notify_alignment_converged(self, now_ns: int) -> None:
        """Report that the aligner has converged, moving ALIGNING to FOLLOWING (S3 → S4).

        The alignment ramp itself is upstream (`WP-3B-09`); this is only the state
        transition the gate owns, taken when the aligner reports convergence.

        Args:
            now_ns: The current server-clock reading, nanoseconds.

        Raises:
            ForbiddenTransitionError: If called outside ALIGNING.
            LinkNotLiveError: If the link is not live — one cannot begin following a
                link delivering no fresh frames.
        """
        if self._state != TeleopLinkState.ALIGNING:
            raise ForbiddenTransitionError(
                f"alignment convergence is only valid in ALIGNING, not {self._state.name}"
            )
        if self._heartbeat.health(now_ns) == LinkHealth.LOST:
            raise LinkNotLiveError("cannot enter FOLLOWING while the VR link is lost")
        self._state = TeleopLinkState.FOLLOWING
        self._wall_streak = 0

    def request_reengage(self, now_ns: int) -> None:
        """Explicit operator re-engage out of a hold into ALIGNING (`FR-TEL-082`).

        This is the sole exit from LINK_LOST or IK_FAULT, and it lands in ALIGNING,
        never FOLLOWING — the `05` §4.2 #1/#3 forbidden direct resume is
        unrepresentable. It is refused while the VR link is still lost, and refused
        while the deadman lease latch is held: the lease re-arm handshake is the
        superior gate and must clear the latch first (`WP-2A-02` outranks link
        recovery).

        Args:
            now_ns: The current server-clock reading, nanoseconds.

        Raises:
            ForbiddenTransitionError: If not currently in a hold state.
            RearmRequiredError: If the deadman lease latch is engaged.
            LinkNotLiveError: If the VR link is still lost.
        """
        if not self._state.is_hold:
            raise ForbiddenTransitionError(
                f"re-engage is only valid from a hold state, not {self._state.name}"
            )
        if self._lease.latched:
            raise RearmRequiredError(
                "deadman lease latch is engaged; complete the re-arm handshake before "
                "re-engaging teleop — link recovery is not re-arming (WP-2A-02)"
            )
        if self._heartbeat.health(now_ns) == LinkHealth.LOST:
            raise LinkNotLiveError("cannot re-engage while the VR link is lost")
        self._state = TeleopLinkState.ALIGNING
        self._wall_streak = 0
        self._decel_velocity = _ZERO_VELOCITY

    def _enter_link_lost(self) -> None:
        """Move a following/aligning gate into LINK_LOST, capturing the coast velocity."""
        self._state = TeleopLinkState.LINK_LOST
        self._decel_velocity = self._last_ee_velocity
        self._wall_streak = 0

    def _advance_follow(self, target: EEPose, health: LinkHealth) -> GateOutput:
        """Filter the target and emit it while following or aligning.

        Runs the FOLLOWING/ALIGNING command pipeline — sanity discard, workspace
        projection, velocity limit — and escalates a persistent wall violation to a
        hold. Updates the last EE velocity so a subsequent link loss can decelerate
        from the true coasting velocity.

        Args:
            target: The upstream EE pose target.
            health: The heartbeat verdict this tick.

        Returns:
            (GateOutput) The emitted command and its flags.
        """
        sanity_result = self._sanity.accept(target)
        candidate = sanity_result.pose if sanity_result.pose is not None else self._command

        projection = self._workspace.project_pose(candidate)
        projected = EEPose(rotation=candidate.rotation, translation=projection.translation)

        limited = self._velocity.limit(self._command, projected)
        new_command = limited.pose

        self._last_ee_velocity = vector_scale(
            vector_sub(new_command.translation, self._command.translation), 1.0 / self._dt_sec
        )
        self._command = new_command

        if self._state == TeleopLinkState.FOLLOWING:
            self._wall_streak = self._wall_streak + 1 if projection.violated else 0
            if self._wall_streak >= self._persistent_wall_ticks:
                self._state = TeleopLinkState.IK_FAULT

        return self._output(
            health,
            pose_accepted=sanity_result.accepted,
            wall_violated=projection.violated,
            linear_limited=limited.linear_limited,
            angular_limited=limited.angular_limited,
            decelerating=False,
        )

    def _advance_hold(self) -> bool:
        """Decelerate the EE toward a stop, then hold, while in a hold state.

        The command keeps advancing by the shrinking coast velocity (decel phase)
        until the velocity reaches zero, after which the command is frozen (hold).
        The command stream never stops (`FR-TEL-079`).

        Returns:
            (bool) True while still decelerating, False once holding.
        """
        speed = vector_magnitude(self._decel_velocity)
        if speed <= 0.0:
            return False
        self._command = EEPose(
            rotation=self._command.rotation,
            translation=vector_add(
                self._command.translation, vector_scale(self._decel_velocity, self._dt_sec)
            ),
        )
        new_speed = max(0.0, speed - self._decel_m_s2 * self._dt_sec)
        self._decel_velocity = vector_scale(self._decel_velocity, new_speed / speed)
        return new_speed > 0.0

    def _output(
        self,
        health: LinkHealth,
        pose_accepted: bool,
        decelerating: bool,
        wall_violated: bool = False,
        linear_limited: bool = False,
        angular_limited: bool = False,
    ) -> GateOutput:
        """Assemble the tick's `GateOutput` from the current command and flags."""
        return GateOutput(
            command=self._command,
            state=self._state,
            link_health=health,
            pose_accepted=pose_accepted,
            wall_violated=wall_violated,
            linear_limited=linear_limited,
            angular_limited=angular_limited,
            decelerating=decelerating,
        )
