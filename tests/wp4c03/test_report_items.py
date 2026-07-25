"""CG-4C-03g — the report carries all FR-SIM-058 (6) + NFR-PRF-050 (4) items.

`02c` §3.3 인터페이스 계약: the report holds the union of `FR-SIM-058`'s six items
and `NFR-PRF-050`'s four. The two lists are checked separately (not merely their
union) so each requirement's own coverage is proven.
"""

from __future__ import annotations

from backend.eval.stats import FR_SIM_058_ITEMS, NFR_PRF_050_ITEMS
from tests.wp4c03.support import report

# The Korean report labels each required item renders as, so "present in the report"
# is checked at the rendered surface as well as in the structured item map.
_ITEM_RENDER_LABELS = (
    "점추정 성공률",
    "Wilson 95% CI",
    "에피소드 길이 중앙값",
    "충돌 횟수",
    "토크 한계 도달 횟수",
    "안전정지 발동 횟수",
    "추론 지연 p95",
)

_FR_SIM_058_COUNT = 6
_NFR_PRF_050_COUNT = 4


def test_item_list_sizes_match_the_spec() -> None:
    """FR-SIM-058 declares 6 items, NFR-PRF-050 declares 4."""
    assert len(FR_SIM_058_ITEMS) == _FR_SIM_058_COUNT
    assert len(NFR_PRF_050_ITEMS) == _NFR_PRF_050_COUNT


def test_nfr_prf_050_items_are_a_subset_of_fr_sim_058() -> None:
    """NFR-PRF-050's four co-recorded metrics are a subset of FR-SIM-058's six."""
    assert set(NFR_PRF_050_ITEMS) <= set(FR_SIM_058_ITEMS)


def test_report_contains_every_fr_sim_058_item() -> None:
    """CG-4C-03g: all six FR-SIM-058 items are present in the report."""
    values = report(n_success=10, n_trials=20).item_values()
    for item in FR_SIM_058_ITEMS:
        assert item in values


def test_report_contains_every_nfr_prf_050_item() -> None:
    """CG-4C-03g: all four NFR-PRF-050 items are present in the report."""
    values = report(n_success=10, n_trials=20).item_values()
    for item in NFR_PRF_050_ITEMS:
        assert item in values


def test_report_has_no_missing_items() -> None:
    """The structural completeness check reports nothing missing."""
    assert report(n_success=10, n_trials=20).missing_items() == ()


def test_render_shows_every_item_label() -> None:
    """Every required item appears on the rendered report surface (CG-4C-03g)."""
    rendered = report(n_success=10, n_trials=20).render()
    for label in _ITEM_RENDER_LABELS:
        assert label in rendered
