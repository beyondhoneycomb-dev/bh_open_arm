"""The IK 16-slot layout and the CTR-ACT action contract must name the same arm per slot.

`contracts/unit_tags.yaml` freezes `arms: [left, right]`, and every consumer of an
accepted action reads it that way: `sim.mujoco.sim_sync.action_channel_order`, the dry-run
gate that zips those names onto the values, the follower's `send_action` prefix split, and
the recorded dataset's `action` column.

The IK side is anchored on `sim.ik.limits.all_soft_limits`, which is what the adapter
clamps against and what `backend.cartesian_jog`, `backend.moveto.limits`,
`backend.inference.load_preflight.limits`, `sim.ik.bench` and `sim.fkik.roundtrip` all
index positionally.

If those two disagree, the dry-run gate checks each arm against the *other* arm's limits.
Thirteen of the sixteen joints have symmetric limits, so the disagreement is invisible on
them; `joint_2` is the exception (left −90..9 deg, right −9..90 deg) and inverts there.

A round trip cannot detect this. The adapter is fed a 16-vector and returns one, so an
unconverted order on both sides cancels; it only shows when the value crosses to a
consumer that labels the slots. That is why this test compares the two declarations
directly instead of asserting on a solve.
"""

from __future__ import annotations

import pytest

pytest.importorskip("mujoco")
pytest.importorskip("mink")
pytest.importorskip("lerobot")

from sim.ik.limits import all_soft_limits
from sim.mujoco.sim_sync import action_channel_order


def _contract_side(channel: str) -> str:
    """Return the arm a contract channel name belongs to."""
    return channel.split("_", 1)[0]


def _ik_side(mjcf_joint: str) -> str:
    """Return the arm an MJCF joint name belongs to (``openarm_<side>_<joint>``)."""
    return mjcf_joint.split("_")[1]


def test_every_slot_names_the_same_arm_on_both_sides_of_the_boundary() -> None:
    """Slot i must be the same physical arm in the IK layout and in the action contract."""
    contract = action_channel_order(bimanual=True)
    ik_layout = [limit.mjcf_joint for limit in all_soft_limits()]
    assert len(contract) == len(ik_layout)

    mismatched = [
        (index, contract[index], ik_layout[index])
        for index in range(len(contract))
        if _contract_side(contract[index]) != _ik_side(ik_layout[index])
    ]
    assert not mismatched, (
        "the IK slot layout and the action contract disagree on which arm each slot is; "
        f"{len(mismatched)}/{len(contract)} slots differ, e.g. "
        f"slot {mismatched[0][0]} is {mismatched[0][1]!r} to the contract "
        f"and {mismatched[0][2]!r} to IK"
    )


def test_joint_2_is_the_asymmetric_limit_this_disagreement_would_hide_behind() -> None:
    """Pin the asymmetry that makes the swap detectable at all.

    If a future limit revision makes `joint_2` symmetric like the rest, an arm-order swap
    becomes undetectable by limit checking alone, and the test above is the only thing
    left standing between it and a wrong-arm command.
    """
    by_joint = {limit.mjcf_joint: limit for limit in all_soft_limits()}
    left = by_joint["openarm_left_joint2"]
    right = by_joint["openarm_right_joint2"]

    assert (left.lower_deg.value, left.upper_deg.value) != (
        right.lower_deg.value,
        right.upper_deg.value,
    ), "joint_2 limits are no longer asymmetric; an arm-order swap would pass limit checks"
