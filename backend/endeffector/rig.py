"""The end-effector build fitted to each arm, persisted and re-read every start.

Which tool is bolted on is a fact about the bench, not about the code, and it changes without
any file changing. So it is recorded next to the CAN channel binding and read back the same way:
a stored answer, validated on load, refused rather than defaulted when it does not parse.

The default is the spatula build. That is a deliberate asymmetry rather than a neutral choice —
defaulting to `GRIPPER` on a rig with no gripper fitted makes the arm poll motor `0x08`, and an
unanswered poll walks the controller toward `ERROR-PASSIVE`, degrading the seven joints that are
present. Defaulting to `FIXED_SPATULA` on a rig that *does* have a gripper costs a refused
gripper command and a clear message. One default breaks the arm quietly; the other stops and
says so.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.endeffector.profile import (
    EndEffector,
    EndEffectorError,
    EndEffectorProfile,
    spatula_build,
)

RIG_FILENAME = "end_effectors.json"
RIG_VERSION = 1

FIELD_VERSION = "version"
FIELD_ARMS = "arms"
FIELD_END_EFFECTOR = "end_effector"
FIELD_TOOL_MASS_KG = "tool_mass_kg"

SIDE_LEFT = "left"
SIDE_RIGHT = "right"
SIDES: tuple[str, ...] = (SIDE_LEFT, SIDE_RIGHT)


@dataclass(frozen=True)
class RigEndEffectors:
    """What each arm carries.

    Attributes:
        left: The left arm's build.
        right: The right arm's build.
    """

    left: EndEffectorProfile
    right: EndEffectorProfile

    def for_side(self, side: str) -> EndEffectorProfile:
        """Return one arm's profile.

        Args:
            side: `left` or `right`, the CTR-UNIT arm order.

        Raises:
            EndEffectorError: On any other name — a typo must not resolve to an arm.
        """
        if side == SIDE_LEFT:
            return self.left
        if side == SIDE_RIGHT:
            return self.right
        raise EndEffectorError(f"unknown side {side!r}; expected one of {SIDES}")

    @property
    def total_motor_count(self) -> int:
        """How many motors the whole rig has on its two buses."""
        return self.left.motor_count + self.right.motor_count


def default_rig() -> RigEndEffectors:
    """Both arms on the spatula build — the shape that cannot poll an absent motor."""
    return RigEndEffectors(left=spatula_build(), right=spatula_build())


def rig_path(directory: Path) -> Path:
    """Return the end-effector record path under a directory."""
    return directory / RIG_FILENAME


def save_rig(path: Path, rig: RigEndEffectors) -> None:
    """Write the record atomically — temp file, fsync, rename, fsync the directory.

    A torn write here leaves the rig unsure whether motor `0x08` exists, and the consequence of
    guessing wrong is a degraded CAN controller rather than a parse error.
    """
    body = json.dumps(
        {
            FIELD_VERSION: RIG_VERSION,
            FIELD_ARMS: {
                side: {
                    FIELD_END_EFFECTOR: rig.for_side(side).end_effector.value,
                    FIELD_TOOL_MASS_KG: rig.for_side(side).tool_mass_kg,
                }
                for side in SIDES
            },
        },
        indent=2,
        sort_keys=True,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    handle_fd, temp_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(body + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)  # noqa: PTH105 — atomic rename primitive
        _fsync_dir(path.parent)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise


def _fsync_dir(directory: Path) -> None:
    """Fsync a directory so a rename into it survives a crash."""
    fd = os.open(str(directory), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def load_rig(path: Path) -> RigEndEffectors:
    """Read and validate the stored end-effector record.

    Args:
        path: The record file.

    Returns:
        (RigEndEffectors) What each arm carries.

    Raises:
        EndEffectorError: On a malformed envelope, a missing side, an unknown build name, or a
            non-positive mass. Every one is a refusal: a record that cannot be read is a record
            that cannot say whether motor `0x08` is on the bus, and the safe answer to that is
            to stop, not to assume.
    """
    try:
        loaded: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as bad:
        raise EndEffectorError(f"{path} could not be read as JSON: {bad}") from bad
    if not isinstance(loaded, dict):
        raise EndEffectorError(f"{path} did not parse to an object")
    if loaded.get(FIELD_VERSION) != RIG_VERSION:
        raise EndEffectorError(
            f"{path} declares version {loaded.get(FIELD_VERSION)!r}, expected {RIG_VERSION}"
        )
    arms = loaded.get(FIELD_ARMS)
    if not isinstance(arms, dict):
        raise EndEffectorError(f"{path} carries no {FIELD_ARMS} object")

    profiles = {side: _profile_from(path, side, arms.get(side)) for side in SIDES}
    return RigEndEffectors(left=profiles[SIDE_LEFT], right=profiles[SIDE_RIGHT])


def _profile_from(path: Path, side: str, raw: Any) -> EndEffectorProfile:
    """Build one arm's profile from its stored object."""
    if not isinstance(raw, dict):
        raise EndEffectorError(f"{path} has no record for the {side} arm")
    name = raw.get(FIELD_END_EFFECTOR)
    try:
        end_effector = EndEffector(name)
    except ValueError as bad:
        known = ", ".join(member.value for member in EndEffector)
        raise EndEffectorError(
            f"{path}: {side} names an unknown end effector {name!r}; known are {known}"
        ) from bad
    mass = raw.get(FIELD_TOOL_MASS_KG)
    if mass is not None:
        if isinstance(mass, bool) or not isinstance(mass, int | float):
            raise EndEffectorError(f"{path}: {side} tool_mass_kg must be a number or null")
        if mass <= 0.0:
            raise EndEffectorError(
                f"{path}: {side} tool_mass_kg is {mass}; a fitted tool has positive mass, and "
                "an unweighed one is null rather than zero"
            )
        mass = float(mass)
    return EndEffectorProfile(end_effector=end_effector, tool_mass_kg=mass)
