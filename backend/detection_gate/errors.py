"""The refusals the WP-2C-02 detection activation gate raises when a safety rule is challenged.

`DetectionGateError` subclasses `ValueError` for the reason the sibling gates do (WP-2B-08's
`PathBError`, WP-2B-02's `GravityBackendError`): a caller already guarding config for `ValueError`
keeps working, while one that wants to tell a gate refusal apart can catch this type.

The two concrete refusals are the two failure modes the audit hunts (§2.0 THE ONE RULE):
`DetectionActivationRefusedError` is the code-level lock — activation attempted while it is not
permitted (PG-FRIC-001 not PASS, or the architecture-reopen state); `SilentDowngradeError` is the
downgrade that would pass without lowering the speed cap or showing the effective delay.
"""

from __future__ import annotations


class DetectionGateError(ValueError):
    """A detection-gate operation refused because it would defeat FR-SAF-029/030/001b."""


class DetectionActivationRefusedError(DetectionGateError):
    """Collision-detection activation was attempted while the gate does not permit it.

    FR-SAF-030 makes detection a function of PG-FRIC-001 PASS: until it passes, activation is a
    hard code-level block, raised rather than returned so a caller cannot ignore it. The same
    refusal covers the architecture-reopen state, where 1 kHz is unreachable by any frame pattern
    and running detection anyway would be an unaccepted degrade (02b §3.2 negative branch).
    """


class SilentDowngradeError(DetectionGateError):
    """A degraded activation would pass without its effective-delay display and lowered speed cap.

    02b §3.3 names the exact defect: displaying the effective latency without actually lowering
    the jog/teleop speed cap makes the display an alibi. A `DEGRADED_ACCEPTED` activation that
    does not carry a speed-cap scale below 1.0 (with the latency shown) is that silent downgrade,
    and the gate refuses to represent it (acceptance ③, "0 paths that silently pass a downgrade").
    """
