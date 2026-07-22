"""Mandatory asset-provenance metadata for every safety parameter (FR-SAF-067).

A safety parameter is unloadable without a complete
`{source_repo, commit_sha, path, robot_version, identified_on}` stamp. The point is not
documentation: `follower.yaml` (the v1 seed) predates the first v2.0 asset by ten months and
was never edited after its import, so nothing in the value itself marks it as v1. Provenance
is the only thing that does, and the strict version gate in `asset.py` reads `robot_version`
from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.dynamics.constants import PROVENANCE_FIELDS, ROBOT_VERSION_V2
from backend.dynamics.errors import DynamicsConversionError


@dataclass(frozen=True)
class Provenance:
    """The origin stamp a safety parameter must carry to be loadable.

    Attributes:
        source_repo: The repository the asset came from.
        commit_sha: The exact commit the asset was read at.
        path: The path within the source repository.
        robot_version: The robot generation the asset describes ("1.0" or "2.0"); the strict
            load gate refuses anything other than "2.0".
        identified_on: The date the parameter was identified or captured (ISO-8601).
    """

    source_repo: str
    commit_sha: str
    path: str
    robot_version: str
    identified_on: str

    def __post_init__(self) -> None:
        """Refuse a stamp with any blank field.

        Raises:
            DynamicsConversionError: If any required field is empty or whitespace, which is
                the unloadable-safety-parameter refusal of FR-SAF-067.
        """
        for field_name in PROVENANCE_FIELDS:
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise DynamicsConversionError(
                    f"provenance field {field_name!r} is required and must be a non-empty "
                    "string; a safety parameter without complete provenance is unloadable "
                    "(FR-SAF-067)"
                )

    @classmethod
    def from_mapping(cls, data: Any, where: str) -> Provenance:
        """Build provenance from a parsed mapping, refusing unknown or missing fields.

        Args:
            data: A parsed provenance mapping.
            where: The asset field the mapping sits under, for error messages.

        Returns:
            (Provenance) The validated stamp.

        Raises:
            DynamicsConversionError: On a non-mapping, unknown fields, or missing fields.
        """
        if not isinstance(data, dict):
            raise DynamicsConversionError(
                f"{where} provenance must be a mapping, got {type(data).__name__}; a safety "
                "parameter without provenance is unloadable (FR-SAF-067)"
            )
        known = set(PROVENANCE_FIELDS)
        unknown = set(data) - known
        if unknown:
            raise DynamicsConversionError(
                f"unknown provenance field(s) in {where}: {sorted(unknown)}"
            )
        missing = known - set(data)
        if missing:
            raise DynamicsConversionError(
                f"{where} provenance missing required field(s): {sorted(missing)} (FR-SAF-067)"
            )
        return cls(**{key: data[key] for key in PROVENANCE_FIELDS})

    def is_v2(self) -> bool:
        """Return whether this stamp declares the v2.0 robot generation."""
        return self.robot_version == ROBOT_VERSION_V2

    def to_dict(self) -> dict[str, str]:
        """Return the JSON-ready mapping for this stamp."""
        return {field_name: getattr(self, field_name) for field_name in PROVENANCE_FIELDS}
