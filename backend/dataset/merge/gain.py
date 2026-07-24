"""Follower PD gain-profile tagging and merge-time verification (WP-3D-06, `FR-DAT-045`).

`FR-DAT-045`: the follower PD gain profile drives the following error
(`observation.state - action`), so episodes recorded under different gains carry
different error distributions and must not share a dataset. A dataset is tagged with
its gain profile, and a merge verifies the tags agree. `02b` §8.2 WP-3D-06 ② makes a
gain-tagless merge the FAIL_BLOCKING defect: an untagged source could silently mix
distributions, so a source with no tag is refused rather than merged.

The tag is the profile id *and* the `kp`/`kd` vectors, because the id alone is not the
distribution — two datasets both tagged `custom` with different vectors are different
distributions, and comparing only the label would let them merge (`03` §2.8: five real
profiles, `custom` among them). Equality is on the vectors within a float round-trip
tolerance, so it is the gains that must match, not the name.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from backend.dataset.merge.constants import (
    GAIN_KD_MAX,
    GAIN_KD_MIN,
    GAIN_KP_MAX,
    GAIN_KP_MIN,
    GAIN_MATCH_TOLERANCE,
    GAIN_PROFILE_ID_FIELD,
    GAIN_PROFILE_KD_FIELD,
    GAIN_PROFILE_KP_FIELD,
    GAIN_PROFILE_RELATIVE_PATH,
)


class GainTagMissingError(ValueError):
    """A merge source carries no gain-profile tag — the FAIL_BLOCKING defect.

    `02b` §8.2 WP-3D-06 ②: merging without a gain tag could silently mix following-error
    distributions, so an untagged source aborts the merge instead of being assumed safe.
    """


class GainProfileError(ValueError):
    """A gain-profile tag is malformed or carries an out-of-band gain.

    The DM MIT encoding bounds the gains (`03` §2.8, `FR-MOT-025`); a tag outside them
    never came from a real profile, so it is refused before it can drive a merge check.
    """


class GainProfileMismatchError(ValueError):
    """Two merge sources declare different gain profiles — the merge is refused.

    Mixing gain-profile-different episodes splits the following-error distribution
    (`FR-DAT-045`), so a merge across differing tags is blocked (`02b` §8.2 WP-3D-06 ②).
    """


def _float_vector(value: object) -> tuple[float, ...]:
    """Coerce a deserialised JSON value into a float tuple, or refuse it.

    Args:
        value: A value read from the gain tag JSON, expected to be a list of numbers.

    Returns:
        (tuple[float, ...]) The value as a float tuple.

    Raises:
        TypeError: When the value is not a list/tuple of numbers.
    """
    if not isinstance(value, (list, tuple)):
        raise TypeError(f"expected a list of numbers, got {type(value).__name__}")
    result: list[float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise TypeError(f"expected a number, got {type(item).__name__}")
        result.append(float(item))
    return tuple(result)


@dataclass(frozen=True)
class GainProfile:
    """A dataset's follower PD gain-profile tag: the id and the driving kp/kd vectors.

    Attributes:
        profile_id: The named profile the recording ran under (`03` §3.4:
            `compliant`/`stiff`/`lerobot_follower`/`teleop_follower`/`custom`).
        kp: The per-joint position stiffness vector the follower sent every frame.
        kd: The per-joint damping vector.
    """

    profile_id: str
    kp: tuple[float, ...]
    kd: tuple[float, ...]

    def __post_init__(self) -> None:
        """Refuse an unnamed profile, a width mismatch, or an out-of-band gain.

        Raises:
            GainProfileError: On an empty id, an empty or mismatched kp/kd width, or a
                gain outside the DM MIT encoding band.
        """
        if not self.profile_id.strip():
            raise GainProfileError("gain profile id must be a non-empty name")
        if not self.kp or not self.kd:
            raise GainProfileError("gain profile kp/kd must be non-empty vectors")
        if len(self.kp) != len(self.kd):
            raise GainProfileError(
                f"gain profile kp width {len(self.kp)} != kd width {len(self.kd)}"
            )
        for gain in self.kp:
            if not GAIN_KP_MIN <= gain <= GAIN_KP_MAX:
                raise GainProfileError(
                    f"kp {gain} is outside the DM MIT band [{GAIN_KP_MIN}, {GAIN_KP_MAX}]"
                )
        for gain in self.kd:
            if not GAIN_KD_MIN <= gain <= GAIN_KD_MAX:
                raise GainProfileError(
                    f"kd {gain} is outside the DM MIT band [{GAIN_KD_MIN}, {GAIN_KD_MAX}]"
                )

    def matches(self, other: GainProfile) -> bool:
        """Whether two tags are the same distribution — same id and same gains.

        The id must be equal and every kp/kd entry must agree within the float
        round-trip tolerance; a differing width is never a match.

        Args:
            other: The tag to compare against.

        Returns:
            (bool) True when the profiles are the same following-error distribution.
        """
        if self.profile_id != other.profile_id:
            return False
        if len(self.kp) != len(other.kp) or len(self.kd) != len(other.kd):
            return False
        pairs = (
            *zip(self.kp, other.kp, strict=True),
            *zip(self.kd, other.kd, strict=True),
        )
        return all(abs(mine - theirs) <= GAIN_MATCH_TOLERANCE for mine, theirs in pairs)

    def to_dict(self) -> dict[str, object]:
        """Serialise the tag to its JSON-safe on-disk form."""
        return {
            GAIN_PROFILE_ID_FIELD: self.profile_id,
            GAIN_PROFILE_KP_FIELD: list(self.kp),
            GAIN_PROFILE_KD_FIELD: list(self.kd),
        }

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> GainProfile:
        """Reconstruct a tag from its serialised form.

        Args:
            body: The parsed `meta/gain_profile.json` mapping.

        Returns:
            (GainProfile) The reconstructed tag.

        Raises:
            GainProfileError: When a required field is absent or malformed.
        """
        try:
            profile_id = str(body[GAIN_PROFILE_ID_FIELD])
            kp = _float_vector(body[GAIN_PROFILE_KP_FIELD])
            kd = _float_vector(body[GAIN_PROFILE_KD_FIELD])
        except (KeyError, TypeError, ValueError) as bad:
            raise GainProfileError(f"gain profile tag is malformed: {bad}") from bad
        return cls(profile_id=profile_id, kp=kp, kd=kd)


def gain_profile_path(root: Path) -> Path:
    """The gain-profile tag path for a dataset root.

    Args:
        root: The dataset root directory.

    Returns:
        (Path) `<root>/meta/gain_profile.json`.
    """
    return root / GAIN_PROFILE_RELATIVE_PATH


def write_gain_profile(root: Path, profile: GainProfile) -> None:
    """Stamp a dataset with its gain-profile tag.

    Args:
        root: The dataset root directory.
        profile: The gain profile the recording ran under.
    """
    path = gain_profile_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")


def read_gain_profile(repo_id: str, root: Path) -> GainProfile:
    """Read a dataset's gain-profile tag, or refuse a tagless dataset.

    Args:
        repo_id: The dataset identity, for the FAIL_BLOCKING message.
        root: The dataset root directory.

    Returns:
        (GainProfile) The tag read from disk.

    Raises:
        GainTagMissingError: When the dataset carries no tag (FAIL_BLOCKING).
        GainProfileError: When the tag file is malformed.
    """
    path = gain_profile_path(root)
    if not path.is_file():
        raise GainTagMissingError(
            f"dataset {repo_id!r} has no gain-profile tag at {path}; a gain-tagless merge "
            "could silently mix following-error distributions (WP-3D-06 FAIL_BLOCKING)"
        )
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as bad:
        raise GainProfileError(f"gain profile tag {path} is not valid JSON: {bad}") from bad
    return GainProfile.from_dict(body)


def verify_uniform_gain(profiles: list[GainProfile]) -> GainProfile:
    """Verify every source shares one gain profile; return the shared one.

    Args:
        profiles: The source gain tags, in merge order; at least one.

    Returns:
        (GainProfile) The first profile, now proven equal to every other.

    Raises:
        GainProfileMismatchError: When any source's profile differs from the first.
        GainProfileError: When no profiles are given.
    """
    if not profiles:
        raise GainProfileError("verify_uniform_gain needs at least one profile")
    reference = profiles[0]
    for other in profiles[1:]:
        if not reference.matches(other):
            raise GainProfileMismatchError(
                f"gain profile {other.profile_id!r} (kp={list(other.kp)}) differs from "
                f"{reference.profile_id!r} (kp={list(reference.kp)}); mixing gain-profile-"
                "different episodes splits the following-error distribution (WP-3D-06 refused)"
            )
    return reference
