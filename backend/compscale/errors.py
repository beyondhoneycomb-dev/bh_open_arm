"""The single error type the WP-2B-09 scale-separation package raises on a refused scale set.

A subclass of `ValueError` so a caller already guarding config loads for `ValueError` keeps
working, while a caller that wants to tell a scale-separation refusal apart from an unrelated
value error can catch this type specifically.
"""

from __future__ import annotations


class ScaleSeparationError(ValueError):
    """A compensation-scale configuration that violates detection/control independence.

    Raised for a detection-model scale that is not the full 100% model (a residual model
    built on a partial model re-introduces the very bias this package exists to remove,
    FR-SAF-035), a control-compensation scale outside `[0, 1]` (a value above 1 over-
    compensates and injects energy), a joint or friction vector of the wrong width, or a
    static scan that finds detection and control scales bound to one variable. The set is
    refused at the point of use rather than yielding a silently wrong residual.
    """
