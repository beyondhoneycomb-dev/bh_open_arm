"""The synthetic single-WS harness reaches the regime the acceptance items need.

Before any judge means anything the run must actually saturate the link and must
actually protect the control classes while shedding the camera. These are the
preconditions every other test rests on, checked once here.
"""

from __future__ import annotations

from backend.loadtest import LoadProfile, LoadRun
from contracts.ws.schema import WsFrameType


def test_profile_saturates_the_link(max_load_profile: LoadProfile) -> None:
    assert max_load_profile.is_saturating()
    assert (
        max_load_profile.camera_preview_bytes_per_sec()
        > max_load_profile.link_capacity_bytes_per_sec
    )


def test_camera_is_shed_and_control_is_not(saturated_run: LoadRun) -> None:
    camera = saturated_run.result(WsFrameType.CAMERA)
    assert camera.dropped > 0, "camera must be shed for the load test to prove anything"

    for frame_type in (WsFrameType.TELEMETRY, WsFrameType.COMMAND, WsFrameType.LEASE_RENEW):
        result = saturated_run.result(frame_type)
        assert result.dropped == 0, f"{frame_type.value} was dropped — control must be protected"
        assert result.delivered > 0, f"{frame_type.value} delivered nothing to measure"


def test_peak_buffer_crosses_the_backpressure_threshold(saturated_run: LoadRun) -> None:
    # The camera shed only happens once bufferedAmount is over the CTR-WS threshold,
    # so a run that shed camera frames must have peaked above it.
    from contracts.ws.schema import BUFFERED_AMOUNT_THRESHOLD_BYTES

    assert saturated_run.peak_buffered_bytes > BUFFERED_AMOUNT_THRESHOLD_BYTES
