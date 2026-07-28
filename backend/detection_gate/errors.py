"""The refusals the WP-2C-02 detection activation gate raises when a safety rule is challenged.

`DetectionGateError` subclasses `ValueError` for the reason the sibling gates do (WP-2B-08's
`PathBError`, WP-2B-02's `GravityBackendError`): a caller already guarding config for `ValueError`
keeps working, while one that wants to tell a gate refusal apart can catch this type.

The concrete refusals split by what was attempted. `DetectionActivationRefusedError` is the
code-level lock — activation attempted while it is not permitted (PG-FRIC-001 not PASS, or the
architecture-reopen state). `SilentDowngradeError` is the downgrade that would pass without
lowering the speed cap or showing the effective delay. `ObserverDivergenceError` is neither an
activation attempt nor a downgrade but a configuration that cannot detect at all.
"""

from __future__ import annotations


class DetectionGateError(ValueError):
    """A detection-gate operation refused because it would defeat FR-SAF-029/030/001b."""


class DetectionActivationRefusedError(DetectionGateError):
    """Collision-detection activation was attempted while the gate does not permit it.

    FR-SAF-030 makes detection a function of PG-FRIC-001 PASS: until it passes, activation is a
    hard code-level block, raised rather than returned so a caller cannot ignore it. The same
    refusal covers the architecture-reopen state, where the achievable loop rate cannot satisfy
    the observer's convergence bound and running detection anyway would be an unaccepted degrade
    (02b §3.2 negative branch, NORM-008).
    """


class SilentDowngradeError(DetectionGateError):
    """A degraded activation would pass without its effective-delay display and lowered speed cap.

    02b §3.3 names the exact defect: displaying the effective latency without actually lowering
    the jog/teleop speed cap makes the display an alibi. A `DEGRADED_ACCEPTED` activation that
    does not carry a speed-cap scale below 1.0 (with the latency shown) is that silent downgrade,
    and the gate refuses to represent it (acceptance ③, "0 paths that silently pass a downgrade").
    """


class ObserverDivergenceError(DetectionGateError):
    """A gain and detection period were paired that the forward-Euler residual diverges at.

    NORM-008's one exception to "no frequency is a pass/fail gate": `K*dt < 2` is not a quality
    target but the condition under which the residual means anything, so a configuration outside
    it is refused rather than run. Raised when an operator-set gain is persisted against the
    detection period, and when a verdict that would permit detection is constructed over a loop
    the gain cannot converge at.
    """
