"""Render the BOOT band status page from whatever is actually on disk.

The page answers one question — may work packages start yet — because that is
the question the band exists to gate (`00` §3.5: not met means `FAIL_BLOCKING`
and nothing downstream may begin).

Absence and pass are rendered differently, everywhere. A checker that has not
run is not a checker that passed, and a page that draws them the same way
commits the failure the plan calls worse than having no rule at all.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

import yaml

from registry.checks import JUDGE_EXCLUDED

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = REPO_ROOT / "registry" / "traceability.yaml"
REPORT_PATH = REPO_ROOT / "registry" / "build" / "check-report.json"
RECONCILIATION_PATH = REPO_ROOT / "registry" / "build" / "reconciliation.md"
CHECKS_DIR = REPO_ROOT / "registry" / "checks"
OUTPUT_PATH = REPO_ROOT / "dashboard" / "index.html"

ISSUED_PACKAGE_COUNT = 177

# The rules `06` §5 declares. Two of these are easy to lose, and losing either
# breaks `WP-BOOT-03`'s contract, which forbids omitting a rule as strictly as
# it forbids inventing one:
#
# - `CI-16` has no row in the §5 table at all. It is declared in §5.6 as its
#   own prose subsection, so an implementer reading only the table misses it.
# - `CI-11b-자기적용` is a row in its own right, with its own name, not a
#   sub-clause of `CI-11b`. It requires running CI-11b over the real corpus and
#   proving both that the violation fixture fails and that the prose exceptions
#   pass — the checker that checks the checker.
#
# Which of them are judged is `JUDGE_EXCLUDED`, imported so this page and the
# checker cannot disagree. Two are excluded and both are still built and shown:
# CI-18 (its predicate references this gate) and CI-07 (it judges a Wave −1 hash
# that cannot exist at BOOT landing — see registry/checks/__init__.py).
CI_RULES = [
    "CI-01",
    "CI-01b",
    "CI-02",
    "CI-02b",
    "CI-03",
    "CI-03b",
    "CI-03c",
    "CI-03d",
    "CI-04",
    "CI-04b",
    "CI-04c",
    "CI-04d",
    "CI-05",
    "CI-05b",
    "CI-05c",
    "CI-05d",
    "CI-05e",
    "CI-06",
    "CI-07",
    "CI-08",
    "CI-09",
    "CI-10",
    "CI-11",
    "CI-11b",
    "CI-11b-자기적용",
    "CI-11c",
    "CI-12",
    "CI-13",
    "CI-14",
    "CI-14b",
    "CI-14c",
    "CI-15",
    "CI-16",
    "CI-17",
    "CI-18",
]

STATE_PASS = "pass"
STATE_FAIL = "fail"
STATE_ABSENT = "absent"


@dataclass(frozen=True)
class RuleStatus:
    """One CI rule's standing.

    Attributes:
        rule_id: Rule identifier from `06` §5.
        state: `pass`, `fail`, or `absent` — absent meaning no executable ran.
        detail: Short human-readable reason, empty when there is nothing to say.
        judged: Whether this rule counts toward the band acceptance gate.
    """

    rule_id: str
    state: str
    detail: str
    judged: bool


def _load_registry() -> dict[str, Any]:
    """Return the registry document, or an empty shell when it does not exist."""
    if not REGISTRY_PATH.exists():
        return {"entries": []}
    loaded: dict[str, Any] = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    return loaded


def _load_rule_statuses() -> list[RuleStatus]:
    """Determine each rule's state from the check report and the checker tree.

    Three states, never two. A rule whose executable is missing, or whose
    executable exists but never ran, is `absent` — not `pass`. Collapsing those
    into "green" is exactly how a rule comes to be trusted without being
    enforced.

    The report is written by `registry.check` on every run, and its `rules`
    entries are this page's only evidence that a rule executed. A missing report,
    or a report that omits a rule, is absent: the page never infers that a rule
    ran from the mere existence of a checker module next to it.
    """
    ran: dict[str, dict[str, Any]] = {}
    if REPORT_PATH.exists():
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        for entry in report.get("rules", []):
            rule_id = entry.get("rule_id", "")
            if rule_id:
                ran[rule_id] = entry

    statuses: list[RuleStatus] = []
    for rule_id in CI_RULES:
        entry = ran.get(rule_id)
        if entry is None:
            module = CHECKS_DIR / f"ci_{rule_id[3:].lower().replace('-', '_')}.py"
            state = STATE_ABSENT
            detail = "실행체 없음" if not module.exists() else "미실행"
        elif entry.get("findings"):
            state = STATE_FAIL
            detail = f"위반 {len(entry['findings'])}건"
        elif entry.get("vacuous"):
            # Green because it judged nothing is not the claim green because it
            # judged and found nothing. The strip cannot draw that difference,
            # so the label carries it.
            state = STATE_PASS
            detail = "판정 대상 0건 — 위반이 없는 게 아니라 볼 것이 없었다"
        else:
            state = STATE_PASS
            detail = f"판정 대상 {entry.get('sites', 0)}건"
        statuses.append(
            RuleStatus(
                rule_id=rule_id, state=state, detail=detail, judged=rule_id not in JUDGE_EXCLUDED
            )
        )
    return statuses


def _head_commit() -> str:
    """Return the short commit the page describes."""
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )
    return result.stdout.strip() or "unknown"


def _rule_marks(statuses: list[RuleStatus]) -> str:
    """Render the rule strip.

    The strip is the page's argument, not its ornament. Every rule in `06` §5
    gets one mark, so a gap is literally a rule with nothing enforcing it —
    the shape the plan warns about most: "rules with no executable are not
    discipline, they are hope".
    """
    marks = []
    for status in statuses:
        marks.append(
            f'<button class="mark mark--{status.state}" type="button" '
            f'aria-label="{escape(status.rule_id)}: '
            f'{escape(status.state)} {escape(status.detail)}">'
            f'<span class="mark__bar"></span>'
            f'<span class="mark__id">{escape(status.rule_id[3:])}</span>'
            f"</button>"
        )
    return "\n".join(marks)


def _readouts(document: dict[str, Any]) -> list[tuple[str, str, str, str]]:
    """Compute the instrument readouts: value, unit, label, state."""
    entries = document.get("entries", [])
    packages = len({entry["wp"] for entry in entries} - {"DEFERRED", "OUT"})
    deferred = sum(1 for entry in entries if entry["wp"] == "DEFERRED")
    return [
        (
            str(packages),
            f"/{ISSUED_PACKAGE_COUNT}",
            "작업 패키지 등재",
            STATE_PASS if packages == ISSUED_PACKAGE_COUNT else STATE_FAIL,
        ),
        (str(len(entries)), "", "레지스트리 레코드", STATE_PASS if entries else STATE_ABSENT),
        (str(deferred), "", "소유 WP 미배정", STATE_ABSENT if deferred else STATE_PASS),
    ]


def _verdict(statuses: list[RuleStatus], document: dict[str, Any]) -> tuple[str, str, str]:
    """Decide the headline verdict.

    Returns:
        (str) Three values: state token, headline, and the reason line.
    """
    entries = document.get("entries", [])
    packages = len({entry["wp"] for entry in entries} - {"DEFERRED", "OUT"})
    judged = [status for status in statuses if status.judged]
    failing = [status for status in judged if status.state == STATE_FAIL]
    unproven = [status for status in judged if status.state == STATE_ABSENT]

    if packages != ISSUED_PACKAGE_COUNT:
        return (
            STATE_FAIL,
            "착수 불가",
            f"조건 ① 미달 — 발급 {ISSUED_PACKAGE_COUNT}개 중 {packages}개만 등재됐다.",
        )
    if failing:
        names = ", ".join(status.rule_id for status in failing[:4])
        return STATE_FAIL, "착수 불가", f"조건 ② 미달 — {names} 위반."
    if unproven:
        return (
            STATE_ABSENT,
            "판정 보류",
            f"조건 ①은 통과했다. 조건 ②는 {len(unproven)}개 규칙이 아직 자기 코퍼스에서 "
            "돌지 않아 판정할 수 없다 — 통과가 아니라 미확인이다.",
        )
    return STATE_PASS, "착수 가능", "조건 ①·② 모두 충족. 하류 작업 패키지가 열린다."


def _reconciliation_findings() -> list[tuple[str, str]]:
    """Pull the defect section headings and counts out of the reconciliation report."""
    if not RECONCILIATION_PATH.exists():
        return []
    findings = []
    for line in RECONCILIATION_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("### 3.") and "—" in line:
            title, _, count = line[4:].rpartition("—")
            findings.append((title.strip(), count.strip()))
    return findings


def render(document: dict[str, Any], statuses: list[RuleStatus]) -> str:
    """Build the page body.

    Returns:
        (str) Complete HTML document.
    """
    state, headline, reason = _verdict(statuses, document)
    state_label = {"pass": "조건 충족", "fail": "FAIL_BLOCKING", "absent": "미확인"}[state]
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    readouts = "\n".join(
        f'<div class="readout readout--{item_state}">'
        f'<div class="readout__value">{escape(value)}'
        f'<span class="readout__unit">{escape(unit)}</span></div>'
        f'<div class="readout__label">{escape(label)}</div></div>'
        for value, unit, label, item_state in _readouts(document)
    )

    legend = "\n".join(
        f'<li class="legend__item"><span class="mark mark--{token} mark--static">'
        f'<span class="mark__bar"></span></span>{escape(text)}</li>'
        for token, text in (
            (STATE_PASS, "실행체가 있고, 위반 픽스처가 실제로 실패한다"),
            (STATE_FAIL, "돌았고, 위반을 잡았다"),
            (STATE_ABSENT, "돌지 않았다 — 통과가 아니라 미확인"),
        )
    )

    findings = _reconciliation_findings()
    findings_rows = (
        "\n".join(
            f"<tr><td>{escape(title)}</td><td class='num'>{escape(count)}</td></tr>"
            for title, count in findings
        )
        or "<tr><td colspan='2'>대조 리포트가 아직 생성되지 않았다.</td></tr>"
    )

    unproven = sum(1 for status in statuses if status.judged and status.state == STATE_ABSENT)
    judged_total = sum(1 for status in statuses if status.judged)

    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wave −2 BOOT — 대역 수용 상태</title>
<style>
:root {{
  --panel:  #1b1916;
  --panel2: #232019;
  --rule:   #3a352c;
  --bone:   #ece5d8;
  --steel:  #948c7d;
  --amber:  #e0a13c;
  --signal: #c8492f;
  --clear:  #7d9a72;
  --ink:    var(--bone);
  --bg:     var(--panel);
  --surface: var(--panel2);
  --mono: ui-monospace, "SF Mono", "Cascadia Mono", "Roboto Mono", Menlo, monospace;
  --sans: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Pretendard",
          "Noto Sans KR", "Malgun Gothic", system-ui, sans-serif;
}}
@media (prefers-color-scheme: light) {{
  :root {{ --bg:#e8e2d5; --surface:#f2ede2; --ink:#1b1916; --rule:#c9c0ad; --steel:#6d6558; }}
}}
:root[data-theme="dark"] {{
  --bg:var(--panel); --surface:var(--panel2); --ink:var(--bone); --rule:#3a352c; --steel:#948c7d;
}}
:root[data-theme="light"] {{
  --bg:#e8e2d5; --surface:#f2ede2; --ink:#1b1916; --rule:#c9c0ad; --steel:#6d6558;
}}
* {{ box-sizing: border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:var(--sans); line-height:1.62; -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:60rem; margin:0 auto; padding:clamp(1.25rem,4vw,3.5rem); }}
.eyebrow {{
  font-family:var(--mono); font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
  color:var(--steel); display:flex; gap:1.5rem; flex-wrap:wrap;
  border-bottom:1px solid var(--rule); padding-bottom:.9rem;
}}
.eyebrow span:first-child {{ color:var(--amber); }}

.verdict {{ padding:clamp(2rem,6vw,3.5rem) 0 clamp(1.5rem,4vw,2.5rem); }}
.verdict__state {{
  font-family:var(--mono); font-size:.7rem; letter-spacing:.22em; text-transform:uppercase;
  display:inline-flex; align-items:center; gap:.55rem; color:var(--steel); margin-bottom:1rem;
}}
.verdict__state::before {{
  content:""; width:.5rem; height:.5rem; border-radius:50%; background:currentColor;
}}
.verdict--pass .verdict__state {{ color:var(--clear); }}
.verdict--fail .verdict__state {{ color:var(--signal); }}
.verdict--absent .verdict__state {{ color:var(--amber); }}
.verdict__head {{
  font-family:var(--mono); font-weight:600;
  font-size:clamp(2.6rem,10vw,5.5rem); line-height:.95; letter-spacing:-.045em; margin:0;
}}
.verdict--pass .verdict__head {{ color:var(--clear); }}
.verdict--fail .verdict__head {{ color:var(--signal); }}
.verdict--absent .verdict__head {{ color:var(--amber); }}
.verdict__reason {{ margin:1.1rem 0 0; max-width:44rem; color:var(--ink); opacity:.86; }}

.readouts {{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(9rem,1fr));
  gap:1px; background:var(--rule); border:1px solid var(--rule); margin:0 0 2.75rem;
}}
.readout {{ background:var(--surface); padding:1.1rem 1.2rem; }}
.readout__value {{
  font-family:var(--mono); font-size:clamp(1.7rem,5vw,2.4rem);
  letter-spacing:-.03em; line-height:1;
}}
.readout--fail .readout__value {{ color:var(--signal); }}
.readout--absent .readout__value {{ color:var(--amber); }}
.readout__unit {{ font-size:.55em; color:var(--steel); letter-spacing:0; }}
.readout__label {{
  font-family:var(--mono); font-size:.65rem; letter-spacing:.16em; text-transform:uppercase;
  color:var(--steel); margin-top:.5rem;
}}

h2 {{
  font-family:var(--mono); font-size:.72rem; letter-spacing:.2em; text-transform:uppercase;
  color:var(--steel); font-weight:500;
  border-bottom:1px solid var(--rule); padding-bottom:.65rem; margin:0 0 1.25rem;
}}
section {{ margin-bottom:2.75rem; }}

.strip {{ display:flex; gap:2px; align-items:flex-end; overflow-x:auto; padding-bottom:.4rem; }}
.mark {{
  flex:1 0 auto; min-width:1.1rem; background:none; border:0; padding:0;
  display:flex; flex-direction:column; align-items:center; gap:.4rem;
  cursor:default; font:inherit; color:inherit;
}}
.mark__bar {{ display:block; width:100%; height:2.6rem; }}
.mark--pass   .mark__bar {{ background:var(--clear); }}
.mark--fail   .mark__bar {{ background:var(--signal); }}
.mark--absent .mark__bar {{
  background:repeating-linear-gradient(
    -45deg, transparent, transparent 3px, var(--rule) 3px, var(--rule) 4px);
  border:1px solid var(--rule);
}}
.mark__id {{
  font-family:var(--mono); font-size:.55rem; color:var(--steel); letter-spacing:.02em;
}}
.mark:focus-visible {{ outline:2px solid var(--amber); outline-offset:2px; }}
.mark--static {{ min-width:0; width:.85rem; display:inline-flex; vertical-align:middle; }}
.mark--static .mark__bar {{ height:.85rem; }}

.legend {{ list-style:none; padding:0; margin:1.4rem 0 0; display:grid; gap:.55rem; }}
.legend__item {{
  display:flex; align-items:center; gap:.7rem; font-size:.85rem; color:var(--ink); opacity:.8;
}}

.note {{
  border-left:2px solid var(--amber); padding:.15rem 0 .15rem 1rem;
  margin:1.4rem 0 0; color:var(--ink); opacity:.82; font-size:.9rem;
}}

.tablewrap {{ overflow-x:auto; }}
table {{ width:100%; border-collapse:collapse; font-size:.9rem; }}
th, td {{ text-align:left; padding:.7rem .5rem; border-bottom:1px solid var(--rule); }}
th {{
  font-family:var(--mono); font-size:.65rem; letter-spacing:.16em; text-transform:uppercase;
  color:var(--steel); font-weight:500;
}}
td.num {{ font-family:var(--mono); text-align:right; white-space:nowrap; color:var(--amber); }}

footer {{
  font-family:var(--mono); font-size:.65rem; letter-spacing:.1em; color:var(--steel);
  border-top:1px solid var(--rule); padding-top:1.1rem; margin-top:1rem;
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation:none !important; transition:none !important; }}
}}
</style>
</head>
<body>
<div class="wrap">
  <div class="eyebrow">
    <span>Wave −2 · BOOT</span>
    <span>대역 수용 게이트</span>
    <span>{escape(_head_commit())}</span>
    <span>{escape(stamp)}</span>
  </div>

  <div class="verdict verdict--{state}">
    <div class="verdict__state">{escape(state_label)}</div>
    <h1 class="verdict__head">{escape(headline)}</h1>
    <p class="verdict__reason">{escape(reason)}</p>
  </div>

  <div class="readouts">
{readouts}
  </div>

  <section>
    <h2>CI 규칙 {len(CI_RULES)}개 — 실행체 유무</h2>
    <div class="strip">
{_rule_marks(statuses)}
    </div>
    <ul class="legend">
{legend}
    </ul>
    <p class="note">
      판정 대상은 <strong>{judged_total}개 규칙</strong>이다. CI-18·CI-07은 짓되
      판정에는 넣지 않는다 — CI-18은 술어가 이 게이트를 참조해 자기참조가 되고,
      CI-07은 Wave −1이 발행하는 정규화 해시를 검사하는데 그 해시는 BOOT 착지
      시점엔 존재할 수 없다. 짓는 범위와 판정 범위가 다른 것은 의도다.
    </p>
  </section>

  <section>
    <h2>산문이 남긴 결함 — 사람이 고쳐야 하는 것</h2>
    <div class="tablewrap">
      <table>
        <thead><tr><th>항목</th><th style="text-align:right">건수</th></tr></thead>
        <tbody>
{findings_rows}
        </tbody>
      </table>
    </div>
  </section>

  <footer>
    미확인 {unproven}/{judged_total} · 이 페이지는 디스크의 실제 파일에서 생성된다 ·
    python -m dashboard.render
  </footer>
</div>
<script>
  // The rule strip is keyboard-reachable, so the detail must reach a screen
  // reader too: aria-label carries it, and title makes it visible on hover.
  for (const mark of document.querySelectorAll('.mark[aria-label]')) {{
    mark.title = mark.getAttribute('aria-label');
  }}
</script>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    """Render the status page.

    Returns:
        (int) 0 always — the page reports the verdict; it does not enforce it.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    args = parser.parse_args(argv)

    document = _load_registry()
    statuses = _load_rule_statuses()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render(document, statuses), encoding="utf-8")

    state, headline, _ = _verdict(statuses, document)
    print(f"{args.output.relative_to(REPO_ROOT)} — {headline} ({state})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
