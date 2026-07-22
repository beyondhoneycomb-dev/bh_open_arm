"""The single error type the WP-2B-07 friction identification raises on a refused input or fit.

A subclass of `ValueError` so a caller already guarding config loads for `ValueError` keeps
working, while a caller that wants to tell a friction-identification refusal apart from an
unrelated value error can catch this type specifically.
"""

from __future__ import annotations


class FrictionIdentificationError(ValueError):
    """A friction identification that cannot be run or written as configured.

    Raised for an excitation log of the wrong width or with mismatched per-sample array
    lengths, a joint vector that is not `ARM_JOINT_COUNT` wide, a non-positive logging
    frequency, or a friction.yaml write whose parameters or metadata are incomplete. The
    input is refused at the point of use rather than producing a silently wrong friction fit,
    which would leak a gravity or inertia error into the identified parameters (spec 12 §2.6).
    """
