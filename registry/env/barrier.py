"""Start-blocking barrier: a work package may not start without the current env_hash.

`02a` §2.2 WP-ENV-04: every downstream WP manifest declares `env_hash`, and a
mismatch refuses start — the environment analogue of the normalization barrier
(`registry.normalization.barrier`). `05` §2.2 / `06` §2.2 give every manifest the
`env_hash` field; this module is the value half: a manifest that declares no
env_hash, or one whose value is not the hash currently issued, is refused start.

The mismatch case is the staleness barrier seen from the launch side: after a pin
or lock change bumps the issued env_hash, a manifest still citing the old value is
built against a superseded environment and must not spawn. Which already-running
`SHAPE-IM` descendants that same bump invalidates is the closure side, seeded on
`env_hash:CHANGED` through `registry.normalization.stale` (`02a` WP-ENV-04 reuses
that machinery rather than rebuilding it).

This is a launch-time gate invoked explicitly, not a member of the `CI-01..CI-18`
roster — it decides a start, it does not judge the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

ENV_HASH_FIELD = "env_hash"

REASON_ABSENT = "declares no env_hash"
REASON_MISMATCH = "cites a superseded env_hash"


@dataclass(frozen=True)
class EnvBarrierVerdict:
    """The outcome of checking one manifest against the issued env hash.

    Attributes:
        wp_id: The work package the manifest names, or `(unknown)`.
        blocked: True when the manifest is refused start.
        reason: Why it was blocked, empty when it is cleared.
        declared: The env hash the manifest cites, or None when it cites none.
        expected: The env hash currently issued.
    """

    wp_id: str
    blocked: bool
    reason: str
    declared: str | None
    expected: str

    def as_line(self) -> str:
        """Render the verdict as one report line.

        Returns:
            (str) Single-line human-readable form.
        """
        if not self.blocked:
            return f"{self.wp_id} CLEARED env_hash={self.expected}"
        return (
            f"{self.wp_id} BLOCKED {self.reason} (declared={self.declared}, issued={self.expected})"
        )


def check_manifest(manifest: dict[str, Any], issued_hash: str) -> EnvBarrierVerdict:
    """Decide whether a manifest may start against the issued env hash.

    Args:
        manifest: A parsed WP manifest mapping (`06` §2.2 field set).
        issued_hash: The env hash currently published by WP-ENV-04.

    Returns:
        (EnvBarrierVerdict) Blocked with a reason, or cleared.
    """
    wp_id = str(manifest.get("wp_id") or "(unknown)")
    declared_raw = manifest.get(ENV_HASH_FIELD)
    declared = str(declared_raw) if declared_raw else None

    if declared is None:
        return EnvBarrierVerdict(wp_id, True, REASON_ABSENT, None, issued_hash)
    if declared != issued_hash:
        return EnvBarrierVerdict(wp_id, True, REASON_MISMATCH, declared, issued_hash)
    return EnvBarrierVerdict(wp_id, False, "", declared, issued_hash)
