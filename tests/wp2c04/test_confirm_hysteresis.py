"""Acceptance ① — chatter injection does not make confirm/release oscillate (FR-SAF-022).

Two failure directions are ruled out and measured against the naive `|r| > thr` comparator that has
neither guard:

* a residual oscillating across the threshold never confirms, because confirmation needs
  `confirm_samples` *consecutive* over-threshold samples and the dip resets the run;
* a residual chattering inside the hysteresis band after a confirmation never releases, because
  release needs the residual below `hysteresis_ratio x thr`.

The metric is the number of confirmed-signal transitions: the gate produces at most one where the
bare comparator produces many.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.threshold import (
    ConfirmHysteresisGate,
    ThresholdCalibration,
    ThresholdConfig,
    ThresholdMode,
)

_THR0 = ThresholdCalibration.literature_default().thr0
_JOINT = 0
_THRESHOLD = _THR0[_JOINT]


def _gate(confirm_samples: int = 5, hysteresis_ratio: float = 0.7) -> ConfirmHysteresisGate:
    """A gate on the literature base threshold with the given debounce parameters."""
    config = ThresholdConfig(
        calibration=ThresholdCalibration.literature_default(),
        mode=ThresholdMode.STATIC,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(0.0,) * 7,
        use_accel_term=False,
        confirm_samples=confirm_samples,
        hysteresis_ratio=hysteresis_ratio,
        per_joint_enable=(True,) * 7,
    )
    return ConfirmHysteresisGate(config)


def _residual_row(value: float) -> tuple[float, ...]:
    """A 7-wide residual row that is `value` on the driven joint and 0 elsewhere."""
    return tuple(value if index == _JOINT else 0.0 for index in range(7))


def _run(gate: ConfirmHysteresisGate, magnitudes: Sequence[float]) -> list[bool]:
    """Drive the gate over a residual-magnitude trace and return the per-sample detected signal."""
    thresholds = tuple(_THR0)
    return [gate.update(_residual_row(m), thresholds).detected for m in magnitudes]


def _transitions(signal: Sequence[bool]) -> int:
    """Count how many times a boolean signal changes value."""
    return sum(1 for a, b in zip(signal, signal[1:], strict=False) if a != b)


def _naive_detect(magnitudes: Sequence[float]) -> list[bool]:
    """The bare `|r| > thr` comparator — no confirm, no hysteresis: the thing we improve on."""
    return [m > _THRESHOLD for m in magnitudes]


def test_confirms_only_after_consecutive_samples() -> None:
    """Confirmation lands exactly on the `confirm_samples`-th consecutive over-threshold sample."""
    gate = _gate(confirm_samples=5)
    over = _THRESHOLD * 1.5
    detected = _run(gate, [over] * 5)
    assert detected == [False, False, False, False, True]


def test_single_dip_resets_the_consecutive_run() -> None:
    """One sample at or below threshold resets the run, so a spike train never confirms."""
    gate = _gate(confirm_samples=5)
    over = _THRESHOLD * 1.5
    under = _THRESHOLD * 0.5
    # Over four times, dip, over four times: never five in a row.
    detected = _run(gate, [over, over, over, over, under, over, over, over, over])
    assert not any(detected)


def test_alternating_chatter_never_confirms() -> None:
    """A residual alternating across the threshold each sample never confirms; the naive flips."""
    gate = _gate(confirm_samples=5)
    over = _THRESHOLD * 1.3
    under = _THRESHOLD * 0.6
    chatter = [over if step % 2 == 0 else under for step in range(40)]
    detected = _run(gate, chatter)

    assert not any(detected)
    assert _transitions(detected) == 0
    assert _transitions(_naive_detect(chatter)) > 10


def test_hysteresis_holds_confirmed_across_band_chatter() -> None:
    """After confirming, chatter inside [0.7 x thr, thr] stays confirmed — no release."""
    gate = _gate(confirm_samples=5, hysteresis_ratio=0.7)
    over = _THRESHOLD * 1.2
    in_band = _THRESHOLD * 0.85  # above the 0.7 release level, below the detection threshold
    trace = [over] * 5 + [in_band if step % 2 == 0 else over for step in range(30)]
    detected = _run(gate, trace)

    # One rising transition on confirmation, none after: the confirmed signal does not oscillate.
    assert detected[4] is True
    assert all(detected[4:])
    assert _transitions(detected) == 1
    assert _transitions(_naive_detect(trace)) > 10


def test_releases_only_below_hysteresis_level() -> None:
    """The confirmed signal clears only once the residual drops below hysteresis_ratio x thr."""
    gate = _gate(confirm_samples=5, hysteresis_ratio=0.7)
    over = _THRESHOLD * 1.2
    in_band = _THRESHOLD * 0.8
    below_release = _THRESHOLD * 0.6
    detected = _run(gate, [over] * 5 + [in_band] * 5 + [below_release])

    assert detected[4] is True
    assert all(detected[4:10])  # held through the in-band stretch
    assert detected[-1] is False  # released once below 0.7 x thr


def test_disabled_joint_never_confirms() -> None:
    """A per-joint-disabled joint never confirms even under a sustained over-threshold residual."""
    config = ThresholdConfig(
        calibration=ThresholdCalibration.literature_default(),
        mode=ThresholdMode.STATIC,
        vel_coeff=(0.05,) * 7,
        acc_coeff=(0.0,) * 7,
        use_accel_term=False,
        confirm_samples=5,
        hysteresis_ratio=0.7,
        per_joint_enable=(False,) + (True,) * 6,
    )
    gate = ConfirmHysteresisGate(config)
    thresholds = tuple(_THR0)
    detected = [
        gate.update(_residual_row(_THRESHOLD * 3.0), thresholds).detected for _ in range(20)
    ]
    assert not any(detected)


def test_reset_re_arms_the_gate() -> None:
    """`reset()` clears a confirmed state so the gate can be re-armed."""
    gate = _gate(confirm_samples=5)
    _run(gate, [_THRESHOLD * 1.5] * 5)
    assert gate.detected is True
    gate.reset()
    assert gate.detected is False
    assert gate.confirmed == (False,) * 7
