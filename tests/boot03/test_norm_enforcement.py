"""NORM-006 and NORM-007 enforcement, and the two ways it could be worthless.

Half of these tests assert what the check finds; the other half assert what it leaves
alone. Only the second half is load-bearing. A check that banned `전원 차단` outright
would score full marks on every positive test here and would then report FR-GUI-064's
standing drop warning and FR-GUI-093's process-death hazard as violations — at which
point the cheapest way to clear the gate is to delete two safety warnings. So the
repaired-specification fixture keeps that text verbatim and demands silence over it.

The corpus is red today. `test_the_repository_is_still_red` records the exact findings,
and the doctored fixtures prove the same code reports nothing once the documents are
repaired, which is the evidence that the redness lives in the documents rather than in
the checker.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from registry import NORMALIZATION_SUBPATH, PLAN_SUBPATH, SPEC_SUBPATH
from registry.checks.corpus import Corpus
from registry.checks.norm_enforcement import (
    KIND_VACUOUS,
    SCAN_ANCHORS,
    check_norm_006,
    check_norm_007,
    reachability_clause,
    scanned_frontend_files,
    strip_comments,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

GUI_SPEC_NAME = "13-GUI-화면-명세.md"

PORT_MANIFEST = """### 2.7 네트워크 경계 · 포트 매니페스트

| 경계 | 프로토콜/포트 | 나르는 것 |
|---|---|---|
| 브라우저 ↔ 백엔드 | WebSocket :8000 | 텔레옵 명령 + 텔레메트리 |
| 백엔드 ↔ 원격 추론 | gRPC :8080 | async PolicyServer↔RobotClient |
| 카메라 장치 → 백엔드 | USB/CSI | raw 프레임 grab |
"""

RELAY_BOUNDARY_ROW = "| 안전 릴레이 ↔ 백엔드 | GPIO | 모터 전원 라인 차단 |\n"

# The `13` requirement cells as they read once both rulings are carried out. FR-GUI-064,
# FR-GUI-093 and the closing clause of FR-GUI-111 are quoted from the live document
# unchanged: the ledger ruled them surviving, and a check that reports them has inverted
# its own purpose.
REPAIRED_REQUIREMENTS = """### 3.5 안전 · 정지

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-060 | GUI는 제어권·모드·연결 상태를 상시 배지로 표시해야 한다. | M | §2.6 | [확정] |
| FR-GUI-063 | GUI는 소프트 스톱(STOP_HOLD) 컨트롤과 전원라인 물리 버튼 안내 패널을 \
시각·경로 모두 분리해 제공해야 한다. | M | §2.6 | [확정] |
| FR-GUI-064 | GUI는 하드 E-Stop 안내 패널 근처에 "전원 차단 시 파지 중인 물체가 낙하한다" \
경고를 상시 표시해야 한다. | M | §2.6 | [확정] |
| FR-GUI-065 | STOP_HOLD 컨트롤은 모든 화면·모든 모드·제어권 보유 여부와 무관하게 항상 \
접근 가능해야 한다. | M | §2.6 | [확정] |
| FR-GUI-067 | GUI는 단축키를 제공하고 매핑을 조회·재정의할 수 있어야 한다. 최소: \
STOP_HOLD, 에피소드 start/success/fail/cancel, 모드 전환. | M | §2.6 | [확정] |
| FR-GUI-093 | 프로세스 사망이나 CAN bus-off = 낙하다. 실패안전은 기계적 지지·낙하영역 \
격리·독립 전원차단 회로로만 성립한다. | M | `12` §2.3 | [확정] |

### 3.8 충돌 · 안전

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-111 | S-12 충돌·안전은 가상벽/금지영역을 3D 뷰포트에서 직접 편집하고 충돌 반응 \
정책(소프트 스톱 / 속도 스케일 하향)을 선택할 수 있어야 하며, 충돌 감지의 기본 반응이 \
전원 차단이어서는 안 된다. | M | `12` FR-SAF-037 | [확정] |

### 3.9 성능

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| NFR-GUI-005 | STOP_HOLD 명령의 왕복 지연 상한(브라우저 입력 → WS → 백엔드 적용)을 \
정의하고 초과 시 경고해야 한다. | M | §2.6 | [확정] |
"""


def _doctored(tmp_path: Path, body: str) -> Corpus:
    """Build a corpus whose `13` is replaced and whose everything else is real.

    The ledger, the `02d` catalogue and the frontend tree stay the live ones, so a
    fixture only has to state the document under test.

    Args:
        tmp_path: Per-test temporary directory.
        body: Markdown body of the substitute `13`.

    Returns:
        (Corpus) A corpus reading the substitute document.
    """
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / GUI_SPEC_NAME).write_text(body, encoding="utf-8")
    return Corpus(REPO_ROOT, spec_dir=spec_dir, plan_dir=REPO_ROOT / PLAN_SUBPATH)


def _frontend_root(tmp_path: Path, sources: dict[str, str]) -> Corpus:
    """Build a corpus rooted on a synthetic frontend tree.

    The ledger is copied so the NORM-007 sample gates read a real row; the spec and plan
    directories point back at the live corpus so only the frontend is substituted.

    Args:
        tmp_path: Per-test temporary directory.
        sources: Repo-relative path to file contents.

    Returns:
        (Corpus) A corpus whose `frontend/src` is the given tree.
    """
    root = tmp_path / "root"
    ledger = root / NORMALIZATION_SUBPATH / "ledger.yaml"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(REPO_ROOT / NORMALIZATION_SUBPATH / "ledger.yaml", ledger)
    for relative, text in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return Corpus(root, spec_dir=REPO_ROOT / SPEC_SUBPATH, plan_dir=REPO_ROOT / PLAN_SUBPATH)


@pytest.fixture(scope="module")
def live() -> Corpus:
    """Return the live repository corpus."""
    return Corpus(REPO_ROOT)


def test_the_repository_is_still_red(live: Corpus) -> None:
    """Both rulings are unenforced in the documents, at these exact cells.

    Written as an inventory rather than a bare count so that repairing one cell changes
    this list and repairing the wrong one does not.
    """
    reported = {
        (violation.norm_id, violation.kind, violation.detail.split(" ")[0])
        for violation in check_norm_006(live) + check_norm_007(live)
    }
    spec = "docs/v1/spec/13-GUI-화면-명세.md"
    catalog = "docs/v1/plan/02d-작업패키지-GUI.md:125"
    assert reported == {
        ("NORM-006", "ambiguous-stop-word", f"{spec}:232"),
        ("NORM-006", "ambiguous-stop-word", f"{spec}:234"),
        ("NORM-006", "ambiguous-stop-word", f"{spec}:326"),
        ("NORM-006", "ambiguous-stop-word", catalog),
        ("NORM-006", "unfixed-reachability-subject", catalog),
        ("NORM-007", "discarded-reading-alive", f"{spec}:227"),
        ("NORM-007", "discarded-reading-alive", f"{spec}:230"),
        ("NORM-007", "discarded-reading-alive", f"{spec}:287"),
        ("NORM-007", "power-cut-policy-option", f"{spec}:287"),
    }


def test_a_repaired_specification_clears_both_rulings(tmp_path: Path) -> None:
    """The surviving safety text is not a violation, and never becomes one.

    This fixture keeps FR-GUI-064's drop warning, FR-GUI-093's process-death hazard and
    FR-GUI-111's "the default reaction must not be a power cut" clause verbatim. All
    three say `전원 차단`. Silence over them is the whole difference between enforcing
    NORM-007 and deleting the warnings it was written to protect.
    """
    corpus = _doctored(tmp_path, PORT_MANIFEST + REPAIRED_REQUIREMENTS)
    spec_findings = [
        violation
        for violation in check_norm_007(corpus)
        if "13-GUI" in violation.detail or violation.kind == KIND_VACUOUS
    ]
    assert spec_findings == []
    assert [v for v in check_norm_006(corpus) if "13-GUI" in v.detail] == []


def test_boundary_hardware_is_reported_only_while_the_manifest_omits_it(tmp_path: Path) -> None:
    """The gate is bound to `13` §2.7, not to a fixed list of forbidden words.

    A requirement assuming a relay is a violation today because the port manifest lists
    no relay. Add the row and the same requirement stops being one — the check goes quiet
    because the hardware changed, which is the only reason it should ever go quiet.
    """
    assumes_relay = REPAIRED_REQUIREMENTS.replace(
        "| FR-GUI-060 | GUI는 제어권·모드·연결 상태를 상시 배지로 표시해야 한다.",
        "| FR-GUI-060 | GUI는 안전 릴레이 개폐 상태를 상시 배지로 표시해야 한다.",
    )

    without_row = _doctored(tmp_path / "a", PORT_MANIFEST + assumes_relay)
    reported = [v for v in check_norm_007(without_row) if v.kind == "unlisted-boundary"]
    assert len(reported) == 1
    assert "FR-GUI-060" in reported[0].detail
    assert "릴레이" in reported[0].detail

    with_row = _doctored(tmp_path / "b", PORT_MANIFEST + RELAY_BOUNDARY_ROW + assumes_relay)
    assert [v for v in check_norm_007(with_row) if v.kind == "unlisted-boundary"] == []


def test_a_hard_estop_returned_to_the_policy_is_reported(tmp_path: Path) -> None:
    """FR-GUI-111 may not offer a power cut as a selectable collision reaction."""
    restored = REPAIRED_REQUIREMENTS.replace(
        "정책(소프트 스톱 / 속도 스케일 하향)", "정책(소프트 스톱 / 속도 스케일 하향 / 하드 E-Stop)"
    )
    corpus = _doctored(tmp_path, PORT_MANIFEST + restored)
    reported = [v for v in check_norm_007(corpus) if v.kind == "power-cut-policy-option"]
    assert len(reported) == 1
    assert "FR-GUI-111" in reported[0].detail


def test_the_retired_word_returning_to_a_cell_is_reported(tmp_path: Path) -> None:
    """A single reintroduction of `비상정지` into a requirement cell fails the gate."""
    reverted = REPAIRED_REQUIREMENTS.replace(
        "| FR-GUI-065 | STOP_HOLD 컨트롤은", "| FR-GUI-065 | 비상정지 컨트롤은"
    )
    corpus = _doctored(tmp_path, PORT_MANIFEST + reverted)
    reported = [
        v
        for v in check_norm_006(corpus)
        if v.kind == "ambiguous-stop-word" and "13-GUI" in v.detail
    ]
    assert len(reported) == 1
    assert "FR-GUI-065" in reported[0].detail


def test_the_reachability_clause_ends_at_the_next_acceptance_id() -> None:
    """A `STOP_HOLD` belonging to a later check must not answer for `CG-G-03b`.

    The `02d` acceptance column is one paragraph listing every `CG-G-03*` check, so a
    clause read to the end of the cell borrows every identifier that follows it.
    """
    borrowed = "① CG-G-03a 두 컨트롤 분리 ② CG-G-03b 전 조합 접근 가능 ③ CG-G-03c STOP_HOLD 경로"
    assert reachability_clause(borrowed) == "CG-G-03b 전 조합 접근 가능 ③ "

    fixed = "② CG-G-03b 전 조합에서 STOP_HOLD 접근 가능 ③ CG-G-03c 정적 검사"
    clause = reachability_clause(fixed)
    assert clause is not None
    assert "STOP_HOLD" in clause

    assert reachability_clause("① CG-G-03a 두 컨트롤 분리") is None


def test_an_empty_requirement_sample_is_a_violation_not_a_pass(tmp_path: Path) -> None:
    """A `13` the parser cannot read is a broken checker, not a satisfied rule."""
    corpus = _doctored(tmp_path, PORT_MANIFEST)
    assert [v.kind for v in check_norm_006(corpus) if v.kind == KIND_VACUOUS] == [KIND_VACUOUS]
    assert KIND_VACUOUS in {v.kind for v in check_norm_007(corpus)}


def test_a_missing_port_manifest_is_a_violation_not_a_pass(tmp_path: Path) -> None:
    """Without the manifest there is no evidence of which boundaries are absent."""
    corpus = _doctored(tmp_path, REPAIRED_REQUIREMENTS)
    vacuous = [v for v in check_norm_007(corpus) if v.kind == KIND_VACUOUS]
    assert len(vacuous) == 1
    assert "port manifest" in vacuous[0].detail


def test_the_frontend_scan_reaches_the_files_a_regression_lands_in(live: Corpus) -> None:
    """Counting files proves nothing; a path typo walks an empty tree and reports green."""
    scanned = {live.rel(path) for path in scanned_frontend_files(live)}
    assert set(SCAN_ANCHORS) <= scanned
    assert not [v for v in check_norm_007(live) if v.kind == KIND_VACUOUS]


def test_the_power_off_reaction_mode_is_not_a_target(live: Corpus) -> None:
    """`POWER_CUT_REACTION_MODE` is a CAN torque cut (`12` §2.10), not a contactor.

    It sits in a scanned file and names a power cut in both its identifier and its value.
    Reporting it would ban the one place the collision policy is allowed to say the word.
    """
    reactive = (REPO_ROOT / "frontend/src/screens/S-12/reactionPolicy.ts").read_text(
        encoding="utf-8"
    )
    assert "POWER_CUT_REACTION_MODE" in reactive
    assert not [v for v in check_norm_007(live) if v.kind == "power-cut-actuation-symbol"]


def test_a_power_cut_handler_in_the_frontend_is_reported(tmp_path: Path) -> None:
    """A prop that reaches a power cut is the regression NORM-007 exists to catch."""
    corpus = _frontend_root(
        tmp_path,
        {
            SCAN_ANCHORS[0]: "export interface P {\n  onPowerCut: () => void;\n}\n",
            SCAN_ANCHORS[1]: 'export const MODE = "POWER_OFF";\n',
        },
    )
    reported = [v for v in check_norm_007(corpus) if v.kind == "power-cut-actuation-symbol"]
    assert len(reported) == 1
    assert reported[0].detail.startswith(f"{SCAN_ANCHORS[0]}:2 ")
    assert "'onPowerCut'" in reported[0].detail


def test_a_commented_symbol_is_not_a_finding_and_lines_do_not_shift(tmp_path: Path) -> None:
    """Comments explain the ban; they are not the ban's target.

    Block comments blank out to their own newlines rather than to nothing, so the line
    number a finding cites still points at the offending line.
    """
    source = "/* naming\n   onPowerCut\n*/\nconst url = 'https://x'; // onPowerCut\nonPowerCut();\n"
    assert strip_comments(source).count("\n") == source.count("\n")

    corpus = _frontend_root(
        tmp_path, {SCAN_ANCHORS[0]: source, SCAN_ANCHORS[1]: "export const M = 1;\n"}
    )
    reported = [v for v in check_norm_007(corpus) if v.kind == "power-cut-actuation-symbol"]
    assert len(reported) == 1
    assert reported[0].detail.startswith(f"{SCAN_ANCHORS[0]}:5 ")


def test_test_files_are_not_scanned(live: Corpus) -> None:
    """`staticChecks.test.ts` asserts the banned symbols are absent, by writing them."""
    scanned = {live.rel(path) for path in scanned_frontend_files(live)}
    assert "frontend/src/global/staticChecks.test.ts" not in scanned
