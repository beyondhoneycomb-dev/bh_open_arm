"""Datagram builders for the WP-3B-07 VR UDP tests.

The frozen synthetic stream (`contracts/fixtures/vr_pose_stream.py`) is the primary
input: `datagram_from_sample` serialises one of its samples to the exact wire shape
the receiver parses. `raw_payload` builds a hand-specified frame so a test can drive
cases the smooth synthetic trajectory never emits on its own — chiefly per-arm
validity divergence (`vl` != `vr`), which the fixture always sets equal. Kept out of
a `test_` module so pytest does not collect it.
"""

from __future__ import annotations

import json

from contracts.fixtures.vr_pose_stream import SyntheticVrPoseStream
from contracts.teleop import TeleopValidity


def datagram_from_sample(stream: SyntheticVrPoseStream, index: int) -> bytes:
    """Serialise one synthetic sample to a newline-terminated UTF-8 JSON datagram."""
    return (json.dumps(stream.sample(index).udp_payload()) + "\n").encode("utf-8")


def raw_payload(
    *,
    source_ts: float = 1.5,
    left_position: tuple[float, float, float] = (0.1, 0.0, 0.0),
    right_position: tuple[float, float, float] = (0.5, 0.0, 0.0),
    left_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    right_quaternion: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0),
    left_grip: float = 0.25,
    right_grip: float = 0.75,
    validity: TeleopValidity = TeleopValidity.OK,
    left_validity: TeleopValidity | None = None,
    right_validity: TeleopValidity | None = None,
) -> dict[str, object]:
    """Build a wire payload with independent per-arm validity.

    `left_validity`/`right_validity` default to the overall `validity`; a test sets
    them apart to exercise per-arm exposure.
    """
    return {
        "t": source_ts,
        "lc": list(left_position),
        "rc": list(right_position),
        "lt": list(left_quaternion),
        "rt": list(right_quaternion),
        "lg": left_grip,
        "rg": right_grip,
        "a": False,
        "b": False,
        "x": False,
        "y": False,
        "v": int(validity),
        "vl": int(left_validity if left_validity is not None else validity),
        "vr": int(right_validity if right_validity is not None else validity),
    }


def datagram(payload: dict[str, object]) -> bytes:
    """Serialise a wire payload to a newline-terminated UTF-8 JSON datagram."""
    return (json.dumps(payload) + "\n").encode("utf-8")
