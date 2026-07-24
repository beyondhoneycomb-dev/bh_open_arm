"""CG-4A-07a — RTC `max_guidance_weight <= 0` is rejected at the input stage.

The load-bearing distinction is *where* the rejection happens: our `InferenceParamError`
must fire before LeRobot's `configuration_rtc.py:38-48` `ValueError` is ever reached.
The tests prove both halves — our validator raises the typed input-stage error, and the
downstream LeRobot point genuinely exists and is a *different* exception — so the two are
ordered enforcement points, not one duplicated.
"""

from __future__ import annotations

import pytest

from backend.inference.adapter import (
    InferenceParamError,
    InferenceParamReason,
    RtcParams,
    build_rtc_config,
    validate_rtc_params,
)


def test_nonpositive_guidance_weight_rejected_at_input_stage() -> None:
    """A non-positive `max_guidance_weight` raises our typed input-stage error."""
    for weight in (0.0, -1.0, -10.0):
        with pytest.raises(InferenceParamError) as excinfo:
            validate_rtc_params(RtcParams(max_guidance_weight=weight))
        assert excinfo.value.reason is InferenceParamReason.RTC_GUIDANCE_WEIGHT_NONPOSITIVE


def test_build_rtc_config_validates_before_lerobot() -> None:
    """`build_rtc_config` rejects the bad weight before constructing LeRobot's RTCConfig."""
    with pytest.raises(InferenceParamError) as excinfo:
        build_rtc_config(RtcParams(max_guidance_weight=0.0))
    assert excinfo.value.reason is InferenceParamReason.RTC_GUIDANCE_WEIGHT_NONPOSITIVE


def test_lerobot_downstream_point_is_a_distinct_valueerror() -> None:
    """The LeRobot ValueError our check front-runs exists and is not an InferenceParamError.

    Confirms CG-4A-07a's "before ...:38-48" is meaningful: there is a genuine second
    enforcement point, and it is a plain `ValueError`, so a test asserting our
    `InferenceParamError` proves the rejection came from the earlier input stage.
    """
    from lerobot.policies.rtc.configuration_rtc import RTCConfig

    with pytest.raises(ValueError) as excinfo:
        RTCConfig(max_guidance_weight=0.0)
    assert not isinstance(excinfo.value, InferenceParamError)


def test_good_rtc_params_build_a_real_lerobot_config() -> None:
    """Validated params flow into a real LeRobot RTCConfig with the frozen defaults."""
    config = build_rtc_config(RtcParams())
    assert config.max_guidance_weight == 10.0
    assert config.execution_horizon == 10
    assert config.prefix_attention_schedule.value == "LINEAR"


def test_other_rtc_reasons_are_distinct() -> None:
    """Unknown schedule, non-positive horizon, and negative threshold each get their reason."""
    cases = [
        (RtcParams(prefix_attention_schedule="SIGMOID"), InferenceParamReason.RTC_SCHEDULE_UNKNOWN),
        (RtcParams(execution_horizon=0), InferenceParamReason.RTC_EXECUTION_HORIZON_NONPOSITIVE),
        (RtcParams(queue_threshold=-1), InferenceParamReason.RTC_QUEUE_THRESHOLD_NEGATIVE),
    ]
    for params, reason in cases:
        with pytest.raises(InferenceParamError) as excinfo:
            validate_rtc_params(params)
        assert excinfo.value.reason is reason
