"""The single v2-runtime load gate — the seed-contamination guard (FR-SAF-067).

`load_into_v2_runtime` is the one place an asset enters the v2 runtime. It refuses any asset not
stamped `robot_version "2.0"` — the seed, or anything else of the v1 generation — as
contamination rather than loading it silently. That refusal is the FAIL_BLOCKING condition of
`02b` WP-2B-10: a v1 value silently loaded into the v2 runtime is a v1 model masquerading as a v2
one.

The only mapping that passes is one carrying a genuine v2 stamp, which in this package means a
`PromotedProfile.as_v2_mapping()` — the output of an explicit, approved promotion.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from backend.dynamics.asset import LoadedDynamicsAsset, load_safety_params
from backend.seed_profile.errors import SeedContaminationError


def load_into_v2_runtime(asset: Mapping[str, Any]) -> LoadedDynamicsAsset:
    """Load an asset into the v2 runtime, refusing any non-v2 stamp as contamination.

    The provenance is validated first (a missing or malformed stamp raises through WP-2B-01's
    loader), then the version decision is made explicitly: only a robot_version "2.0" asset is
    admitted, so there is no path by which a v1 value loads silently.

    Args:
        asset: A full asset mapping (payload plus a `provenance` stamp).

    Returns:
        (LoadedDynamicsAsset) The loaded asset, guaranteed v2.

    Raises:
        SeedContaminationError: If the asset is not stamped robot_version "2.0" — a v1 value
            reaching the v2 runtime (FAIL_BLOCKING, FR-SAF-067).
        DynamicsConversionError: If the asset carries no provenance or a malformed stamp.
    """
    loaded = load_safety_params(dict(asset), strict=False)
    if not loaded.provenance.is_v2():
        raise SeedContaminationError(
            f"asset is robot_version {loaded.provenance.robot_version!r}, not '2.0': a v1 value "
            "reaching the v2 runtime is asset contamination and is refused (FAIL_BLOCKING, "
            "FR-SAF-067)"
        )
    return loaded
