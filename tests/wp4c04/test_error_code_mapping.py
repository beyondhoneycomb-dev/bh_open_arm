"""CG-4C-04d — each tag maps to a 14 §2.10 error code or an explicit 'no code'."""

from __future__ import annotations

from backend.eval.taxonomy import (
    NO_CODE,
    TAG_ERROR_CODES,
    FailureTag,
    code_for_tag,
    has_registry_code,
)
from backend.inference.runaway import RUNAWAY_ERROR_CODE
from contracts.errors import REGISTRY
from contracts.errors.constants import CODE_PATTERN


def test_every_tag_is_mapped() -> None:
    """Every tag has an entry — no tag silently lacks a code decision."""
    assert set(TAG_ERROR_CODES) == set(FailureTag)


def test_every_mapping_is_a_registered_code_or_explicit_no_code() -> None:
    """Each value is either a frozen-registry code or the explicit NO_CODE sentinel."""
    for tag in FailureTag:
        code = code_for_tag(tag)
        assert code == NO_CODE or code in REGISTRY, f"{tag.name} -> {code}"


def test_no_code_sentinel_is_not_a_valid_registry_code() -> None:
    """NO_CODE is a deliberate non-code — it can never be mistaken for a real code."""
    assert NO_CODE not in REGISTRY
    assert CODE_PATTERN.match(NO_CODE) is None


def test_coded_tags_use_the_committed_codes() -> None:
    """The five coded tags resolve to the exact committed OA-* codes (reuse, not re-declare)."""
    assert code_for_tag(FailureTag.POLICY_OUT_OF_BOUNDS) == "OA-CTL-002"
    assert code_for_tag(FailureTag.POLICY_RUNAWAY) == RUNAWAY_ERROR_CODE == "OA-INF-003"
    assert code_for_tag(FailureTag.QUEUE_STARVATION) == "OA-INF-002"
    assert code_for_tag(FailureTag.REMOTE_DISCONNECT) == "OA-INF-001"
    assert code_for_tag(FailureTag.REMOTE_EMPTY_ACTION) == "OA-INF-002"


def test_uncoded_tags_declare_no_code() -> None:
    """Tags the frozen registry has no code for say so explicitly with NO_CODE."""
    for tag in (
        FailureTag.POLICY_INVALID_OUTPUT,
        FailureTag.SAFETY_STOP,
        FailureTag.COLLISION,
        FailureTag.TORQUE_LIMIT,
        FailureTag.POLICY_WRONG_ACTION,
        FailureTag.RESET_ERROR,
        FailureTag.TIMEOUT,
        FailureTag.AMBIGUOUS,
    ):
        assert not has_registry_code(tag)
        assert code_for_tag(tag) == NO_CODE
