"""Static ban on the WS envelope forking a primitive or the lease semantics.

`02b` §5.2 WP-3A-04 makes two forks build-blocking, and this scan is what makes
each bite:

1. A `CTR-PRIM@v1` primitive redefinition — the same fork every 3A consumer is
   forbidden. Delegated to `contracts.prim.check_no_redefinition`, because the WS
   is a consumer of the primitives like any other (a WS that restates the camera
   identifier, or rebinds `EXPIRY_JUDGE_ROLE` to the client, is caught there).
2. A lease-semantics redefinition — unique to the WS. The lease semantics are
   `WP-2A-02`'s canon (`backend.deadman`, U-4), and the WS transports them; a
   `contracts`-tree module that *defines* one of the canon's own types — its own
   `DeadmanLease`, its own `RenewalDecision`, its own `RearmHandshake` — has copied
   the semantics into the transport, which is the "same lease, two meanings"
   `FAIL_BLOCKING`. The two trees do not import each other (`06` §5.6), so the ban
   is on the canon type *names*, held here as literals rather than by import.

The distinction, as in `contracts.prim.redefinition`, is definition vs consumption:
importing a name binds it by import and is fine; a module-level `class`/`def`/
assignment of a reserved name binds it by definition and is the fork. Only
module-level definitions are flagged; a local of the same name is not a contract.

This is machinery, not the frozen contract: it is `EXCLUSIVE`, so the reserved set
can grow without moving the `CTR-WS@v1` frozen hash.
"""

from __future__ import annotations

import ast
from pathlib import Path

from contracts.prim import Redefinition, check_no_redefinition, scan_module

# The dead-man lease-semantics canon type names (`backend.deadman`, WP-2A-02). A
# `contracts`-tree module that defines any of these has forked the lease semantics
# out of their single home. Held as literals because the `contracts` tree may not
# import `backend/deadman` (`06` §5.6 contract join); the agreement between the WS
# transport and these canon types is proven separately, by test.
RESERVED_LEASE_SEMANTICS_SYMBOLS = frozenset(
    {
        "LeaseRenewal",
        "DeadmanLease",
        "RenewalDecision",
        "RenewalResult",
        "RearmHandshake",
        "ClientClockOffset",
    }
)


def _scan_lease_semantics(path: Path) -> list[Redefinition]:
    """Find lease-semantics canon names a module defines rather than transports.

    Args:
        path: Python file to scan (the WS schema, or a synthetic consumer).

    Returns:
        (list[Redefinition]) One entry per module-level definition of a reserved
            lease-semantics name, in source order.
    """
    hits: list[Redefinition] = []
    body = ast.parse(path.read_text(encoding="utf-8"), filename=str(path)).body
    for node in body:
        if isinstance(node, ast.ClassDef) and node.name in RESERVED_LEASE_SEMANTICS_SYMBOLS:
            hits.append(Redefinition(str(path), node.lineno, node.name, "class"))
        elif (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in RESERVED_LEASE_SEMANTICS_SYMBOLS
        ):
            hits.append(Redefinition(str(path), node.lineno, node.name, "def"))
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in RESERVED_LEASE_SEMANTICS_SYMBOLS:
                    hits.append(Redefinition(str(path), node.lineno, target.id, "assign"))
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id in RESERVED_LEASE_SEMANTICS_SYMBOLS
        ):
            hits.append(Redefinition(str(path), node.lineno, node.target.id, "assign"))
    return hits


def check_ws_no_redefinition(paths: list[Path]) -> list[Redefinition]:
    """Scan WS-consuming modules for primitive and lease-semantics redefinitions.

    Runs both bans: the shared `CTR-PRIM@v1` primitive scan, and the WS-specific
    lease-semantics scan. A clean transport imports its primitives and names the
    lease fields on the wire; it defines neither a primitive nor a canon lease type.

    Args:
        paths: Python files to scan.

    Returns:
        (list[Redefinition]) Every redefinition found, primitive and lease alike,
            in path then source order.
    """
    hits = list(check_no_redefinition(paths))
    for path in sorted(paths):
        hits.extend(_scan_lease_semantics(path))
    return hits


__all__ = [
    "RESERVED_LEASE_SEMANTICS_SYMBOLS",
    "Redefinition",
    "check_ws_no_redefinition",
    "scan_module",
]
