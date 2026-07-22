"""CG-2B-10b (second half) — v2 promotion cannot activate without explicit approval (FR-SAF-067).

Activation is bound by digest to the exact report an operator reviewed: a blank, mismatched, or
absent approval cannot activate a promotion, and an approval of one report cannot activate a
different one.
"""

from __future__ import annotations

import pytest

from backend.dynamics.converter import JointFrameConverter
from backend.dynamics.provenance import Provenance
from backend.seed_profile.errors import PromotionNotApprovedError
from backend.seed_profile.profile import SeedProfile
from backend.seed_profile.promotion import (
    Approval,
    build_promotion_report,
    promote,
)
from backend.seed_profile.runtime import load_into_v2_runtime
from tests.wp2b10.conftest import make_v2_provenance

OPERATOR = "operator@bh"
APPROVED_ON = "2026-07-22"


def _approval_for_digest(digest: str) -> Approval:
    return Approval(operator=OPERATOR, acknowledged_report_digest=digest, approved_on=APPROVED_ON)


def test_promote_without_matching_approval_is_refused(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """An approval whose digest does not match the report cannot activate it."""
    report = build_promotion_report(seed, converter, target_provenance)
    wrong = _approval_for_digest("deadbeefdeadbeef")
    with pytest.raises(PromotionNotApprovedError, match="does not acknowledge"):
        promote(report, wrong)


def test_blank_approval_is_refused_at_construction() -> None:
    """A blank operator or digest cannot be an approval at all."""
    with pytest.raises(PromotionNotApprovedError, match="required"):
        Approval(operator="", acknowledged_report_digest="abc", approved_on=APPROVED_ON)
    with pytest.raises(PromotionNotApprovedError, match="required"):
        Approval(operator=OPERATOR, acknowledged_report_digest="   ", approved_on=APPROVED_ON)


def test_matching_approval_activates(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """An approval bound to the report's digest activates a v2 asset."""
    report = build_promotion_report(seed, converter, target_provenance)
    promoted = promote(report, _approval_for_digest(report.digest))
    assert promoted.activated is True
    assert promoted.asset.provenance.is_v2()
    assert promoted.report_digest == report.digest


def test_approval_is_bound_to_its_own_report(
    seed: SeedProfile, converter: JointFrameConverter
) -> None:
    """An approval of report A cannot activate report B — the binding is per-report."""
    report_a = build_promotion_report(seed, converter, make_v2_provenance())
    report_b = build_promotion_report(
        seed, converter, make_v2_provenance(identified_on="2026-08-01")
    )
    approval_a = _approval_for_digest(report_a.digest)
    assert report_a.digest != report_b.digest
    with pytest.raises(PromotionNotApprovedError):
        promote(report_b, approval_a)


def test_promoted_asset_is_the_only_thing_that_passes_the_runtime_gate(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The approved v2 asset loads into the v2 runtime; the same path the raw seed is refused on."""
    report = build_promotion_report(seed, converter, target_provenance)
    promoted = promote(report, _approval_for_digest(report.digest))
    loaded = load_into_v2_runtime(promoted.as_v2_mapping())
    assert loaded.provenance.is_v2()


def test_no_activated_asset_exists_before_approval(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The report is not itself an activated asset; only `promote` yields one."""
    report = build_promotion_report(seed, converter, target_provenance)
    assert report.activated is False
    assert not hasattr(report, "asset")


def test_approval_preserved_on_promoted_profile(
    seed: SeedProfile, converter: JointFrameConverter, target_provenance: Provenance
) -> None:
    """The activated profile records who approved it — the audit trail of the activation."""
    report = build_promotion_report(seed, converter, target_provenance)
    approval = _approval_for_digest(report.digest)
    promoted = promote(report, approval)
    assert promoted.approval.operator == OPERATOR
    assert promoted.approval.acknowledged_report_digest == report.digest
