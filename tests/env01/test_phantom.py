"""WP-ENV-01 acceptance ④ — the phantom/semver spec rejection."""

from __future__ import annotations

from deps.phantom import REASON_PHANTOM, REASON_SEMVER_PIN, is_phantom_version, reject_spec


def test_phantom_0_6_1_is_rejected_as_phantom() -> None:
    rejection = reject_spec("lerobot==0.6.1")
    assert rejection is not None
    assert rejection.reason == REASON_PHANTOM
    assert rejection.version == "0.6.1"


def test_resolved_0_6_0_semver_pin_is_still_rejected() -> None:
    rejection = reject_spec("lerobot==0.6.0")
    assert rejection is not None
    assert rejection.reason == REASON_SEMVER_PIN


def test_extras_and_operators_are_rejected() -> None:
    assert reject_spec("lerobot[dataset]>=0.6") is not None
    assert reject_spec("lerobot ~= 0.6.0") is not None


def test_sha_checkout_form_is_allowed() -> None:
    sha = "lerobot @ git+https://github.com/huggingface/lerobot@30da8e687a6dfc617fcd94afc367ac7071c376ce"
    assert reject_spec(sha) is None


def test_unrelated_dependency_is_not_touched() -> None:
    assert reject_spec("pyyaml==6.0") is None


def test_is_phantom_version() -> None:
    assert is_phantom_version("0.6.1")
    assert not is_phantom_version("0.6.0")
