"""The model-error monitor: a residual margin tracker that calls for re-identification.

WP-2C-09's second job (`02b` §3): keep a moving average and σ of the GMO residual
`r` per joint, and raise a "model needs re-identification" alert when the safety
margin shrinks (`12` FR-SAF-066, FR-MAN-058). The margin is the headroom between the
residual's k-σ envelope and the collision threshold; a payload the model does not
know about, or friction drift as the motors heat, pushes `τ_meas` away from
`τ_model`, the residual grows, and the margin falls. A falling margin is the signal
that the identified model no longer matches the arm.

What this monitor is not: it is not the collision detector and not the detection
activation gate (WP-2C-02 owns that; the band default is OFF). Its alert is advisory
— a prompt to re-identify — never a torque action. And it invents no numbers: the
per-joint collision threshold is the WP-2C-03 calibration output, hardware-deferred,
and is a required input here. A monitor that shipped a baked "measured" threshold
would fake a green the calibration has not earned. The gripper joint is excluded by
default because WP-2C-11 disables residual detection there (no finger-dynamics model;
grasp reaction is a standing offset).
"""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from backend.event_ring.constants import ARM_JOINT_COUNT

# WP-2C-03 states its threshold suggestion as `max + 3σ`; the monitor's margin uses
# the same 3σ envelope so its headroom is measured against the residual band the
# threshold was set from, not a looser or tighter one.
DEFAULT_SIGMA_MULTIPLIER = 3.0

# Below two samples a standard deviation is undefined; the monitor reports σ=0 and
# withholds any alert until it has enough of a window to characterise the residual.
_MIN_SAMPLES_FOR_SIGMA = 2


@dataclass(frozen=True)
class JointMargin:
    """One joint's residual statistics and its margin against the collision threshold.

    Attributes:
        joint_index: Zero-based motor index.
        threshold_nm: The collision threshold for this joint (WP-2C-03), newton-metres.
        residual_mean_nm: Moving average of `|r|` over the window, newton-metres.
        residual_sigma_nm: Standard deviation of `|r|` over the window, newton-metres.
        margin_nm: `threshold − (mean + k·σ)` — headroom before the residual envelope
            reaches the threshold. Falls as the model drifts.
        baseline_margin_nm: The margin captured when the model was fresh, or None if
            no baseline has been frozen.
        decreased: Whether the margin has fallen below the baseline by more than the
            configured tolerance — the per-joint re-identification signal.
    """

    joint_index: int
    threshold_nm: float
    residual_mean_nm: float
    residual_sigma_nm: float
    margin_nm: float
    baseline_margin_nm: float | None
    decreased: bool


@dataclass(frozen=True)
class ModelReidentificationAlert:
    """The advisory that the identified model no longer matches the arm.

    Attributes:
        joints: The joints whose margin fell below baseline, ascending.
        margins: The full per-joint margin snapshot at the time of the alert.
        t_mos_max_degc: The hottest drive temperature seen in the window, or None —
            context for whether the drift is thermal.
        t_rotor_max_degc: The hottest rotor temperature seen in the window, or None.
        detail: A human-readable summary naming the joints and the shortfall.
    """

    joints: tuple[int, ...]
    margins: tuple[JointMargin, ...]
    t_mos_max_degc: float | None
    t_rotor_max_degc: float | None
    detail: str


@dataclass(frozen=True)
class MarginReport:
    """The monitor's assessment at one point in time.

    Attributes:
        margins: Per-joint margin, one entry per tracked joint in tracking order.
        alert: The re-identification alert when any joint's margin fell, else None.
    """

    margins: tuple[JointMargin, ...]
    alert: ModelReidentificationAlert | None

    @property
    def reidentify_needed(self) -> bool:
        """Whether the model should be re-identified (any margin fell below baseline)."""
        return self.alert is not None


class ModelErrorMonitor:
    """Tracks per-joint residual margin and flags when the model needs re-identification.

    Ownership: holds one bounded window of `|r|` per tracked joint and, once frozen,
    the healthy-model baseline margins. It computes; it commands nothing. Fed one
    residual row per tick (`update`), it produces a `MarginReport` on demand
    (`assess`), and raises no exception on drift — the drift is data on the report,
    which the harness surfaces to the operator.
    """

    def __init__(
        self,
        joint_indices: tuple[int, ...],
        thresholds_nm: Mapping[int, float],
        window_len: int,
        margin_decrease_tolerance_nm: float,
        sigma_multiplier: float = DEFAULT_SIGMA_MULTIPLIER,
        min_samples: int = _MIN_SAMPLES_FOR_SIGMA,
    ) -> None:
        """Configure the tracked joints and the re-identification policy.

        Args:
            joint_indices: The joints to track. The gripper is excluded by default
                via `for_arm_joints` (WP-2C-11).
            thresholds_nm: The collision threshold per tracked joint (WP-2C-03),
                newton-metres. Required — the monitor never supplies its own.
            window_len: Rolling window length, in samples, for the mean and σ.
            margin_decrease_tolerance_nm: How far the margin may fall below its
                baseline before a joint is flagged for re-identification.
            sigma_multiplier: The k in the `mean + k·σ` residual envelope.
            min_samples: Samples required before a joint is assessed at all.

        Raises:
            KeyError: If any tracked joint has no threshold.
        """
        missing = [index for index in joint_indices if index not in thresholds_nm]
        if missing:
            raise KeyError(f"no collision threshold for joint(s) {missing}")
        self._joint_indices = joint_indices
        self._thresholds_nm = dict(thresholds_nm)
        self._window_len = window_len
        self._tolerance_nm = margin_decrease_tolerance_nm
        self._sigma_multiplier = sigma_multiplier
        self._min_samples = min_samples
        self._windows: dict[int, deque[float]] = {
            index: deque(maxlen=window_len) for index in joint_indices
        }
        self._baseline: dict[int, float] = {}
        self._t_mos_max_degc: float | None = None
        self._t_rotor_max_degc: float | None = None

    @classmethod
    def for_arm_joints(
        cls,
        thresholds_nm: Mapping[int, float],
        window_len: int,
        margin_decrease_tolerance_nm: float,
        sigma_multiplier: float = DEFAULT_SIGMA_MULTIPLIER,
        min_samples: int = _MIN_SAMPLES_FOR_SIGMA,
    ) -> ModelErrorMonitor:
        """Build a monitor over the arm joints only, excluding the gripper (WP-2C-11).

        Args:
            thresholds_nm: The collision threshold per arm joint, newton-metres.
            window_len: Rolling window length, in samples.
            margin_decrease_tolerance_nm: Margin fall tolerance before flagging.
            sigma_multiplier: The k in the `mean + k·σ` envelope.
            min_samples: Samples required before a joint is assessed.

        Returns:
            (ModelErrorMonitor) A monitor tracking joints `0..ARM_JOINT_COUNT-1`.
        """
        return cls(
            joint_indices=tuple(range(ARM_JOINT_COUNT)),
            thresholds_nm=thresholds_nm,
            window_len=window_len,
            margin_decrease_tolerance_nm=margin_decrease_tolerance_nm,
            sigma_multiplier=sigma_multiplier,
            min_samples=min_samples,
        )

    def update(
        self,
        residuals_nm: Sequence[float],
        t_mos_degc: Sequence[float] | None = None,
        t_rotor_degc: Sequence[float] | None = None,
    ) -> None:
        """Fold one tick's residual row (and optional temperatures) into the windows.

        Args:
            residuals_nm: Per-joint residual `r`, newton-metres, indexable by every
                tracked joint index. The absolute value is windowed.
            t_mos_degc: Optional per-joint drive temperatures; their max is retained
                as alert context.
            t_rotor_degc: Optional per-joint rotor temperatures; their max is retained.
        """
        for index in self._joint_indices:
            self._windows[index].append(abs(residuals_nm[index]))
        if t_mos_degc is not None and t_mos_degc:
            self._t_mos_max_degc = max(t_mos_degc)
        if t_rotor_degc is not None and t_rotor_degc:
            self._t_rotor_max_degc = max(t_rotor_degc)

    def freeze_baseline(self) -> None:
        """Capture the current margins as the healthy-model baseline.

        Called once the model is freshly identified and the arm is running clean, so
        later drift is measured as a fall from a known-good margin rather than against
        an absolute floor. Only joints that have reached `min_samples` are frozen —
        `_margins` yields exactly those.
        """
        for margin in self._margins():
            self._baseline[margin.joint_index] = margin.margin_nm

    def assess(self) -> MarginReport:
        """Compute per-joint margins and the re-identification alert, if any.

        Returns:
            (MarginReport) The per-joint margins and, when a margin fell below its
            baseline by more than the tolerance, the alert naming those joints.
        """
        margins = self._margins()
        fallen = tuple(margin.joint_index for margin in margins if margin.decreased)
        if not fallen:
            return MarginReport(margins=margins, alert=None)
        detail = (
            f"joints {list(fallen)} margin fell ≥ {self._tolerance_nm:g} Nm below baseline "
            "— model needs re-identification"
        )
        alert = ModelReidentificationAlert(
            joints=fallen,
            margins=margins,
            t_mos_max_degc=self._t_mos_max_degc,
            t_rotor_max_degc=self._t_rotor_max_degc,
            detail=detail,
        )
        return MarginReport(margins=margins, alert=alert)

    def _margins(self) -> tuple[JointMargin, ...]:
        """Compute the current margin for every tracked joint with enough samples."""
        return tuple(
            self._joint_margin(index)
            for index in self._joint_indices
            if len(self._windows[index]) >= self._min_samples
        )

    def _joint_margin(self, joint_index: int) -> JointMargin:
        """Compute one joint's residual statistics, margin, and decrease verdict."""
        window = self._windows[joint_index]
        count = len(window)
        mean = sum(window) / count
        variance = sum((value - mean) ** 2 for value in window) / (count - 1)
        sigma = variance**0.5
        threshold = self._thresholds_nm[joint_index]
        margin = threshold - (mean + self._sigma_multiplier * sigma)
        baseline = self._baseline.get(joint_index)
        decreased = baseline is not None and margin < baseline - self._tolerance_nm
        return JointMargin(
            joint_index=joint_index,
            threshold_nm=threshold,
            residual_mean_nm=mean,
            residual_sigma_nm=sigma,
            margin_nm=margin,
            baseline_margin_nm=baseline,
            decreased=decreased,
        )
