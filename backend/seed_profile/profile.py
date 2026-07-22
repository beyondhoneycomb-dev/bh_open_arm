"""The read-only v1 seed profile (FR-SAF-031).

`SeedProfile` is the frozen v1 origin the v2 asset is promoted from. Read-only here is enforced
at three levels so no accidental mutation slips through: the dataclass is frozen (its fields
cannot be rebound), the payload is exposed as a `MappingProxyType` (its top-level keys cannot be
assigned), and every accessor that hands out nested structure returns a deep copy (mutating the
returned value cannot reach back into the seed). A seed that is not `robot_version "1.0"` is a
category error and is refused at construction — the seed is the v1 reference by definition.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from backend.dynamics.provenance import Provenance
from backend.seed_profile.constants import SEED_POSE_FIELD, SEED_ROBOT_VERSION
from backend.seed_profile.errors import SeedProfileError

PROVENANCE_KEY = "provenance"


@dataclass(frozen=True)
class SeedProfile:
    """A v1 dynamics seed, immutable and provenance-stamped v1 (FR-SAF-031).

    Attributes:
        provenance: The v1 origin stamp (robot_version "1.0").
        payload: A read-only view of the seed body with `provenance` removed. Use the accessors
            rather than reading nested values off this view directly.
    """

    provenance: Provenance
    payload: Mapping[str, Any]

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> SeedProfile:
        """Build a seed profile from a parsed asset mapping, refusing a non-v1 stamp.

        Args:
            raw: A parsed seed asset; must carry a `provenance` mapping tagged robot_version
                "1.0" and a seed pose field.

        Returns:
            (SeedProfile) The immutable seed with a deep-copied, read-only payload.

        Raises:
            SeedProfileError: On a non-mapping, missing/invalid provenance, a non-v1 stamp, or a
                missing seed pose.
        """
        if not isinstance(raw, Mapping):
            raise SeedProfileError(f"seed asset must be a mapping, got {type(raw).__name__}")
        if PROVENANCE_KEY not in raw:
            raise SeedProfileError(
                "seed asset carries no provenance; a seed without a recorded v1 origin cannot be "
                "isolated from the v2 runtime (FR-SAF-067)"
            )
        provenance = Provenance.from_mapping(raw[PROVENANCE_KEY], "seed")
        if provenance.robot_version != SEED_ROBOT_VERSION:
            raise SeedProfileError(
                f"seed profile must be robot_version {SEED_ROBOT_VERSION!r}, got "
                f"{provenance.robot_version!r}: the seed is the v1 origin by definition, and a "
                "v2-stamped 'seed' would defeat the isolation it exists to provide (FR-SAF-031)"
            )
        body = {key: copy.deepcopy(value) for key, value in raw.items() if key != PROVENANCE_KEY}
        if SEED_POSE_FIELD not in body:
            raise SeedProfileError(
                f"seed asset has no {SEED_POSE_FIELD!r} field; the seed pose is the quantity the "
                "v1->v2 promotion diff is measured on (FR-SAF-031)"
            )
        return cls(provenance=provenance, payload=MappingProxyType(body))

    def seed_pose(self) -> tuple[float, ...]:
        """Return the v1 seed pose (radians, v1 convention) as an independent tuple."""
        return tuple(float(value) for value in self.payload[SEED_POSE_FIELD])

    def as_v1_mapping(self) -> dict[str, Any]:
        """Return a deep-copied full asset mapping, provenance included, still v1-stamped.

        This is the form fed to the runtime gate to *prove* the seed is refused there: it carries
        the v1 stamp, so `load_into_v2_runtime` rejects it as contamination. It is never a load
        path — the seed has no v2 stamp and cannot acquire one except through promotion.

        Returns:
            (dict[str, Any]) The seed as a mutable copy; mutating it cannot reach the seed.
        """
        mapping = copy.deepcopy(dict(self.payload))
        mapping[PROVENANCE_KEY] = self.provenance.to_dict()
        return mapping
