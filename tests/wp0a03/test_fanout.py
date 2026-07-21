"""WP-0A-03 acceptance ④ — the fan-out width calculator.

④ On an overlap fixture the calculator returns `n=1`: a cohort that cannot be
   proven overlap-0 degrades to a single serial worker. A cohort whose globs are
   disjoint keeps its full width, and a declared handover is not an overlap, so
   a handover cohort keeps its width too.
"""

from __future__ import annotations

from ownership.prover import DEGRADED_FAN_OUT_WIDTH, assemble_claims, fan_out_width

FOLLOWER = "packages/lerobot_robot_openarm/openarm_follower_oa.py"
FOLLOWER_CHAIN = (("WP-1-02", "WP-1-03"),)


def test_overlapping_cohort_degrades_to_one() -> None:
    """Acceptance ④ — an overlap fixture returns n=1."""
    owners = {"backend/x/**": ("WP-A", "WP-B")}
    claims = assemble_claims(owners, ())
    assert fan_out_width(("WP-A", "WP-B"), claims, ("backend/x/mod.py",)) == DEGRADED_FAN_OUT_WIDTH


def test_disjoint_cohort_keeps_full_width() -> None:
    """A cohort whose globs never share a file fans out to its full size."""
    owners = {"pkg_a/**": ("WP-A",), "pkg_b/**": ("WP-B",)}
    claims = assemble_claims(owners, ())
    assert fan_out_width(("WP-A", "WP-B"), claims, ("pkg_a/x.py", "pkg_b/y.py")) == 2


def test_sequential_handover_cohort_keeps_full_width() -> None:
    """A handover is sequential, not concurrent, so the cohort is not degraded."""
    owners = {FOLLOWER: ("WP-1-02", "WP-1-03")}
    claims = assemble_claims(owners, FOLLOWER_CHAIN)
    assert fan_out_width(("WP-1-02", "WP-1-03"), claims, (FOLLOWER,)) == 2
