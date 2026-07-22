"""The single error type the gripper endpoint/mirror surface raises on a bad config.

A subclass of `ValueError` so a caller that already guards persistence loads for
`ValueError` keeps working, while a caller that wants to distinguish a gripper
schema refusal from an unrelated value error can catch this type specifically.
"""

from __future__ import annotations


class GripperConfigError(ValueError):
    """A gripper endpoint capture or limit config that violates the frozen schema.

    Raised for a sign-mirror violation (`left != (-hi_right, -lo_right)`), a force
    cap outside the per-unit domain, a degenerate endpoint pair, a bad side token,
    or a malformed speed cap. It is the load-refusal signal of FR-MAN-017 /
    FR-TEL-059: the config is rejected at read time, never silently adopted.
    """
