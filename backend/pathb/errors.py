"""The error types the WP-2B-08 path-B bootstrap raises when a safety rule is challenged.

`PathBError` subclasses `ValueError` for the same reason WP-2B-02's `GravityBackendError` does:
a caller already guarding config for `ValueError` keeps working, while one that wants to tell a
path-B refusal apart can catch this type. `DetectionLockError` is the specific refusal the
CG-2B-08c code-level lock raises — enabling collision detection under path B is not a recoverable
request but the action FR-SAF-030 forbids until the v2 friction model is identified.
"""

from __future__ import annotations


class PathBError(ValueError):
    """A path-B bootstrap operation refused because it would misrepresent the fallback.

    Raised when a caller tries to record path B's PG-FRIC-001 result as anything other than
    FAIL_BLOCKING — a "partial success" record is the exact defect 02b §2.1 names.
    """


class DetectionLockError(PathBError):
    """An attempt to enable collision detection while path B is the compensation basis.

    FR-SAF-030 forces detection DISABLED until the v2 friction model is identified. Path B is by
    definition the state where it is not, so this is a hard code-level block, not a togglable
    preference — the lock raises rather than returning a value a caller could ignore.
    """
