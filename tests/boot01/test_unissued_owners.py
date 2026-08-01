"""`06` §6 is the only place the corpus states ownership rather than citation.

`resolve` will not use a stated owner unless the catalogs issued it, because a record pointing at
a package that does not exist breaks the all-packages-registered gate. But failing that test drops
the requirement to `sole-citation` or `DEFERRED`, and the output of a misspelled work package is
byte-identical to the output of deleting the row: same rule, same owner, same gate count. So the
declaration is lost and the requirement acquires an owner the canon contradicts, which is the
failure §3.4a already surfaces for the id column.

`unissued_owners` is what makes the owner column's version of it visible.
"""

from __future__ import annotations

from pathlib import Path

from registry.ingest.catalog import CatalogEntry
from registry.ingest.resolve import DEFERRED, RULE_DOC06, RULE_SOLE, resolve, unissued_owners

_REQ = "FR-XXX-001"
_ISSUED_WP = "WP-1-03"
_OTHER_ISSUED_WP = "WP-1-02"
_UNISSUED_WP = "WP-9-99"

_SOURCE = Path("02b-작업패키지-Wave-2-3.md")
_SOURCE_LINE = 1


def _entry(wp_id: str, *reqs: str) -> CatalogEntry:
    """One issued work package citing the given requirements.

    Only `wp_id` and `reqs` decide ownership; the rest of the record is the raw catalog columns
    the resolver never reads.
    """
    return CatalogEntry(
        wp_id=wp_id,
        band=wp_id.split("-")[1],
        name="",
        source=_SOURCE,
        source_line=_SOURCE_LINE,
        reqs=reqs,
        consumes_text="",
        produces_text="",
        contract_text="",
        acceptance_text="",
        negative_text="",
        exec_classes=(),
        workflows=(),
    )


def test_an_issued_owner_is_reported_as_no_defect() -> None:
    entries = [_entry(_ISSUED_WP, _REQ), _entry(_OTHER_ISSUED_WP, _REQ)]

    assert unissued_owners(entries, {_REQ: _ISSUED_WP}) == []


def test_an_unissued_owner_is_reported_with_the_id_that_named_it() -> None:
    entries = [_entry(_ISSUED_WP, _REQ), _entry(_OTHER_ISSUED_WP, _REQ)]

    assert unissued_owners(entries, {_REQ: _UNISSUED_WP}) == [f"{_REQ} -> {_UNISSUED_WP}"]


def test_a_requirement_with_no_stated_owner_is_not_a_defect() -> None:
    """An absent assignment is the normal case, not a misspelling."""
    assert unissued_owners([_entry(_ISSUED_WP, _REQ)], {_REQ: ""}) == []


def test_an_unissued_owner_silently_demotes_the_assignment() -> None:
    """The consequence the report exists to make visible.

    Both calls resolve to the same rule and the same owner. Nothing in the assignment can tell
    a misspelled work package from a row that was never written, which is why the defect has to
    be collected separately rather than read off the result.
    """
    entries = [_entry(_ISSUED_WP, _REQ)]

    misspelled = resolve([_REQ], entries, {_REQ: _UNISSUED_WP})[_REQ]
    absent = resolve([_REQ], entries, {})[_REQ]

    assert misspelled.rule == absent.rule == RULE_SOLE
    assert misspelled.wp == absent.wp == _ISSUED_WP
    assert unissued_owners(entries, {_REQ: _UNISSUED_WP}) != unissued_owners(entries, {})


def test_the_demotion_reaches_deferred_when_citations_are_ambiguous() -> None:
    """With several citations and no usable declaration, the owner is lost outright."""
    entries = [_entry(_ISSUED_WP, _REQ), _entry(_OTHER_ISSUED_WP, _REQ)]

    assert resolve([_REQ], entries, {_REQ: _UNISSUED_WP})[_REQ].wp == DEFERRED
    assert resolve([_REQ], entries, {_REQ: _ISSUED_WP})[_REQ].rule == RULE_DOC06
