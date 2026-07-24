"""The bridge from validated adapter params to LeRobot's own config objects.

This is where the "input-stage" ordering (CG-4A-07a) becomes real rather than
rhetorical: `build_rtc_config` runs `validate_rtc_params` and only *then* constructs
LeRobot's `RTCConfig`. A non-positive `max_guidance_weight` therefore raises our
`InferenceParamError` here, before `configuration_rtc.py:38-48`'s `ValueError` is ever
reached — the two enforcement points are ordered, not duplicated.

LeRobot imports (which pull torch and the processor stack) are lazy and local to the
build functions, so importing this module costs nothing until a config is actually
built, and the pure validators in `params` stay usable in a torch-free context.
"""

from __future__ import annotations

from typing import Any

from backend.inference.adapter.params import (
    RtcParams,
    validate_rtc_params,
)


def build_rtc_config(params: RtcParams) -> Any:
    """Validate RTC params at the input stage, then build LeRobot's `RTCConfig`.

    The validation runs first (CG-4A-07a): a non-positive `max_guidance_weight` is
    rejected here as an `InferenceParamError` before LeRobot's `RTCConfig.__post_init__`
    `ValueError` could fire. The returned object is LeRobot's real config, so the
    validated params genuinely flow into the inference stack.

    Args:
        params: The RTC params to validate and translate.

    Returns:
        (RTCConfig) LeRobot's real `RTCConfig`, built from the validated params.

    Raises:
        InferenceParamError: If the params fail input-stage validation.
    """
    validate_rtc_params(params)
    from lerobot.configs import RTCAttentionSchedule
    from lerobot.policies.rtc.configuration_rtc import RTCConfig

    return RTCConfig(
        prefix_attention_schedule=RTCAttentionSchedule[params.prefix_attention_schedule],
        max_guidance_weight=params.max_guidance_weight,
        execution_horizon=params.execution_horizon,
    )
