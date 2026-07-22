"""Acceptance ② (CG-2C-09b) — payload change / temperature drift shrinks the margin → alert.

The monitor is baselined on a healthy model, then two drift sources are injected in turn:
a payload change (a standing residual offset the model does not know) and a thermal drift
(rising temperature dragging the friction residual up). Each pushes the residual envelope
toward the collision threshold, the margin falls below its baseline, and a "model needs
re-identification" alert fires. A steady healthy stream raises nothing, so the alert is a
response to drift, not a constant. The gripper joint is not tracked (WP-2C-11).
"""

from __future__ import annotations

from backend.event_ring import EventChannel, ModelErrorMonitor
from backend.event_ring.constants import ARM_JOINT_COUNT, GRIPPER_JOINT_INDEX
from tests.wp2c09.conftest import DT_SEC, uniform_sample

# A representative per-joint collision threshold (WP-2C-03 output stands in here; the real
# calibrated value is hardware-deferred). The monitor never invents this — it is required.
_THRESHOLD_NM = 4.0
_WINDOW = 50
_TOLERANCE_NM = 0.2
_HEALTHY_RESIDUAL_NM = 0.1
_PAYLOAD_RESIDUAL_NM = 1.5


def _baselined_monitor() -> ModelErrorMonitor:
    """A monitor over the arm joints, warmed on a healthy residual and baselined."""
    monitor = ModelErrorMonitor.for_arm_joints(
        thresholds_nm=dict.fromkeys(range(ARM_JOINT_COUNT), _THRESHOLD_NM),
        window_len=_WINDOW,
        margin_decrease_tolerance_nm=_TOLERANCE_NM,
    )
    for tick in range(_WINDOW + 5):
        monitor.update(
            uniform_sample(tick * DT_SEC, residual_nm=_HEALTHY_RESIDUAL_NM).channel(EventChannel.R)
        )
    monitor.freeze_baseline()
    return monitor


def test_healthy_stream_raises_no_alert() -> None:
    """A steady, well-modelled residual keeps the margin at baseline — no alert (②)."""
    monitor = _baselined_monitor()

    report = monitor.assess()
    assert not report.reidentify_needed
    assert report.alert is None


def test_payload_change_shrinks_margin_and_alerts() -> None:
    """An unmodelled payload lifts the residual, the margin falls, and the alert fires (②)."""
    monitor = _baselined_monitor()
    baseline_margin = monitor.assess().margins[0].margin_nm

    for tick in range(_WINDOW + 5, 2 * _WINDOW + 10):
        monitor.update(
            uniform_sample(tick * DT_SEC, residual_nm=_PAYLOAD_RESIDUAL_NM).channel(EventChannel.R)
        )

    report = monitor.assess()
    assert report.reidentify_needed
    assert report.alert is not None
    assert report.margins[0].margin_nm < baseline_margin - _TOLERANCE_NM
    assert "re-identification" in report.alert.detail


def test_temperature_drift_shrinks_margin_and_alerts() -> None:
    """Thermal drift (residual rising with temperature) shrinks the margin and alerts (②)."""
    monitor = _baselined_monitor()

    # Residual and temperature climb together, as friction drift does as the motors heat.
    for step in range(_WINDOW + 5):
        residual = _HEALTHY_RESIDUAL_NM + 0.02 * step
        temp = 30.0 + 1.0 * step
        sample = uniform_sample(
            (step + _WINDOW + 5) * DT_SEC,
            residual_nm=residual,
            t_mos_degc=temp,
            t_rotor_degc=temp - 5.0,
        )
        monitor.update(
            sample.channel(EventChannel.R),
            t_mos_degc=sample.channel(EventChannel.T_MOS),
            t_rotor_degc=sample.channel(EventChannel.T_ROTOR),
        )

    report = monitor.assess()
    assert report.reidentify_needed
    assert report.alert is not None
    # The thermal context travels with the alert so an operator can attribute the drift.
    assert report.alert.t_mos_max_degc is not None
    assert report.alert.t_mos_max_degc > 30.0


def test_gripper_joint_is_not_tracked() -> None:
    """The monitor tracks arm joints only; the gripper's residual is excluded (WP-2C-11) (②)."""
    monitor = _baselined_monitor()

    report = monitor.assess()
    tracked = {margin.joint_index for margin in report.margins}
    assert GRIPPER_JOINT_INDEX not in tracked
    assert tracked == set(range(ARM_JOINT_COUNT))
