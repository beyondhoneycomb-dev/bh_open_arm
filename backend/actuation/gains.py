"""The named PD gain profiles — the canon `03` §2.8 declares, in one place (FR-MOT-024).

`03` §2.8 registers five sets and says so explicitly: there is no single gain vector to pin.
The shoulder runs kp 70 under `compliant` and kp 240 under `lerobot_follower`, and that 3.4x is
real stiffness rather than a unit difference — LeRobot converts deg to rad before encoding, so
both paths write the same Nm/rad MIT field. A build that fixes one vector makes every other path
silently wrong, which is why a caller names a profile instead of passing numbers.

Four properties this module holds, each named with what enforces it:

1. **Lookup is by name and an unknown name is refused** (`resolve_gain_profile`). No default and
   no nearest match: `13` FR-GUI-068 requires the active profile name and its values to be
   answerable at any moment and forbids control starting with none loaded, and a lookup that
   quietly substitutes one turns that answer into a guess.
2. **Vectors are per joint** (`NamedGainProfile.kp` / `.kd`). A scalar broadcast is the failure
   `03` §2.8 exists to prevent — under `compliant` the elbow is kp 60 and the wrist kp 10, and
   one number cannot be both.
3. **Every profile carries its provenance** (`source`, `lineage`). Two of the five are v1-era
   numbers and one is v1-only; `03` FR-MOT-026 forbids offering those without the label, and
   LeRobot ships one of them as its running default.
4. **A profile covers exactly the joints its source declares** (`for_send_ids`). `calib_hold` has
   seven entries where the others have eight, and an id a profile does not cover is refused
   rather than padded with a neighbour's value.

The registered numbers are checked against the gateway's own gain envelope at import
(`_validate_registered`), importing `backend.actuation.safety`'s bounds rather than restating
them: a profile the single send_action gateway would reject is not a profile this rig can run,
and finding that out at import beats finding it out with the arm energized.

Scope is §2.8 only. §2.9's limit sets stay where their enforcement already lives — a limit is
meaningless without its frame (F_URDF vs F_motor, `03` §2.9) and the plan resolved limits as a
subset hierarchy with a validator (`12` FR-SAF-045, `03` FR-MOT-032), which is `SafetyLimits` in
`safety.py`. A name-to-vector table cannot express "operational must be contained in mechanical",
so folding the two canons together would lose the check that makes the limit canon useful.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType

from backend.actuation.safety import (
    KD_MAX,
    KD_MIN,
    KP_MAX,
    KP_MIN,
    POSITION_CONTROL_KD_FLOOR,
    POSITION_CONTROL_KP_FLOOR,
)
from backend.endeffector import ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID

# The joint order every registered vector is indexed by: index 0 = J1 = CAN send id `0x01`,
# through J7, then the gripper at `0x08` for the profiles whose source declares an eighth entry
# (`03` §2.8 column header, "kp (J1…J7[, J8])").
PROFILE_SEND_IDS: tuple[int, ...] = (*ARM_JOINT_SEND_IDS, GRIPPER_SEND_ID)

# The two widths a source is allowed to declare: the seven arm joints, or those plus the gripper.
ARM_ONLY_WIDTH = len(ARM_JOINT_SEND_IDS)
WITH_GRIPPER_WIDTH = len(PROFILE_SEND_IDS)

# The registered profile ids. Named because a caller that spells one wrong gets a refusal at the
# lookup, and a caller that spells one wrong in a comparison gets silence.
COMPLIANT = "compliant"
STIFF = "stiff"
LEROBOT_FOLLOWER = "lerobot_follower"
TELEOP_FOLLOWER = "teleop_follower"
CALIB_HOLD = "calib_hold"

# What LeRobot applies when nothing overrides it (`03` §2.8, confirmed): `send_action` reads the
# config's `position_kp` and `position_kd` into every MIT frame it builds
# (`openarm_follower.py:319-340`). The other four reach a motor only through
# `send_action(action, custom_kp=..., custom_kd=...)`, so selecting a profile anywhere else in
# this codebase changes nothing on the wire by itself.
LEROBOT_RUNTIME_PROFILE = LEROBOT_FOLLOWER

# The ros2_control gripper's own gains (`03` §2.8 final row, FR-MOT-029). Deliberately not a sixth
# profile: it is one motor's slot in a stack that is not our runtime (`03` §2.9 cites ros2_control
# and MoveIt for provenance only), and what LeRobot actually sends to `0x08` is
# `lerobot_follower`'s eighth entry — kp 25 / kd 0.3, which is neither this pair nor
# `openarm_cell.yaml`'s kd 0.2. Three different numbers for one motor, so none of them may be
# folded into the arm vectors.
ROS2_CONTROL_GRIPPER_KP = 5.0
ROS2_CONTROL_GRIPPER_KD = 0.1


class GainProfileError(ValueError):
    """Raised when a registered profile is asked for a joint it does not cover."""


class UnknownGainProfileError(LookupError):
    """Raised when a name is not a registered profile — never resolved to a default."""


class GainLineage(Enum):
    """Which robot generation a profile's numbers were tuned for (`03` FR-MOT-026).

    The 240-series sets predate the first v2.0 asset by ten months — `openarm_teleop`'s
    `config/follower.yaml` has been untouched since its 2025-07-23 import commit, and
    `openarm_description` gained v2.0 assets on 2026-05-18 — and LeRobot ships one of them as its
    default. A build that says nothing therefore runs v1 gains on a v2 arm, so the lineage travels
    with the numbers and is required wherever a profile is offered.
    """

    V2_CANON = "v2_canon"
    V1_DERIVED = "v1_derived"
    V1_ONLY = "v1_only"


@dataclass(frozen=True)
class JointGains:
    """One joint's stiffness and damping together.

    Attributes:
        send_id: The CAN send id these gains belong to.
        kp: Position gain, Nm/rad on the MIT field.
        kd: Velocity gain, Nm·s/rad on the MIT field.

    The pair travels as one value because the MIT law couples them: `03` FR-MOT-021 forbids a
    driving kp with kd = 0, so a kp handed around without its kd cannot be checked.
    """

    send_id: int
    kp: float
    kd: float


@dataclass(frozen=True)
class NamedGainProfile:
    """One registered gain set: the per-joint vectors and where they came from.

    Attributes:
        name: The id `resolve_gain_profile` looks it up by.
        kp: Per-joint position gains, index 0 = J1. Seven or eight entries — the width is the
            source's own and is never padded to a common one.
        kd: Per-joint velocity gains, same indexing and width as `kp`.
        lineage: Which generation the numbers were tuned for (`03` FR-MOT-026).
        source: The primary source `03` §2.8 cites for these numbers.
        role: What the set is for, and what a caller choosing it is choosing.
    """

    name: str
    kp: tuple[float, ...]
    kd: tuple[float, ...]
    lineage: GainLineage
    source: str
    role: str

    @property
    def is_canonical(self) -> bool:
        """Whether these numbers are v2 canon, or v1-era values needing the non-canonical label."""
        return self.lineage is GainLineage.V2_CANON

    @property
    def covers_gripper(self) -> bool:
        """Whether this profile declares an eighth entry for the gripper at `0x08`."""
        return len(self.kp) == WITH_GRIPPER_WIDTH

    @property
    def send_ids(self) -> tuple[int, ...]:
        """The CAN send ids this profile has entries for, in vector order."""
        return PROFILE_SEND_IDS[: len(self.kp)]

    def for_send_id(self, send_id: int) -> JointGains:
        """Return one joint's gains from this profile.

        Args:
            send_id: The motor's CAN send id, `0x01..0x08`.

        Returns:
            (JointGains) That joint's pair.

        Raises:
            GainProfileError: When this profile has no entry for that id. `calib_hold` is the live
                case: its source drives the seven arm joints as one list and bumps the gripper
                separately under its own contact threshold, so asking it for `0x08` is asking for
                a number that does not exist rather than one that happens to be missing.
        """
        ids = self.send_ids
        if send_id not in ids:
            raise GainProfileError(
                f"profile {self.name!r} has no entry for CAN send id {send_id:#04x}; it covers "
                f"{', '.join(f'{covered:#04x}' for covered in ids)}"
            )
        index = ids.index(send_id)
        return JointGains(send_id=send_id, kp=self.kp[index], kd=self.kd[index])

    def for_send_ids(self, send_ids: Sequence[int]) -> tuple[JointGains, ...]:
        """Return the gains for exactly the motors named, in the order named.

        This is where a profile's gripper entry either applies or does not, and the decision is
        the fitted set's rather than this module's: a caller passes the ids its end-effector
        record says are on the bus (`backend.endeffector.EndEffectorProfile.motor_send_ids`), so
        on this rig — `fixed_spatula`, seven joints, no `0x08` — the eighth entry of the
        eight-wide profiles is left out because no fitted id asks for it. Nothing is padded and
        nothing is truncated to a length; an id the profile does not cover is refused.

        Args:
            send_ids: The fitted motors' CAN send ids.

        Returns:
            (tuple[JointGains, ...]) One pair per id, in the order given.

        Raises:
            GainProfileError: When any id is outside this profile's coverage.
        """
        return tuple(self.for_send_id(send_id) for send_id in send_ids)


_REGISTERED: tuple[NamedGainProfile, ...] = (
    NamedGainProfile(
        name=COMPLIANT,
        kp=(70.0, 70.0, 70.0, 60.0, 10.0, 10.0, 10.0, 10.0),
        kd=(2.75, 2.5, 2.0, 2.0, 0.7, 0.6, 0.5, 0.2),
        lineage=GainLineage.V2_CANON,
        source=(
            "openarm_driver/configs/openarm_cell.yaml control_gains + "
            "openarm_description/.../control/control_gains.yaml (identical over J1-J7)"
        ),
        role=(
            "The driver and ros2_control default: soft enough to back-drive, which is what "
            "contact work and a hand on the arm need."
        ),
    ),
    NamedGainProfile(
        name=STIFF,
        kp=(230.0, 230.0, 190.0, 190.0, 30.0, 30.0, 30.0, 10.0),
        kd=(2.7, 2.7, 2.2, 2.2, 1.5, 1.5, 1.5, 0.2),
        lineage=GainLineage.V2_CANON,
        source="openarm_driver/configs/openarm_cell_higher_pd.yaml",
        role=(
            "Identical to the openarm_mujoco/v2 actuator kp/kv, which makes it the only profile "
            "whose real response matches the sim — the sim-real parity canon (`09` FR-SIM-028b). "
            "Running the twin or a dry run on any other profile poisons the residual by the gain "
            "gap."
        ),
    ),
    NamedGainProfile(
        name=LEROBOT_FOLLOWER,
        kp=(240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 25.0),
        kd=(5.0, 5.0, 3.0, 5.0, 0.3, 0.3, 0.3, 0.3),
        lineage=GainLineage.V1_DERIVED,
        source="lerobot/robots/openarm_follower/config_openarm_follower.py:102-105",
        role=(
            "The only profile the LeRobot runtime actually applies (`03` §2.8, confirmed): "
            "send_action writes the config's position_kp/position_kd into every MIT frame, so "
            "this is what runs when nothing selects otherwise. J1-J7 kp match openarm_teleop's "
            "v1 values, and kd 5.0 is the MIT encoding ceiling itself — it cannot go higher."
        ),
    ),
    NamedGainProfile(
        name=TELEOP_FOLLOWER,
        kp=(240.0, 240.0, 240.0, 240.0, 24.0, 31.0, 25.0, 16.0),
        kd=(3.0, 3.0, 3.0, 3.0, 0.2, 0.2, 0.2, 0.2),
        lineage=GainLineage.V1_ONLY,
        source="openarm_teleop/config/follower.yaml",
        role=(
            'The bilateral teleop follower\'s set, from a repository pinned to ARM_TYPE="v10" '
            "and shipped with a tanh friction model tuned alongside it. v1-only: the same file's "
            "soft limits exceed v2 mechanical stops on J2/J4/J6/J8."
        ),
    ),
    NamedGainProfile(
        name=CALIB_HOLD,
        kp=(300.0, 300.0, 150.0, 150.0, 40.0, 40.0, 30.0),
        kd=(2.5, 2.5, 2.5, 2.5, 0.8, 0.8, 0.8),
        lineage=GainLineage.V2_CANON,
        source="openarm_can/setup/openarm-can-zero-position-calibration",
        role=(
            "Zero-calibration hold only, and not a control or benchmark set (`15` Q-11): the "
            "shoulder at kp 300 is there to hold a joint against a mechanical stop. Seven entries "
            "because that script drives the arm as a seven-motor list and constructs the gripper "
            "separately, with its own contact threshold (dq<0.3, |tau|>0.3 against the arm's "
            "dq<0.1, |tau|>2.0). The bump phase itself runs different gains again (kp 45/280), so "
            "this is the hold, not the whole calibration."
        ),
    ),
)


def _validate_registered(profile: NamedGainProfile) -> None:
    """Refuse a registered profile the send_action gateway would reject anyway.

    The check runs at import over every row, so a transcription slip is an ImportError at the
    bench rather than a rejected command with the arm energized — or worse, a silently wrapped
    gain, since the vendor encoder clamps out-of-range values without an error (FR-MOT-018).

    Args:
        profile: The row to check.

    Raises:
        GainProfileError: When the vectors disagree in length, declare a width no arm has, carry a
            gain outside the MIT encoding band, or pair a driving stiffness with zero damping
            (`03` FR-MOT-021).
    """
    if len(profile.kp) != len(profile.kd):
        raise GainProfileError(
            f"profile {profile.name!r} has {len(profile.kp)} kp entries and {len(profile.kd)} kd "
            "entries; a joint without both halves of its pair cannot be commanded"
        )
    if len(profile.kp) not in (ARM_ONLY_WIDTH, WITH_GRIPPER_WIDTH):
        raise GainProfileError(
            f"profile {profile.name!r} declares {len(profile.kp)} joints; an arm is "
            f"{ARM_ONLY_WIDTH} joints, or {WITH_GRIPPER_WIDTH} with the gripper"
        )
    for index, (kp, kd) in enumerate(zip(profile.kp, profile.kd, strict=True)):
        if not KP_MIN <= kp <= KP_MAX:
            raise GainProfileError(
                f"profile {profile.name!r} kp[{index}]={kp} is outside the MIT encoding band "
                f"[{KP_MIN}, {KP_MAX}]"
            )
        if not KD_MIN <= kd <= KD_MAX:
            raise GainProfileError(
                f"profile {profile.name!r} kd[{index}]={kd} is outside the MIT encoding band "
                f"[{KD_MIN}, {KD_MAX}]"
            )
        if kp > POSITION_CONTROL_KP_FLOOR and kd <= POSITION_CONTROL_KD_FLOOR:
            raise GainProfileError(
                f"profile {profile.name!r} pairs kp[{index}]={kp} with kd[{index}]={kd}; Damiao "
                "states a position command with zero damping makes the motor vibrate or run away "
                "(03 FR-MOT-021)"
            )


for _profile in _REGISTERED:
    _validate_registered(_profile)

GAIN_PROFILES: Mapping[str, NamedGainProfile] = MappingProxyType(
    {profile.name: profile for profile in _REGISTERED}
)


def profile_names() -> tuple[str, ...]:
    """The registered profile ids, in the order `03` §2.8 tabulates them."""
    return tuple(profile.name for profile in _REGISTERED)


def resolve_gain_profile(name: str) -> NamedGainProfile:
    """Return the registered profile with this name, or refuse.

    There is no default parameter and no fallback by design. `13` FR-GUI-068 forbids control
    starting with no profile loaded and requires the active name to be answerable; a resolver that
    substituted a profile for an unrecognised name would satisfy the call and break the guarantee,
    and the arm would run gains nobody chose.

    Args:
        name: The profile id.

    Returns:
        (NamedGainProfile) The registered set.

    Raises:
        UnknownGainProfileError: When no profile carries that name.
    """
    profile = GAIN_PROFILES.get(name)
    if profile is None:
        raise UnknownGainProfileError(
            f"{name!r} is not a registered gain profile; `03` §2.8 registers "
            f"{', '.join(profile_names())}"
        )
    return profile
