"""The regression checker: drift fires per contract, and CTR-PRIM staleness propagates.

`02b` §5.2 WP-3A-06 ②: the checker must fail on a hash mismatch of any of the six
frozen contracts, and a `CTR-PRIM@v1` change must mark all five consumers STALE. The
real-tree run proves it passes when nothing drifted; the scratch-tree runs prove the
two failure modes actually fire — a checker that only ever passed would be a forge.

The scratch corpus mirrors the six-contract shape (one primitive, five consumers of
it) with tiny bodies, so the proof exercises the checker's logic, not the real bytes.
The locked hash is always the *clean* body's hash, registered before any mutation, so
a mutated body is a genuine drift off a committed lock.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.fixtures.contract_regression import check_contract_regression, check_repo
from registry.checks import ci_09
from registry.checks.fixtures import corpus, record

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY_REL = "registry/contracts/contract_index.json"

PRIMITIVE = "CTR-PRIM@v1"
# The five consumer contracts and the producing work package of each, so the scratch
# corpus reproduces the real consumes/produces axes the checker derives staleness from.
CONSUMERS = {
    "CTR-CAM@v1": "WP-3A-01",
    "CTR-CAP@v1": "WP-3A-02",
    "CTR-TEL@v1": "WP-3A-03",
    "CTR-WS@v1": "WP-3A-04",
    "CTR-REC@v1": "WP-3A-05",
}
ALL_SIX = (PRIMITIVE, *sorted(CONSUMERS))


def _glob_for(contract_id: str) -> str:
    """The scratch frozen-glob path for a contract id."""
    stem = contract_id.split("@", 1)[0].lower().replace("-", "_")
    return f"contracts/{stem}/schema.json"


def _scratch(root: Path, mutate: frozenset[str]) -> tuple[object, Path]:
    """Build a six-contract scratch corpus, mutating the named bodies after locking.

    Args:
        root: Scratch repository root.
        mutate: Contract ids whose on-disk body is perturbed after its lock is set.

    Returns:
        (tuple[object, Path]) The corpus to check and the scratch authority path.
    """
    records = []
    tracked: list[str] = []
    locked_rows: list[dict[str, object]] = []
    for contract_id in ALL_SIX:
        glob = _glob_for(contract_id)
        tracked.append(glob)
        path = root / glob
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"clean body of {contract_id}\n", encoding="utf-8")
        locked_rows.append(
            {
                "contract_id": contract_id,
                "canonical_hash": ci_09.content_hash((glob,), root),
                "status": "FROZEN",
            }
        )
        wp = "WP-3A-00" if contract_id == PRIMITIVE else CONSUMERS[contract_id]
        consumes = [] if contract_id == PRIMITIVE else [PRIMITIVE]
        records.append(
            record(
                wp=wp,
                contract={"consumes": consumes, "produces": [contract_id]},
                owns=[{"glob": glob, "mode": "CONTRACT_FROZEN"}],
            )
        )

    for contract_id in mutate:
        (root / _glob_for(contract_id)).write_text(
            f"clean body of {contract_id}\nDRIFT\n", encoding="utf-8"
        )

    (root / "registry" / "contracts").mkdir(parents=True, exist_ok=True)
    authority = root / AUTHORITY_REL
    authority.write_text(json.dumps({"contracts": locked_rows}), encoding="utf-8")
    built = corpus(tuple(records), root=root, tracked_files=tuple(sorted(tracked)))
    return built, authority


def test_real_repo_is_clean() -> None:
    """Against the freshly frozen tree the checker passes with no mismatch or stale set."""
    report = check_repo(REPO_ROOT)
    assert report.ok, report.summary()
    assert report.mismatches == ()
    assert report.stale == ()
    assert set(report.checked) == set(ALL_SIX)


def test_clean_scratch_passes(tmp_path: Path) -> None:
    """With no mutation, every locked hash matches its body and the run is green."""
    built, authority = _scratch(tmp_path, frozenset())
    report = check_contract_regression(built, authority)
    assert report.ok, report.summary()
    assert report.mismatches == ()
    assert report.stale == ()


def test_drift_fires_for_each_of_the_six(tmp_path: Path) -> None:
    """Mutating any one contract's body makes exactly that contract a mismatch."""
    for contract_id in ALL_SIX:
        root = tmp_path / contract_id.split("@", 1)[0]
        built, authority = _scratch(root, frozenset({contract_id}))
        report = check_contract_regression(built, authority)
        assert not report.ok, f"{contract_id} drifted but the checker stayed green"
        assert contract_id in report.mismatches, f"{contract_id} drift was not detected"


def test_ctr_prim_change_marks_all_five_consumers_stale(tmp_path: Path) -> None:
    """A CTR-PRIM@v1 body change flags every consumer stale, even bytes-unchanged ones."""
    built, authority = _scratch(tmp_path, frozenset({PRIMITIVE}))
    report = check_contract_regression(built, authority)
    assert PRIMITIVE in report.mismatches
    assert set(report.stale) == set(CONSUMERS), report.summary()
    # The consumers' own bodies did not move: they are stale by propagation, not drift.
    assert not set(report.mismatches) & set(CONSUMERS)


def test_a_consumer_change_does_not_stale_its_siblings(tmp_path: Path) -> None:
    """A lone consumer drift is a mismatch but triggers no stale propagation."""
    built, authority = _scratch(tmp_path, frozenset({"CTR-CAM@v1"}))
    report = check_contract_regression(built, authority)
    assert report.mismatches == ("CTR-CAM@v1",)
    assert report.stale == (), "a consumer change must not stale its siblings; only CTR-PRIM does"


def test_lock_is_read_from_the_authority_not_recomputed(tmp_path: Path) -> None:
    """A wrong hash in the authority fires even when the body is untouched — no self-hash."""
    built, authority = _scratch(tmp_path, frozenset())
    doctored = json.loads(authority.read_text(encoding="utf-8"))
    for row in doctored["contracts"]:
        if row["contract_id"] == "CTR-WS@v1":
            row["canonical_hash"] = "sha256:" + "0" * 64
    authority.write_text(json.dumps(doctored), encoding="utf-8")
    report = check_contract_regression(built, authority)
    assert "CTR-WS@v1" in report.mismatches, "the checker recomputed the lock instead of reading it"
