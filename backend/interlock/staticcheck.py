"""Acceptance ④ — the real-send interlock has zero bypass paths, proven statically.

An interlock bypass is any way to hold real-send authority without a genuine
dry-run grant. Since the *only* thing authorising real transmission is a
``TransmissionGrant``, and the *only* sanctioned minters of one live in
``sim/dryrun/interlock.py`` (guarded at runtime by its key-gated constructor), a
bypass in the real-send consumer tree can take exactly one shape: fabricating a
grant. An absence like that is only honest to check statically — a runtime test
shows the paths it happened to run, never the one a later edit adds — so this is an
AST scan, paired with a fixture that constructs a grant to prove the scan bites.

The detector itself is reused, not rebuilt: ``sim.dryrun.staticcheck``'s
``check_grant_construction`` already flags ``TransmissionGrant(...)`` construction.
Its one exemption is for a file *named* ``interlock.py`` (its own sanctioned minter),
and that exemption keys on basename alone — so a file named ``interlock.py`` placed
in this tree would be silently waved through, re-opening the bypass. This module
reuses the detector for the real work and adds one guard closing that loophole: no
file named ``interlock.py`` may exist under the scanned real-send tree.
"""

from __future__ import annotations

from pathlib import Path

from sim.dryrun.staticcheck import StaticFinding, check_grant_construction

RULE_SHADOW_INTERLOCK = "shadow-interlock-module"

# The basename the shared detector exempts; a file wearing it in this tree would
# dodge the grant-fabrication scan, so its mere presence here is a finding.
_EXEMPTED_BASENAME = "interlock.py"


def find_grant_fabrication(root: Path) -> tuple[StaticFinding, ...]:
    """Flag every real-send bypass under ``root`` (acceptance ④).

    Two forms are caught: a ``TransmissionGrant`` construction (via the reused Wave
    0-C detector), and a file named ``interlock.py`` that would be silently exempted
    from that detector, re-opening the bypass.

    Args:
        root: The real-send consumer tree to scan (``backend/interlock``).

    Returns:
        (tuple[StaticFinding, ...]) Findings in file-then-line order; empty when the
        tree has no bypass.
    """
    findings: list[StaticFinding] = []
    for path in sorted(root.rglob("*.py")):
        module = str(path)
        if path.name == _EXEMPTED_BASENAME:
            findings.append(
                StaticFinding(
                    rule=RULE_SHADOW_INTERLOCK,
                    module=module,
                    line=1,
                    message=(
                        "a file named interlock.py in the real-send tree is silently "
                        "exempted by the shared grant detector, re-opening the bypass "
                        "(02b §1.2 WP-2A-00 ④)"
                    ),
                )
            )
            continue
        findings.extend(check_grant_construction(path.read_text(encoding="utf-8"), module))
    return tuple(findings)
