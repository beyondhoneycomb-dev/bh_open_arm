"""WP-0A-03 acceptance ②③ — the overlap checker.

② Two work packages whose path_glob and ownership span overlap at once are
   rejected.
③ The `OpenArmFollower` subclass path is exclusive, and the `WP-1-02`/`WP-1-03`
   spans are adjacent but not overlapping: a both-active fixture is rejected, a
   sequential-handover fixture passes.

The two fixtures differ only in whether the handover chain is declared, which is
the whole distinction the rule turns on — concurrency is forbidden, sequence is
not.
"""

from __future__ import annotations

from ownership.prover import assemble_claims, concurrent_conflicts

FOLLOWER = "packages/lerobot_robot_openarm/openarm_follower_oa.py"
FOLLOWER_CHAIN = (("WP-1-02", "WP-1-03"),)

_UNCHAINED_GLOB = "backend/x/**"
_UNCHAINED_FILE = "backend/x/mod.py"


def test_two_packages_sharing_a_glob_with_no_handover_are_rejected() -> None:
    """Acceptance ② — overlapping glob and span with no declared handover."""
    owners = {_UNCHAINED_GLOB: ("WP-A", "WP-B")}
    claims = assemble_claims(owners, ())
    conflicts = concurrent_conflicts(claims, (_UNCHAINED_FILE,))
    assert conflicts
    assert conflicts[0].shared_paths == (_UNCHAINED_FILE,)
    assert {conflicts[0].left_wp, conflicts[0].right_wp} == {"WP-A", "WP-B"}


def test_both_active_on_the_follower_subclass_is_rejected() -> None:
    """Acceptance ③ — WP-1-02 and WP-1-03 active at once (no handover) conflict."""
    owners = {FOLLOWER: ("WP-1-02", "WP-1-03")}
    claims = assemble_claims(owners, ())
    conflicts = concurrent_conflicts(claims, (FOLLOWER,))
    assert conflicts
    assert conflicts[0].shared_paths == (FOLLOWER,)


def test_sequential_handover_on_the_follower_subclass_passes() -> None:
    """Acceptance ③ — the same pair, now a declared handover, does not conflict."""
    owners = {FOLLOWER: ("WP-1-02", "WP-1-03")}
    claims = assemble_claims(owners, FOLLOWER_CHAIN)
    assert concurrent_conflicts(claims, (FOLLOWER,)) == ()


def test_follower_spans_are_exclusive_adjacent_and_non_overlapping() -> None:
    """Acceptance ③ — exclusive=true, spans adjacent but not overlapping."""
    owners = {FOLLOWER: ("WP-1-02", "WP-1-03")}
    claims = assemble_claims(owners, FOLLOWER_CHAIN)
    by_wp = {claim.owner_wp: claim for claim in claims}

    assert by_wp["WP-1-02"].exclusive
    assert by_wp["WP-1-03"].exclusive

    first, second = by_wp["WP-1-02"].span, by_wp["WP-1-03"].span
    assert not first.overlaps(second)
    assert first.end == second.start
