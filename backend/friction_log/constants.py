"""Shared constants for the no-transmit logging tap (WP-2B-05)."""

from __future__ import annotations

# The pattern-A tick condition: 16 MIT frames per cycle (8 per arm, two arms — 10 §2.3).
# `PG-CAN-001` measures this on the bus; 32 frames would break the tick condition and
# force the ≤625 Hz variant. Held here as the width one logged frame is expected to carry
# and the count acceptance ⑦ compares the bus measurement against.
BIMANUAL_JOINT_COUNT = 16
