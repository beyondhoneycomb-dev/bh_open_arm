"""Start-blocking barrier: a work package may not start without the current hash.

`SPINE` §5 and `02a` §1.5 WP-N1-04 make normalization a global blocking barrier —
no downstream work package starts without citing the normalization hash. `06` §2.2
gives every manifest a `normalization_hash` field, and `WP-BOOT-02` acceptance ⑦
digs that slot (a manifest missing the field is rejected at schema time). This
module is the value half WP-N1-04 owns: a manifest that declares no hash, or one
whose hash is not the hash currently issued, is refused start.

The mismatch case is the staleness barrier seen from the launch side: after a
ledger change bumps the issued hash, a manifest still citing the old hash is
citing a superseded normalization and must not spawn. Which already-running
descendants that same bump invalidates is the closure side, in
`registry/normalization/stale.py`.

This is a launch-time gate invoked explicitly (the normalization CLI, a spawn
adapter), not a member of the `CI-01..CI-18` roster — it decides a start, it does
not judge the corpus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

NORMALIZATION_FIELD = "normalization_hash"

REASON_ABSENT = "declares no normalization_hash"
REASON_MISMATCH = "cites a superseded normalization_hash"


@dataclass(frozen=True)
class BarrierVerdict:
    """The outcome of checking one manifest against the issued hash.

    Attributes:
        wp_id: The work package the manifest names, or `(unknown)`.
        blocked: True when the manifest is refused start.
        reason: Why it was blocked, empty when it is cleared.
        declared: The hash the manifest cites, or None when it cites none.
        expected: The hash currently issued.
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
            return f"{self.wp_id} CLEARED normalization_hash={self.expected}"
        return (
            f"{self.wp_id} BLOCKED {self.reason} (declared={self.declared}, issued={self.expected})"
        )


def check_manifest(manifest: dict[str, Any], issued_hash: str) -> BarrierVerdict:
    """Decide whether a manifest may start against the issued normalization hash.

    Args:
        manifest: A parsed WP manifest mapping (`06` §2.2 field set).
        issued_hash: The hash currently published by WP-N1-04.

    Returns:
        (BarrierVerdict) Blocked with a reason, or cleared.
    """
    wp_id = str(manifest.get("wp_id") or "(unknown)")
    declared_raw = manifest.get(NORMALIZATION_FIELD)
    declared = str(declared_raw) if declared_raw else None

    if declared is None:
        return BarrierVerdict(wp_id, True, REASON_ABSENT, None, issued_hash)
    if declared != issued_hash:
        return BarrierVerdict(wp_id, True, REASON_MISMATCH, declared, issued_hash)
    return BarrierVerdict(wp_id, False, "", declared, issued_hash)
