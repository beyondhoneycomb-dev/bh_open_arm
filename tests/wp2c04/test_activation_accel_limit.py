"""Acceptance ③ — arming while acceleration limits are off is refused or warned (FR-SAF-014).

The v2.0 `joint_limits.yaml` reality is limits off / ceilings zero, so on stock assets the
precondition fails. The default REFUSE policy raises (the WP-2C-04 negative branch is
RETRY_WITH_VARIANT: activate the limits first); the WARN policy is the "or warn" alternative the
requirement permits and records the reason instead of raising.
"""

from __future__ import annotations

import pytest

from backend.threshold import (
    AccelerationLimitError,
    AccelLimitPolicy,
    AccelLimitStatus,
    ThresholdConfigError,
    check_acceleration_limit_precondition,
)

_ALL_ENABLED = (True,) * 7


def test_v2_default_is_inactive_on_every_joint() -> None:
    """The v2.0 default (limits off, ceilings zero) is inactive on all seven joints."""
    assert AccelLimitStatus.v2_default().active() == (False,) * 7


def test_refuse_policy_raises_when_limits_off() -> None:
    """Under REFUSE (the default), arming with acceleration limits off raises."""
    with pytest.raises(AccelerationLimitError, match="RETRY_WITH_VARIANT"):
        check_acceleration_limit_precondition(AccelLimitStatus.v2_default(), _ALL_ENABLED)


def test_warn_policy_allows_with_recorded_warning() -> None:
    """Under WARN, arming is allowed but every offending joint is named in a recorded warning."""
    decision = check_acceleration_limit_precondition(
        AccelLimitStatus.v2_default(), _ALL_ENABLED, policy=AccelLimitPolicy.WARN
    )
    assert decision.allowed is True
    assert decision.disabled_joints == tuple(range(7))
    assert len(decision.warnings) == 1
    assert "FR-SAF-014" in decision.warnings[0]


def test_active_limits_allow_arming() -> None:
    """With every joint's acceleration limit active, arming is allowed with no warning."""
    decision = check_acceleration_limit_precondition(
        AccelLimitStatus.all_active(10.0), _ALL_ENABLED
    )
    assert decision.allowed is True
    assert decision.disabled_joints == ()
    assert decision.warnings == ()


def test_flag_set_but_zero_ceiling_is_inactive() -> None:
    """A joint with the flag set but a zero ceiling is inactive — both conditions are required."""
    status = AccelLimitStatus(
        has_acceleration_limits=(True,) * 7,
        max_acceleration=(0.0,) * 7,
    )
    assert status.active() == (False,) * 7
    with pytest.raises(AccelerationLimitError):
        check_acceleration_limit_precondition(status, _ALL_ENABLED)


def test_disabled_joint_does_not_block_arming() -> None:
    """A detection-disabled joint contributes no residual, so its missing limit is irrelevant."""
    # Only joint1 lacks an acceleration limit, and joint1 detection is disabled.
    status = AccelLimitStatus(
        has_acceleration_limits=(False,) + (True,) * 6,
        max_acceleration=(0.0,) + (10.0,) * 6,
    )
    per_joint_enable = (False,) + (True,) * 6
    decision = check_acceleration_limit_precondition(status, per_joint_enable)
    assert decision.allowed is True
    assert decision.disabled_joints == ()


def test_one_enabled_unlimited_joint_still_blocks() -> None:
    """A single enabled joint with no acceleration limit refuses arming, and is named."""
    status = AccelLimitStatus(
        has_acceleration_limits=(True,) * 6 + (False,),
        max_acceleration=(10.0,) * 6 + (0.0,),
    )
    with pytest.raises(AccelerationLimitError, match="joint7"):
        check_acceleration_limit_precondition(status, _ALL_ENABLED)


def test_all_active_rejects_non_positive_ceiling() -> None:
    """`all_active` refuses a non-positive ceiling — an inactive limit dressed as active."""
    with pytest.raises(ThresholdConfigError, match="positive"):
        AccelLimitStatus.all_active(0.0)
