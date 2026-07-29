"""Decide which arm is on which channel by moving one arm and watching which channel answers.

The bus cannot answer this (`03` §2.1: both arms use send `0x01–0x08` / recv `0x11–0x18`), and
this rig's adapter reports no serial so a udev rule can only key on a USB port path that changes
when the adapter moves. What does not change is the arm: if a human moves the left arm and one
channel's joint positions move, that channel is the left arm. No model, no root, no port path.

Torque stays off throughout. `connect_readonly` opens the bus and warms feedback without
`enable_torque` and without zeroing (`02` FR-CON-062, `12` FR-SAF-075), which is exactly the
state where a person can backdrive the arm by hand.

The judgment is deliberately one-sided. A channel counts as moved only when its motion clears
`MOTION_THRESHOLD_RAD` **and** every other channel stays under `QUIET_THRESHOLD_RAD`; anything
else is reported as inconclusive rather than resolved to the larger number. Two arms that both
register motion means the operator brushed both, or a cable is transmitting a knock — and
guessing between them is the one failure this whole module exists to prevent.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

# How far a joint must move before the motion is the operator's and not sensor noise. The DM
# encoders resolve far finer than this; the margin is for a hand resting on a link, not for
# quantisation.
MOTION_THRESHOLD_RAD = 0.05

# How still every other channel must stay for the moved one to be unambiguous. Below the motion
# threshold on purpose: the gap between them is the band where the answer is "ask again".
QUIET_THRESHOLD_RAD = 0.01

# A reading is one channel's joint vector. The caller supplies the reader so this module needs no
# CAN socket and the tests need no rig.
JointReader = Callable[[str], Sequence[float]]


class IdentificationError(Exception):
    """Raised when identification cannot produce an unambiguous answer."""


@dataclass(frozen=True)
class ChannelMotion:
    """How much one channel's joints moved between two readings.

    Attributes:
        interface: The kernel interface the reading came from.
        max_delta_rad: The largest absolute per-joint change, radians.
    """

    interface: str
    max_delta_rad: float

    @property
    def moved(self) -> bool:
        """Whether this channel cleared the motion threshold."""
        return self.max_delta_rad >= MOTION_THRESHOLD_RAD

    @property
    def quiet(self) -> bool:
        """Whether this channel stayed under the quiet threshold."""
        return self.max_delta_rad <= QUIET_THRESHOLD_RAD


@dataclass(frozen=True)
class IdentificationResult:
    """The outcome of one move-and-watch round.

    Attributes:
        moved_interface: The single channel that moved, or None when the round was inconclusive.
        motions: Every channel's measured motion, for the operator to see the numbers.
        reason: Why the round was inconclusive; empty when it resolved.
    """

    moved_interface: str | None
    motions: tuple[ChannelMotion, ...]
    reason: str

    @property
    def resolved(self) -> bool:
        """Whether exactly one channel moved while the rest stayed still."""
        return self.moved_interface is not None


def measure_motion(
    interfaces: Sequence[str], read_joints: JointReader, before: dict[str, Sequence[float]]
) -> tuple[ChannelMotion, ...]:
    """Read every channel again and return how far each moved since `before`.

    Args:
        interfaces: The channels to read, in any order.
        read_joints: Reads one channel's joint vector; supplied by the caller so this module
            opens no socket.
        before: The baseline reading per interface, from `read_baseline`.

    Returns:
        (tuple[ChannelMotion, ...]) One entry per interface, in the order given.

    Raises:
        IdentificationError: When a channel has no baseline, or when its width changed between
            readings — a changed width means the two readings are not comparable and the delta
            would be computed over a truncation.
    """
    motions: list[ChannelMotion] = []
    for interface in interfaces:
        baseline = before.get(interface)
        if baseline is None:
            raise IdentificationError(f"{interface} has no baseline reading")
        now = read_joints(interface)
        if len(now) != len(baseline):
            raise IdentificationError(
                f"{interface} returned {len(now)} joints, baseline had {len(baseline)}"
            )
        delta = max((abs(a - b) for a, b in zip(now, baseline, strict=True)), default=0.0)
        motions.append(ChannelMotion(interface=interface, max_delta_rad=delta))
    return tuple(motions)


def read_baseline(
    interfaces: Sequence[str], read_joints: JointReader
) -> dict[str, Sequence[float]]:
    """Read every channel once, before the operator touches anything."""
    return {interface: tuple(read_joints(interface)) for interface in interfaces}


def judge(motions: tuple[ChannelMotion, ...]) -> IdentificationResult:
    """Decide which channel moved, refusing anything short of one clear answer.

    Args:
        motions: Per-channel motion from `measure_motion`.

    Returns:
        (IdentificationResult) Resolved only when exactly one channel cleared the motion
            threshold and every other stayed under the quiet threshold. Every other shape —
            nothing moved, two moved, one moved while another drifted into the middle band —
            is inconclusive with the reason stated.
    """
    if not motions:
        return IdentificationResult(None, motions, "no channels were read")
    moved = [motion for motion in motions if motion.moved]
    if not moved:
        return IdentificationResult(
            None,
            motions,
            f"no channel moved more than {MOTION_THRESHOLD_RAD} rad; move the arm further, "
            "and check the arm is powered and the link is up",
        )
    if len(moved) > 1:
        names = ", ".join(motion.interface for motion in moved)
        return IdentificationResult(
            None, motions, f"more than one channel moved ({names}); move only one arm"
        )
    winner = moved[0]
    noisy = [
        motion for motion in motions if motion.interface != winner.interface and not motion.quiet
    ]
    if noisy:
        names = ", ".join(f"{m.interface}={m.max_delta_rad:.4f}rad" for m in noisy)
        return IdentificationResult(
            None,
            motions,
            f"{winner.interface} moved but {names} did not stay still "
            f"(under {QUIET_THRESHOLD_RAD} rad); let go of the other arm and repeat",
        )
    return IdentificationResult(winner.interface, motions, "")


def identify_moved_channel(
    interfaces: Sequence[str],
    read_joints: JointReader,
    prompt_operator: Callable[[], None],
) -> IdentificationResult:
    """Run one round: read, ask the operator to move one arm, read again, judge.

    Args:
        interfaces: The channels in play.
        read_joints: Reads one channel's joint vector.
        prompt_operator: Blocks until the operator says they have moved the arm. The caller owns
            how that is asked — a CLI `input()`, a GUI button, a test stub.

    Returns:
        (IdentificationResult) The round's outcome; check `resolved` before using it.
    """
    baseline = read_baseline(interfaces, read_joints)
    prompt_operator()
    return judge(measure_motion(interfaces, read_joints, baseline))
