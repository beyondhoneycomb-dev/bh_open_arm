"""The read-only store for the v1 seed profile (FR-SAF-031, `02b` WP-2B-10 acceptance ①).

The store loads the shipped seed asset and refuses every write. The refusal is the acceptance
criterion: a seed rewritten in place would silently redefine the v1 origin the promotion diff is
measured against, so `save` never touches disk — it raises. The only forward path is an explicit
v1->v2 promotion (`promotion.py`) that produces a *new* v2 asset and leaves the seed untouched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from backend.seed_profile.errors import SeedWriteRefusedError
from backend.seed_profile.profile import SeedProfile

# The vendored illustrative v1 seed. Its values stand in for the real `openarm_teleop`
# `config/follower.yaml` (not vendored into this repo); its provenance carries the sentinel v1
# commit the WP-2B-01 fixtures use. The isolation machinery is what this package delivers — the
# numbers are placeholders the real seed replaces, and the sentinel commit_sha says so.
DEFAULT_ASSET_PATH = Path(__file__).parent / "assets" / "seed_follower_v1.yaml"


class SeedProfileStore:
    """A read-only gateway to the v1 seed asset.

    Ownership: the store never writes. It is the single place the seed is read from disk, so the
    read-only guarantee has exactly one enforcement point.
    """

    def __init__(self, asset_path: Path) -> None:
        """Bind the store to a seed asset path.

        Args:
            asset_path: The seed asset YAML this store reads (and refuses to overwrite).
        """
        self._asset_path = asset_path

    @classmethod
    def default(cls) -> SeedProfileStore:
        """Return the store bound to the vendored default seed asset."""
        return cls(DEFAULT_ASSET_PATH)

    @property
    def asset_path(self) -> Path:
        """Return the seed asset path this store reads."""
        return self._asset_path

    def load(self) -> SeedProfile:
        """Load the seed profile from disk, provenance-gated to v1.

        Returns:
            (SeedProfile) The immutable v1 seed.

        Raises:
            SeedProfileError: If the asset is missing its v1 provenance or seed pose.
            FileNotFoundError: If the asset file does not exist.
        """
        raw: Any = yaml.safe_load(self._asset_path.read_text(encoding="utf-8"))
        return SeedProfile.from_mapping(raw)

    def save(self, profile: SeedProfile) -> None:
        """Refuse to write the seed profile (FR-SAF-031) — the seed is read-only.

        Args:
            profile: The profile a caller attempted to persist.

        Raises:
            SeedWriteRefusedError: Always. The seed is the frozen v1 origin; the forward path is
                promotion to a new v2 asset, never an in-place rewrite.
        """
        raise SeedWriteRefusedError(
            f"the seed profile at {self._asset_path} is read-only and cannot be written "
            f"(robot_version {profile.provenance.robot_version!r}); promote it to a new v2 asset "
            "instead of rewriting the v1 origin (FR-SAF-031)"
        )
