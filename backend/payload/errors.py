"""The single error type the payload package raises.

A payload that fails validation, a pose of the wrong width, or a preflight run against a
gravity-trimmed model are all misconfigurations of the same subsystem, so they share one
exception the caller can catch at the registry/preflight boundary.
"""

from __future__ import annotations


class PayloadError(Exception):
    """A payload registration, gravity-reflection, or effort-preflight misconfiguration."""
