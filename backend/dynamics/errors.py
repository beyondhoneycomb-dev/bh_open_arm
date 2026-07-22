"""The single error type the v1->v2 dynamics converter raises on a refused load or conversion.

A subclass of `ValueError` so a caller that already guards asset loads for `ValueError`
keeps working, while a caller that wants to tell a dynamics refusal apart from an unrelated
value error can catch this type specifically. It is the load-refusal signal of FR-SAF-033
(an unconvertible v1 asset) and FR-SAF-067 (missing provenance, or a `robot_version != "2.0"`
parameter under strict mode): the asset is rejected at read time, never silently adopted.
"""

from __future__ import annotations


class DynamicsConversionError(ValueError):
    """A v1-derived dynamics asset that cannot be loaded or converted to the v2 frame.

    Raised for missing or incomplete provenance, a `robot_version != "2.0"` load under
    strict mode, an unconvertible item (a link7 inertia, the rotated base_link frame, or a
    gripper model), or a joint vector of the wrong width. Each carries its reason in the
    message so the refusal is auditable rather than a bare rejection.
    """
