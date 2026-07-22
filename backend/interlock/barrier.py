"""The B-2D.0 dry-run hard-gate: forbid a REAL transition until a dry-run passes.

WP-2A-00 hangs the Wave 0-C dry-run in front of real transmission. The mechanism it
gates on already exists and is *reused, not rebuilt*: ``sim.dryrun`` owns the six
checks, the ``DryRunVerdict`` report schema, and the ``TransmissionGrant`` token
whose sole minters are ``authorize_transmission`` (passing verdict only) and
``authorize_with_modal_confirm`` (the one sanctioned operator override). This module
adds the piece Wave 0-C does not have: **state**. ``sim.dryrun.interlock`` is a pure
verdict-to-grant function; a real-send session needs a standing gate that remembers
whether *this* session's dry-run passed and, on that basis, permits or forbids the
transition into real transmission (the single writer, `WP-1-03`'s ``ActuationScheduler``).

The barrier is fail-closed: a fresh one is ``PENDING`` and authorises nothing. A
grant is obtained only by consuming a verdict through ``sim.dryrun``'s minters, so
the barrier can never manufacture authorisation — the one bypass surface (fabricating
a ``TransmissionGrant``) is closed at runtime by that token's key-gated constructor
and at source by ``backend.interlock.staticcheck`` (acceptance ④). ``guard_real_transition``
is the concrete hard block: the caller's real-send starter runs only when armed, so a
failing dry-run leaves it un-invoked and real transmission never begins.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar

import mujoco

from backend.interlock.decision import (
    InterlockDecision,
    InterlockState,
    RealTransitionBlockedError,
)
from backend.interlock.walls import assert_cell_walls_active
from sim.dryrun.interlock import (
    HardBlockError,
    ModalConfirmation,
    TransmissionGrant,
    authorize_transmission,
    authorize_with_modal_confirm,
)
from sim.dryrun.runner import DryRunRunner, Waypoint
from sim.dryrun.violation import DryRunVerdict

T = TypeVar("T")


def _model_under_check(runner: DryRunRunner) -> mujoco.MjModel:
    """Return the exact compiled model the runner runs its six checks over.

    The wall-activation precondition (③) must read the *same* model the
    cell-collision check reads, not a parallel recompile that could disagree after a
    runtime ``contype``/``conaffinity`` toggle (WP-2C-07). ``DryRunRunner`` (Wave
    0-C, not editable here) exposes no public accessor for it, so the interlock reads
    the owned model directly; this single site is the reason for the private read.
    """
    return runner._model  # the exact model the six checks read; no public accessor exists


class RealSendBarrier:
    """A standing gate that permits real transmission only after a passing dry-run.

    Ownership/lifecycle: one barrier serves one real-send session. Not thread-safe.
    It holds at most one ``TransmissionGrant`` — the Wave 0-C token authorising
    transmission — and hands it out only through ``authorize_real_transition``. The
    grant can only ever have come from ``sim.dryrun``'s sanctioned minters, so the
    barrier's armed state is un-forgeable.
    """

    def __init__(self) -> None:
        """Start fail-closed: pending, holding no grant, authorising nothing."""
        self._state = InterlockState.PENDING
        self._grant: TransmissionGrant | None = None

    @property
    def state(self) -> InterlockState:
        """The barrier's current real-send posture."""
        return self._state

    @property
    def permits_real_send(self) -> bool:
        """Whether the barrier currently authorises real transmission."""
        return self._state is InterlockState.ARMED and self._grant is not None

    def gate(self, verdict: DryRunVerdict) -> InterlockDecision:
        """Consume a dry-run verdict and set the real-send posture from it (①).

        A passing verdict mints a grant and arms the barrier; a failing one
        hard-blocks — the barrier disarms and records the verdict's violations as the
        block's report. This never bypasses: the pass/fail decision is
        ``sim.dryrun``'s ``authorize_transmission``, reused verbatim.

        Args:
            verdict: The Wave 0-C dry-run report to gate on.

        Returns:
            (InterlockDecision) Armed with the verdict when it passed, blocked with
            its violations otherwise.
        """
        try:
            grant = authorize_transmission(verdict)
        except HardBlockError:
            self._state = InterlockState.BLOCKED
            self._grant = None
            return InterlockDecision(
                state=InterlockState.BLOCKED, via_modal_confirm=False, verdict=verdict
            )
        self._grant = grant
        self._state = InterlockState.ARMED
        return InterlockDecision(
            state=InterlockState.ARMED, via_modal_confirm=False, verdict=verdict
        )

    def override(
        self, verdict: DryRunVerdict, confirmation: ModalConfirmation
    ) -> InterlockDecision:
        """Arm a failing verdict through the one sanctioned operator override.

        This is the only path that arms on a failing verdict, and it is not a bypass:
        it reuses ``sim.dryrun``'s ``authorize_with_modal_confirm``, which refuses any
        confirmation that does not acknowledge every violated check. Exposing it here
        keeps the sole override explicit rather than hidden.

        Args:
            verdict: The dry-run report, which may carry violations.
            confirmation: The operator's acknowledgement of every violated check.

        Returns:
            (InterlockDecision) Armed via the modal-confirm path.

        Raises:
            HardBlockError: If the confirmation does not cover every violation.
        """
        grant = authorize_with_modal_confirm(verdict, confirmation)
        self._grant = grant
        self._state = InterlockState.ARMED
        return InterlockDecision(
            state=InterlockState.ARMED, via_modal_confirm=True, verdict=verdict
        )

    def run_and_gate(
        self, runner: DryRunRunner, waypoints: Sequence[Waypoint]
    ) -> InterlockDecision:
        """Verify the scene, run the dry-run, and gate on its verdict end-to-end.

        The runner's mere existence is proof a clamp canon was selected (its
        constructor refuses an unselected one — acceptance ②), so this path cannot be
        driven without one. Before trusting the verdict, the six cell walls are
        checked active on the exact model the checks ran over (③); a vacuous
        cell-collision check must not gate real-send.

        Args:
            runner: A constructed Wave 0-C dry-run runner (proof of a selected canon).
            waypoints: The trajectory to validate.

        Returns:
            (InterlockDecision) The gating decision over the produced verdict.

        Raises:
            CellWallsInactiveError: If a cell wall is collision-inactive (③).
        """
        assert_cell_walls_active(_model_under_check(runner))
        verdict = runner.run_trajectory(waypoints)
        return self.gate(verdict)

    def authorize_real_transition(self) -> TransmissionGrant:
        """Return the grant authorising the REAL transition, or hard-block.

        Returns:
            (TransmissionGrant) The held grant, only when the barrier is armed.

        Raises:
            RealTransitionBlockedError: If no passing dry-run has armed the barrier —
                the REAL transition is forbidden (`02b` §1.2 WP-2A-00).
        """
        if self._grant is None:
            raise RealTransitionBlockedError(
                "real transition forbidden: no dry-run has passed the interlock, so no "
                "transmission grant exists to authorise it (02b §1.2 WP-2A-00)"
            )
        return self._grant

    def guard_real_transition(self, start_real_send: Callable[[TransmissionGrant], T]) -> T:
        """Run the caller's real-send starter only when armed; hard-block otherwise.

        This is the barrier's concrete forbiddance: ``start_real_send`` is whatever
        begins real transmission on the single writer (`WP-1-03` scheduler), and it
        receives the grant as proof. When the dry-run did not pass, the grant does not
        exist, the starter is never invoked, and real transmission never begins.

        Args:
            start_real_send: The callback that begins real transmission, given the grant.

        Returns:
            (T) Whatever the starter returns.

        Raises:
            RealTransitionBlockedError: If the barrier is not armed.
        """
        grant = self.authorize_real_transition()
        return start_real_send(grant)
