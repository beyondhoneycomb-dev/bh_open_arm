"""Bind the dry-run to the WP-0C-03 fixed MJCF, and reject an unfixed one (⑮).

`02a` WP-0C-09 acceptance ⑮: the dry-run must reference the WP-0C-03 fixed MJCF
hash and reject running over an unfixed asset — a J7 ``motor_DM3507`` typo makes
the torque tMax twice wrong, which invalidates torque check ③ wholesale (`09` G6).
So "reference the hash" is not decoration: the dry-run pins which asset its
judgement is bound to, and refuses an asset that fails the WP-0C-03 invariant.

The reference is enforced two ways. ``verify_fixed_asset`` runs WP-0C-03's own
``audit`` (the invariant that *defines* "fixed": J7 resolves to DM4310, zero
``motor_DM3507`` references) and raises when it fails, so an unfixed asset cannot
be dry-run. It also returns the asset's content digest, which the verdict carries
as provenance, so the run names the exact asset bytes it validated against. The
audit is the semantic gate; the digest is the provenance the verdict records.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import sim.mjcf
from sim.mjcf.invariant import audit

# The J7-bearing asset whose correctness torque check ③ depends on. The cell scene
# attaches this bimanual model; its J7 class is what WP-0C-03 fixed.
_BIMANUAL_ASSET = Path(sim.mjcf.__file__).resolve().parent / "v2" / "openarm_bimanual.xml"


class UnfixedAssetError(RuntimeError):
    """Raised when a dry-run targets an asset failing the WP-0C-03 invariant.

    `02a` WP-0C-09 ⑮ / `09` G6: an unfixed J7 (``motor_DM3507``) invalidates torque
    check ③, so the dry-run must refuse to run over it.
    """


def fixed_bimanual_asset() -> Path:
    """Return the path to the J7-bearing bimanual asset the dry-run references."""
    return _BIMANUAL_ASSET


def content_digest(source: str | Path) -> str:
    """Return the SHA-256 digest of an asset's bytes.

    Args:
        source: A path to the asset, or its XML content as a string.

    Returns:
        (str) The hex SHA-256 digest of the content.
    """
    text = source if isinstance(source, str) and source.lstrip().startswith("<") else None
    data = text.encode("utf-8") if text is not None else Path(source).read_bytes()
    return hashlib.sha256(data).hexdigest()


def fixed_asset_digest() -> str:
    """Return the content digest of the WP-0C-03 fixed bimanual asset (⑮).

    Returns:
        (str) The hex SHA-256 digest the dry-run pins its judgement to.
    """
    return content_digest(_BIMANUAL_ASSET)


def verify_fixed_asset(source: str | Path | None = None) -> str:
    """Verify an asset passes the WP-0C-03 invariant, returning its digest.

    Args:
        source: The asset to verify (path or XML string); defaults to the fixed
            bimanual asset.

    Returns:
        (str) The verified asset's content digest, for the verdict's provenance.

    Raises:
        UnfixedAssetError: If the asset fails the WP-0C-03 invariant (e.g. a J7
            ``motor_DM3507`` typo), which would invalidate torque check ③.
    """
    target: str | Path = _BIMANUAL_ASSET if source is None else source
    report = audit(target)
    if not report.ok:
        raise UnfixedAssetError(
            "dry-run asset fails the WP-0C-03 invariant; refusing to run because an "
            f"unfixed J7 invalidates torque check ③ (09 G6): {report.failures}"
        )
    return content_digest(target)
