"""Which friction the runtime is actually using, and where it came from (NORM-012).

The residual observer subtracts a friction estimate to produce `r`, so a friction table that
does not describe this arm leaves a standing bias in the residual and the collision thresholds
calibrated against it are off by that bias. The Wave -1 ruling NORM-012 adopted the v1 seed as
the shipping default — it is the only measured friction that exists — and the cost of that
choice is exactly this bias, until a real identification run replaces it.

That makes one question operationally load-bearing: *is the arm running the v1 seed right now, or
an identified v2 fit?* `FrictionParams` carries only numbers and `FrictionFeedforward` stores only
parameters, so neither can answer it. This module pairs the parameters with the `Provenance` stamp
that already travels with a written table (`writer.build_friction_document`) so the question has
an answer at runtime rather than being reconstructed from which file someone remembers loading.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backend.dynamics.provenance import Provenance
from backend.friction.constants import ARM_JOINT_COUNT
from backend.friction.errors import FrictionIdentificationError
from backend.friction.model import FrictionParams
from backend.friction.seed import V1_SEED_FRICTION, V1_SEED_PROVENANCE

# Document keys as `writer.build_friction_document` emits them. The joint terms are written in
# the YAML's own capitalisation (`Fo`/`Fv`/`Fc`) while `FrictionParams.from_stored_k` takes
# `f_o`/`f_v`/`f_c`, so the mapping between the two spellings lives here, once.
_PROVENANCE_KEY = "provenance"
_JOINTS_KEY = "joints"
_STORED_TO_PARAM = {"Fo": "f_o", "Fv": "f_v", "Fc": "f_c", "k": "k"}


@dataclass(frozen=True)
class ActiveFrictionProfile:
    """The friction parameters in use, with the stamp saying which robot they describe.

    Attributes:
        params: Per-joint friction parameters, joint1..joint7 order.
        provenance: The asset stamp the parameters arrived with.
    """

    params: tuple[FrictionParams, ...]
    provenance: Provenance

    def __post_init__(self) -> None:
        """Refuse a parameter set of the wrong width."""
        if len(self.params) != ARM_JOINT_COUNT:
            raise FrictionIdentificationError(
                f"friction params must have {ARM_JOINT_COUNT} entries, got {len(self.params)}"
            )

    @property
    def is_reidentified(self) -> bool:
        """Whether these parameters came from a v2 identification rather than the v1 seed.

        False means the residual carries the v1-to-v2 friction mismatch as a standing bias, which
        is the first thing to suspect when collision detection fires without contact or misses it.
        """
        return self.provenance.is_v2()

    def as_record(self) -> dict[str, Any]:
        """Render the profile for an operator query or a diagnostic bundle."""
        return {
            "robot_version": self.provenance.robot_version,
            "is_reidentified": self.is_reidentified,
            "provenance": self.provenance.to_dict(),
        }


def v1_seed_profile() -> ActiveFrictionProfile:
    """Return the shipping default: the v1 seed, stamped as v1."""
    return ActiveFrictionProfile(params=V1_SEED_FRICTION, provenance=V1_SEED_PROVENANCE)


def load_profile(path: Path) -> ActiveFrictionProfile:
    """Read a written friction table back as an active profile.

    Args:
        path: A YAML table produced by `writer.build_friction_document`.

    Returns:
        (ActiveFrictionProfile) The parameters with the stamp the file carries.

    Raises:
        FrictionIdentificationError: If the document is not a mapping, carries no provenance, or
            holds a joint count other than `ARM_JOINT_COUNT`. A table whose stamp cannot be read
            is refused rather than defaulted to v2: a wrong "identified" answer here would hide
            the very bias this module exists to surface.
    """
    loaded: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise FrictionIdentificationError(f"{path} did not parse to a mapping")
    if _PROVENANCE_KEY not in loaded:
        raise FrictionIdentificationError(f"{path} carries no {_PROVENANCE_KEY} stamp")
    provenance = Provenance.from_mapping(loaded[_PROVENANCE_KEY], f"{path}:{_PROVENANCE_KEY}")

    joints = loaded.get(_JOINTS_KEY)
    if not isinstance(joints, list) or len(joints) != ARM_JOINT_COUNT:
        raise FrictionIdentificationError(
            f"{path} must carry {ARM_JOINT_COUNT} {_JOINTS_KEY} entries"
        )
    try:
        params = tuple(
            FrictionParams.from_stored_k(
                **{arg: float(joint[stored]) for stored, arg in _STORED_TO_PARAM.items()}
            )
            for joint in joints
        )
    except (KeyError, TypeError, ValueError) as bad:
        raise FrictionIdentificationError(
            f"{path} has a malformed {_JOINTS_KEY} entry: {bad}"
        ) from bad
    return ActiveFrictionProfile(params=params, provenance=provenance)
