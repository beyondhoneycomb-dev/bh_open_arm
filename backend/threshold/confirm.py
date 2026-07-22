"""The per-joint confirm / hysteresis debouncer — the anti-chatter core of WP-2C-04 (FR-SAF-022).

Raw `|r_i| > thr_i` chatters: communication jitter and 12-bit quantisation push the residual back
and forth across a single threshold, and a bare comparison would flip the collision flag on every
crossing. This gate removes both failure directions with a two-sided debounce, per joint:

* Rising edge (arm -> confirmed): the residual must exceed the threshold for `confirm_samples`
  *consecutive* samples. One sample at or below the threshold resets the run, so an oscillation that
  dips below every few samples never accumulates a confirmation — a single spike cannot fire.
* Falling edge (confirmed -> released): once confirmed, a joint releases only when its residual
  drops to `hysteresis_ratio x thr_i`. Between that release level and the detection threshold it
  holds confirmed, so a residual hovering around thr_i does not toggle the confirmed signal.

The gate reports the residual-level confirmed / released transitions only. The operator-ack latch
that keeps a *reaction* engaged until acknowledged is a separate concern (WP-2C-05); folding it in
here would put two owners on one latch, which the audit hunts for.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.threshold.constants import N_ARM_JOINTS
from backend.threshold.errors import ThresholdConfigError
from backend.threshold.modes import ThresholdConfig


@dataclass(frozen=True)
class GateUpdate:
    """The outcome of feeding one sample to the gate.

    Attributes:
        detected: Whether any enabled joint is currently in the confirmed state.
        confirmed: Per-joint confirmed flag after this sample, `N_ARM_JOINTS` wide.
        newly_confirmed: Joint indices that transitioned to confirmed on this sample.
        newly_released: Joint indices that transitioned out of confirmed on this sample.
    """

    detected: bool
    confirmed: tuple[bool, ...]
    newly_confirmed: tuple[int, ...]
    newly_released: tuple[int, ...]


class ConfirmHysteresisGate:
    """Stateful per-joint confirm/hysteresis debouncer over the residual-vs-threshold comparison.

    One instance tracks one detection session: it holds a consecutive-over counter and a confirmed
    flag per joint, and is driven one sample at a time by `update`. Not thread-safe; it belongs to
    the single CAN-owning detection loop (FR-SAF-001) and is stepped from that loop alone.
    """

    def __init__(self, config: ThresholdConfig) -> None:
        """Build a gate from the debounce parameters of a threshold configuration.

        Args:
            config: Supplies `confirm_samples`, `hysteresis_ratio`, and `per_joint_enable`.
        """
        self._confirm_samples = config.confirm_samples
        self._hysteresis_ratio = config.hysteresis_ratio
        self._enabled = tuple(config.per_joint_enable)
        self._confirmed = [False] * N_ARM_JOINTS
        self._consecutive_over = [0] * N_ARM_JOINTS

    @property
    def confirmed(self) -> tuple[bool, ...]:
        """Current per-joint confirmed flags."""
        return tuple(self._confirmed)

    @property
    def detected(self) -> bool:
        """Whether any enabled joint is currently confirmed."""
        return any(self._confirmed)

    def reset(self) -> None:
        """Clear all confirmed flags and consecutive-over counters (re-arm the gate)."""
        self._confirmed = [False] * N_ARM_JOINTS
        self._consecutive_over = [0] * N_ARM_JOINTS

    def update(self, residual: tuple[float, ...], thresholds: tuple[float, ...]) -> GateUpdate:
        """Advance the debounce by one sample and report any transition.

        Args:
            residual: Per-joint GMO residual r_i [Nm] for this sample, `N_ARM_JOINTS` wide.
            thresholds: Per-joint detection threshold [Nm] for this sample (from
                `effective_thresholds`), `N_ARM_JOINTS` wide.

        Returns:
            (GateUpdate) The confirmed flags and the transitions caused by this sample.

        Raises:
            ThresholdConfigError: If `residual` or `thresholds` is not `N_ARM_JOINTS` wide.
        """
        if len(residual) != N_ARM_JOINTS:
            raise ThresholdConfigError(
                f"residual must be {N_ARM_JOINTS} joints wide, got {len(residual)}"
            )
        if len(thresholds) != N_ARM_JOINTS:
            raise ThresholdConfigError(
                f"thresholds must be {N_ARM_JOINTS} joints wide, got {len(thresholds)}"
            )

        newly_confirmed: list[int] = []
        newly_released: list[int] = []
        for joint in range(N_ARM_JOINTS):
            if not self._enabled[joint]:
                continue
            magnitude = abs(residual[joint])
            threshold = thresholds[joint]
            if self._confirmed[joint]:
                if magnitude <= threshold * self._hysteresis_ratio:
                    self._confirmed[joint] = False
                    self._consecutive_over[joint] = 0
                    newly_released.append(joint)
            elif magnitude > threshold:
                self._consecutive_over[joint] += 1
                if self._consecutive_over[joint] >= self._confirm_samples:
                    self._confirmed[joint] = True
                    self._consecutive_over[joint] = 0
                    newly_confirmed.append(joint)
            else:
                self._consecutive_over[joint] = 0

        return GateUpdate(
            detected=any(self._confirmed),
            confirmed=tuple(self._confirmed),
            newly_confirmed=tuple(newly_confirmed),
            newly_released=tuple(newly_released),
        )
