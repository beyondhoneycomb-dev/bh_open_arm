"""Static proof that no production path promotes itself to a real-time scheduler (NORM-014).

`13` NFR-GUI-008 asked for the control-loop thread to be `SCHED_FIFO` + `mlockall`. The Wave -1
ruling NORM-014 discarded that clause: promotion needs root, a priority inversion can wedge the
whole box, and while the GIL is the bottleneck it buys nothing. The other three clauses of
NFR-GUI-008 stand — control loop separated from WS/encoding, encoding never blocking the control
loop, cycle time measured continuously — and those are where jitter is actually visible.

The scan is AST-based rather than textual because the predicate is about *calls*. `13` §3.9's own
S-13 screen reports whether a process is RT-scheduled, and the load report names the policy in
prose; naming a policy is not requesting one. An `ast.Constant` holding "SCHED_FIFO" is display
text, while `os.SCHED_FIFO` reaching a `sched_setscheduler` call is the thing NORM-014 forbids.

`roots` and `exclude` are parameters, not constants, because the ruling is scoped to the shipped
control path and not to the whole tree. `sim/harness/rt_promotion.py` promotes on purpose: it is
WP-0C-06's experiment for `15` §2.10 condition 6, and `NFR-PRF-040` — still 확정, untouched by
this ruling — requires publishing the measured result that promotion does not help. A scan that
reached it would delete the evidence for the very claim NORM-014 rests on.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# The libc/os entry points that actually perform promotion or page locking. Naming one of these is
# how a Python process requests real-time scheduling; there is no other route from this codebase.
RT_PROMOTION_CALLS = ("sched_setscheduler", "sched_setparam", "mlockall")

# Scheduler policy attributes. Reached as `os.SCHED_FIFO`, these are the argument a promotion call
# takes; as a bare string they are display text, which the AST keeps distinguishable.
RT_POLICY_ATTRIBUTES = ("SCHED_FIFO", "SCHED_RR")

PYTHON_GLOB = "*.py"


@dataclass(frozen=True)
class RtPromotionSite:
    """One real-time promotion request found on a production path (NORM-014).

    Attributes:
        path: The file the request was found in.
        line: One-based line number.
        symbol: The call or policy attribute that made it a request.
    """

    path: Path
    line: int
    symbol: str


def scan_rt_promotion(roots: tuple[Path, ...], exclude: tuple[Path, ...]) -> list[RtPromotionSite]:
    """Scan production Python sources for real-time promotion requests; the count must be zero.

    Args:
        roots: Directories to scan recursively for `*.py`. Pass the shipped control path, not the
            whole tree — the measurement harness promotes deliberately under WP-0C-06.
        exclude: Paths (files or directories) whose matches are a definition, a fixture, or this
            checker itself rather than a production request.

    Returns:
        (list[RtPromotionSite]) Every promotion request found, empty when clean.

    Raises:
        SyntaxError: If a scanned file does not parse. A file the checker cannot read is not
            silently skipped: an unparsed file is an unscanned file, and the count would be a
            lower bound presented as a total.
    """
    sites: list[RtPromotionSite] = []
    for root in roots:
        if not root.exists():
            continue
        for path in sorted(root.rglob(PYTHON_GLOB)):
            if _is_excluded(path, exclude):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            sites.extend(_sites_in(tree, path))
    return sites


def _sites_in(tree: ast.AST, path: Path) -> list[RtPromotionSite]:
    """Return the promotion requests in one parsed module."""
    sites: list[RtPromotionSite] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            called = _called_name(node.func)
            if called in RT_PROMOTION_CALLS:
                sites.append(RtPromotionSite(path=path, line=node.lineno, symbol=called))
        elif isinstance(node, ast.Attribute) and node.attr in RT_POLICY_ATTRIBUTES:
            sites.append(RtPromotionSite(path=path, line=node.lineno, symbol=node.attr))
    return sites


def _called_name(func: ast.expr) -> str:
    """Return the bare name a call expression resolves to, or empty when it is not a plain name.

    Both `os.sched_setscheduler(...)` and a `from os import sched_setscheduler` call reduce to the
    same name here, so an import style cannot hide a promotion.
    """
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_excluded(path: Path, exclude: tuple[Path, ...]) -> bool:
    """Report whether a path is one of, or under, the excluded paths."""
    resolved = path.resolve()
    for excluded in exclude:
        target = excluded.resolve()
        if resolved == target or target in resolved.parents:
            return True
    return False
