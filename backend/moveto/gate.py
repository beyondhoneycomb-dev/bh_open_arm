"""The numeric Move-to gate: check first, execute only on pass (WP-2D-09).

FR-MAN-015 makes a numeric Move-to conditional: a typed joint or EE target executes
*only after* it passes a limit check and — for an EE pose — an IK-solution-existence
check. The single failure this WP's audit hunts is a move that executes without the
check, so this module is built so that there is exactly one execution site and it is
structurally unreachable except through the check:

- ``check`` runs the checks and returns an inert report. It moves nothing: the EE
  probe restores the arm state, and the joint path only reads the committed pose.
- ``execute`` calls ``check``, and returns a refusal the instant ``report.passed`` is
  false. Only past that guard does it reach ``_commit`` — the one method that mutates
  the arm — so "execute without the check" cannot be written without deleting the
  guard, which the static acceptance test forbids.

Both checks are the reused primitives, not re-implementations: the limit check runs
WP-2A-03's ``JogClampPath`` stage clamps, and the IK-existence check runs WP-2D-01's
``CartesianJog.plan_pose(commit=False)``. There is no second IK and no second limit
envelope here.
"""

from __future__ import annotations

import numpy as np

from backend.cartesian_jog import CartesianJog, JogStopReason, build_cartesian_jog
from backend.cartesian_jog.constants import ARM_JOINTS_PER_SIDE
from backend.jogclamp import JogClampPath
from backend.moveto.constants import (
    BIMANUAL_WIDTH,
    FIRST_HUMAN_JOINT_NUMBER,
    arm_slot_base,
)
from backend.moveto.report import (
    IkExistenceFinding,
    LimitFinding,
    MoveToCheckReport,
    MoveToResult,
    limit_findings_from_config,
)
from backend.moveto.request import JointMoveTo, PoseMoveTo
from contracts.units import Rad, rad_to_deg

_JOINT_KIND = "joint"
_POSE_KIND = "pose"


class NumericMoveTo:
    """Gate a typed joint/EE Move-to on a limit + IK-existence check before executing.

    Not thread-safe: it drives one ``CartesianJog`` (which holds the committed arm
    state) and consumes one ``JogClampPath`` (the WP-2A-03 limit envelope). It owns
    neither — both are injected reused primitives — and it adds only the gate: the
    checks, the per-reason report, and the single guarded execution site.
    """

    def __init__(self, jog: CartesianJog, clamp: JogClampPath) -> None:
        """Bind the gate to a Cartesian jog and a validated clamp envelope.

        Args:
            jog: The WP-2D-01 Cartesian jog whose IK probe proves EE reachability and
                whose committed state a move advances.
            clamp: The WP-2A-03 jog-path clamp whose validated ``SafetyLimits`` is the
                position envelope the limit check reads.

        Raises:
            ValueError: When the clamp envelope is not the 16-dim bimanual width the
                jog's committed solution uses; a Move-to checks the whole configuration,
                so the envelope must span it.
        """
        if clamp.limits.width != BIMANUAL_WIDTH:
            raise ValueError(
                f"clamp envelope width {clamp.limits.width} must equal the bimanual "
                f"solution width {BIMANUAL_WIDTH}; the Move-to checks the full configuration"
            )
        self._jog = jog
        self._clamp = clamp

    @property
    def jog(self) -> CartesianJog:
        """The Cartesian jog this gate drives."""
        return self._jog

    @property
    def clamp(self) -> JogClampPath:
        """The clamp whose envelope the limit check reads."""
        return self._clamp

    # -- checks (inert) ----------------------------------------------------------

    def check(self, request: JointMoveTo | PoseMoveTo) -> MoveToCheckReport:
        """Run the pre-execution checks for a request without moving the arm.

        Args:
            request: A joint-space or EE-pose numeric target.

        Returns:
            (MoveToCheckReport) The per-reason outcome; ``passed`` gates execution.
        """
        if isinstance(request, JointMoveTo):
            return self._check_joint(request)
        return self._check_pose(request)

    def _check_joint(self, request: JointMoveTo) -> MoveToCheckReport:
        """Check a joint target: only the limit check applies (the joints are the config)."""
        config = self._config_with_side_arm(request.side, request.joints_rad)
        findings = self._limit_findings(config, request.side)
        return MoveToCheckReport(
            kind=_JOINT_KIND,
            side=request.side,
            ik_checked=False,
            limit_findings=findings,
        )

    def _check_pose(self, request: PoseMoveTo) -> MoveToCheckReport:
        """Check an EE pose: IK-existence first, then the limit check on the solution.

        The probe is ``plan_pose(commit=False)``, which restores the arm state, so the
        check leaves the committed pose untouched. When a solution exists, its 16-dim
        joint values are re-checked against the operational envelope — the adapter only
        clamps to the wider mechanical (soft) limits, so an operational violation is a
        genuine additional finding the IK-existence check alone would miss.
        """
        probe = self._jog.plan_pose(
            request.side,
            request.pose_array(),
            frame=request.frame,
            tcp=request.tcp,
            commit=False,
        )
        if probe.stopped:
            reason = probe.reason if probe.reason is not None else JogStopReason.NO_SOLUTION
            return MoveToCheckReport(
                kind=_POSE_KIND,
                side=request.side,
                ik_checked=True,
                ik_finding=IkExistenceFinding(reason=reason, detail=probe.detail),
            )
        solution = np.asarray(probe.solution_rad, dtype=float)
        findings = self._limit_findings(solution, request.side)
        return MoveToCheckReport(
            kind=_POSE_KIND,
            side=request.side,
            ik_checked=True,
            limit_findings=findings,
        )

    # -- execution (the one guarded mutation site) -------------------------------

    def execute(self, request: JointMoveTo | PoseMoveTo) -> MoveToResult:
        """Check a request and execute it only if every check passed.

        This is the sole public execution entry, and it always checks first. A request
        that fails any check returns immediately with ``executed=False`` and the arm
        unmoved (acceptance ①); only a passing request reaches the commit.

        Args:
            request: A joint-space or EE-pose numeric target.

        Returns:
            (MoveToResult) The checks and whether the move committed.
        """
        report = self.check(request)
        if not report.passed:
            return MoveToResult(
                executed=False,
                report=report,
                detail="Move-to refused: checks did not pass",
            )
        return self._commit(request, report)

    def _commit(self, request: JointMoveTo | PoseMoveTo, report: MoveToCheckReport) -> MoveToResult:
        """Advance the arm to a checked target. Reached only past the passed gate.

        The one place in this module that mutates the committed arm state. It is private
        and called only by ``execute`` after ``report.passed`` is confirmed, so there is
        no admitted path to motion that skips the checks.
        """
        if isinstance(request, JointMoveTo):
            config = self._config_with_side_arm(request.side, request.joints_rad)
            self._jog.seed(config)
            return MoveToResult(
                executed=True,
                report=report,
                committed_solution=self._jog.committed_solution(),
                detail="joint Move-to committed",
            )
        # An EE Move-to re-drives the IK to the target and commits; resume() clears any
        # latched jog stop so a checked absolute reposition is not blocked by a prior hold.
        self._jog.resume()
        result = self._jog.plan_pose(
            request.side,
            request.pose_array(),
            frame=request.frame,
            tcp=request.tcp,
            commit=True,
        )
        return MoveToResult(
            executed=result.committed,
            report=report,
            committed_solution=self._jog.committed_solution() if result.committed else None,
            accepted=result.accepted,
            detail="EE Move-to committed" if result.committed else "EE Move-to did not converge",
        )

    # -- internals ---------------------------------------------------------------

    def _config_with_side_arm(self, side: str, joints_rad: tuple[float, ...]) -> np.ndarray:
        """Return the committed 16-dim config with one side's seven arm joints replaced.

        The unmoved side and both grippers keep their committed values, so the limit
        check only ever attributes a violation to a joint the request actually set.
        """
        config = self._jog.committed_solution()
        base = arm_slot_base(side)
        config[base : base + ARM_JOINTS_PER_SIDE] = np.asarray(joints_rad, dtype=float)
        return config

    def _limit_findings(self, config: np.ndarray, side: str) -> tuple[LimitFinding, ...]:
        """Run WP-2A-03's stage clamps over the config and attribute per-joint violations.

        Only the moved side's seven arm joints are reported: the clamp runs over the
        full width (its envelope is 16-dim), but a Move-to should not refuse over an
        unmoved joint that merely sits outside the operational band in the current pose.
        """
        config_deg = tuple(rad_to_deg(Rad(float(value))) for value in config)
        mechanical_clamped, _ = self._clamp.clamp_stage1(config_deg)
        operational_clamped, _ = self._clamp.clamp_stage2(config_deg)
        base = arm_slot_base(side)
        slots = tuple(range(base, base + ARM_JOINTS_PER_SIDE))
        return limit_findings_from_config(
            config_deg=config_deg,
            mechanical_clamped=mechanical_clamped,
            operational_clamped=operational_clamped,
            envelope_mechanical=self._clamp.limits.mechanical_deg,
            envelope_operational=self._clamp.limits.operational_deg,
            side=side,
            slots=slots,
            first_human_joint_number=FIRST_HUMAN_JOINT_NUMBER,
        )


def build_numeric_move_to(
    clamp: JogClampPath,
    jog: CartesianJog | None = None,
    xml: str | None = None,
    q_lift: float = 0.0,
) -> NumericMoveTo:
    """Build a Move-to gate over an injected clamp envelope and (optional) jog.

    The clamp is required and injected — WP-2D-09 does not invent the safety envelope,
    it consumes WP-2A-03's. When no jog is given, one is built through
    ``build_cartesian_jog`` (the sanctioned ordered-IK entry), so there is still no
    second IK.

    Args:
        clamp: The WP-2A-03 jog-path clamp carrying the validated 16-dim envelope.
        jog: A prebuilt Cartesian jog, or None to build the default fixed-cell jog.
        xml: MJCF path passed to ``build_cartesian_jog`` when it builds the jog.
        q_lift: Initial lifter height passed to ``build_cartesian_jog``.

    Returns:
        (NumericMoveTo) A ready gate.
    """
    resolved_jog = jog if jog is not None else build_cartesian_jog(xml=xml, q_lift=q_lift)
    return NumericMoveTo(jog=resolved_jog, clamp=clamp)
