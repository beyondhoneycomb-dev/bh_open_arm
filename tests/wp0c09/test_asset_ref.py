"""Acceptance ⑮ — the dry-run references the fixed asset and rejects an unfixed one."""

from __future__ import annotations

import pytest

from sim.dryrun.asset_ref import (
    UnfixedAssetError,
    content_digest,
    fixed_asset_digest,
    fixed_bimanual_asset,
    verify_fixed_asset,
)
from sim.dryrun.canon import ClampCanon, PositionCanon, VelocityCanon
from sim.dryrun.runner import DryRunRunner


def _unfixed_bimanual_xml() -> str:
    """Return the bimanual asset with J7 reverted to the ``motor_DM3507`` typo."""
    lines = fixed_bimanual_asset().read_text(encoding="utf-8").splitlines(keepends=True)
    reverted = [
        line.replace('class="motor_DM4310"', 'class="motor_DM3507"') if 'joint7"' in line else line
        for line in lines
    ]
    return "".join(reverted)


def test_fixed_asset_passes_and_digest_is_stable() -> None:
    """The fixed asset passes the WP-0C-03 invariant and its digest is its content."""
    digest = verify_fixed_asset()
    assert digest == fixed_asset_digest()
    assert digest == content_digest(fixed_bimanual_asset())


def test_unfixed_asset_is_rejected() -> None:
    """⑮ An unfixed J7 fails the invariant → the dry-run refuses to run over it."""
    with pytest.raises(UnfixedAssetError):
        verify_fixed_asset(_unfixed_bimanual_xml())


def test_runner_binds_to_the_fixed_asset_digest() -> None:
    """⑮ A constructed runner references the fixed-asset digest in its verdict."""
    canon = ClampCanon(PositionCanon.MJCF, VelocityCanon.OPENARM_CONTROL)
    runner = DryRunRunner(canon)
    assert runner.asset_digest == fixed_asset_digest()
