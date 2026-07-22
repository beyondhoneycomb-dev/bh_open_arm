"""The error types the WP-2B-03 gravity-model verification raises on a refused run.

Both subclass `ValueError` so a caller already guarding config loads keeps working, while a
caller that wants to tell a verification refusal apart from an unrelated value error can catch
these specifically.
"""

from __future__ import annotations


class GravityVerifyError(ValueError):
    """A gravity-model verification that cannot be run or assembled as configured.

    Raised for a pose/measurement grid of the wrong shape, a joint vector of the wrong width,
    or a measurement whose basis cannot be trusted. The run is refused at the point of use
    rather than returning a silently wrong residual.
    """


class VerificationRefusedError(GravityVerifyError):
    """Verification was refused because torque measurement is unavailable (FR-SAF-072).

    `use_velocity_and_torque=false` collapses the follower state to position-only, so there is
    no `.torque` channel and therefore no `tau_meas` (spec 12 §2.15 / spec 09 FR-SIM-025b). A
    residual table without a real measured torque cannot be computed, so the verification is
    refused rather than run against a fabricated measurement — the WP-2B-03 acceptance-③
    contract that this is refused execution, not a warning.
    """
