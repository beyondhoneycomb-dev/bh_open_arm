"""Emit the registry document and the prose-to-registry reconciliation report.

The Korean text in `_render_report` is report *content*, not commentary: it is
the body of a document written for the same readers as `docs/plan/`, which is
Korean throughout. The English-comments rule governs what the code says about
itself, and every comment and docstring here is English. Translating the report
body would leave the reconciliation output in a different language from the
corpus it reconciles.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from registry.ingest.build import build
from registry.ingest.resolve import RULE_AMBIGUOUS, RULE_COVERAGE, RULE_DOC06, RULE_SOLE

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = REPO_ROOT / "registry" / "traceability.yaml"
SCHEMA_PATH = REPO_ROOT / "registry" / "schema" / "traceability.schema.json"
REPORT_PATH = REPO_ROOT / "registry" / "build" / "reconciliation.md"
SPINE_DOC = "docs/plan/00-실행계획-개요.md"


class _NoAliasDumper(yaml.SafeDumper):
    """Dump every record in full rather than emitting YAML anchors.

    Work-package-level axes are shared objects across the records of one
    package, and the default dumper collapses the repeats into `&id/*id`
    references. That is valid YAML, but it makes the registry unreadable as a
    diff — a change to one package's gate list would rewrite an anchor far from
    the record being changed — and every non-Python consumer would have to
    resolve aliases to read a single entry.
    """

    def ignore_aliases(self, data: Any) -> bool:  # noqa: ARG002 — PyYAML's override signature
        """Never emit an alias."""
        return True


def _head_commit() -> str:
    """Return the short commit the registry is being seeded from."""
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=REPO_ROOT,
    ).stdout.strip()


def _render_report(document: dict[str, Any], report: Any, errors: list[str]) -> str:
    """Render the reconciliation report.

    The report exists because the registry is seeded from prose exactly once.
    It states what was derived, by which rule, and — more importantly — what
    the corpus does not say, so that the gaps stay visible instead of being
    absorbed into a document that looks complete.
    """
    entries = document["entries"]
    deferred = [entry for entry in entries if entry["wp"] == "DEFERRED"]
    rules = report.assignment_rules
    resolved = rules.get(RULE_DOC06, 0) + rules.get(RULE_SOLE, 0) + rules.get(RULE_COVERAGE, 0)

    lines = [
        "# 산문 ↔ 레지스트리 대조 리포트",
        "",
        "`WP-BOOT-01` 산출물. 레지스트리는 이 문서들에서 **한 번** 파종되고, 그 뒤로는",
        "레지스트리가 정본이고 산문이 뷰다(`05` §0.1). 이 리포트는 그 파종이 무엇을",
        "근거로 무엇을 만들었는지, 그리고 **산문이 말하지 않은 것이 무엇인지** 남긴다.",
        "",
        "## 1. 수용 조건",
        "",
        "| 조건 | 목표 | 실측 | 판정 |",
        "|---|---|---|---|",
        f"| ① 발급 WP 전량 등재 | 177 | {len({e['wp'] for e in entries} - {'DEFERRED', 'OUT'})} | "
        f"{'PASS' if len({e['wp'] for e in entries} - {'DEFERRED', 'OUT'}) == 177 else 'FAIL'} |",
        f"| ② 스키마 검증 | 오류 0 | {len(errors)} | {'PASS' if not errors else 'FAIL'} |",
        f"| 레코드 총계 | — | {len(entries)} | — |",
        f"| 명세 선언 요구사항 | — | {report.requirements} | — |",
        "",
        "## 2. 소유 WP 배정 규칙별 내역",
        "",
        "요구사항 → WP 소유 함수는 **코퍼스 어디에도 전수로 존재하지 않는다.**",
        "카탈로그의 명세 칸은 *인용*(다대다)이고 레지스트리가 필요한 것은 *소유*(다대일)이며,",
        "`06` §6은 영역 규칙과 대표 예시만 두고 전수는 레지스트리가 갖는다고 명시한다.",
        "그래서 배정은 아래 규칙으로만 이뤄지고, 모든 레코드가 자기 규칙을 `provenance`에 남긴다.",
        "",
        "| 규칙 | 뜻 | 건수 |",
        "|---|---|---|",
        *(
            f"| `{rule}` | {meaning} | {count} |"
            for rule, meaning, count in (
                (RULE_DOC06, "`06` §6이 소유 WP를 **명시**", rules.get(RULE_DOC06, 0)),
                (
                    RULE_SOLE,
                    "인용 WP가 **정확히 1개** — 선택의 여지가 없다",
                    rules.get(RULE_SOLE, 0),
                ),
                (
                    RULE_COVERAGE,
                    "후보 여럿 중 **레코드가 0개가 될 WP**로 배정 (177 전량 등재 제약)",
                    rules.get(RULE_COVERAGE, 0),
                ),
                (
                    RULE_AMBIGUOUS,
                    "인용 WP가 여럿이고 소유자 미명시 → `DEFERRED`",
                    rules.get(RULE_AMBIGUOUS, 0),
                ),
                ("uncited", "어느 WP도 인용하지 않음 → `DEFERRED`", rules.get("uncited", 0)),
                (
                    "plan-axis",
                    "요구사항이 닿지 않는 계획 기계 WP → `PLAN-<대역>-<nn>`",
                    sum(1 for entry in entries if entry["req"].startswith("PLAN-")),
                ),
            )
        ),
        "",
        f"**소유자가 확정된 요구사항 {resolved}건 / 미확정 {len(deferred)}건.**",
        "",
        "> 미확정은 숨긴 것이 아니라 드러낸 것이다. `wp: DEFERRED`는 스키마가",
        "> 이 상태를 위해 마련한 값이며 CI-04(게이트 필수)·CI-07(정규화 해시 필수)이",
        "> 둘 다 이 값을 면제한다. 배정을 발명하면 레지스트리는 초록불이 되고,",
        "> 어떤 검사기도 그 거짓을 볼 수 없게 된다.",
        "",
        "## 3. 산문이 남긴 결함 — 사람이 고쳐야 하는 것",
        "",
    ]

    def section(title: str, note: str, items: list[str]) -> None:
        lines.append(f"### {title} — {len(items)}건")
        lines.append("")
        lines.append(note)
        lines.append("")
        lines.extend(f"- `{item}`" for item in items[:40])
        if len(items) > 40:
            lines.append(f"- … 외 {len(items) - 40}건")
        lines.append("")

    section(
        "3.1 코드 스팬 안 이스케이프 누락 파이프",
        "표 행이 열 밀림으로 렌더링된다. 파서는 백틱 균형으로 복구하지만 **문서 결함**이다.",
        report.pipe_defects,
    )
    section(
        "3.2 우선순위가 `M`/`S`/`C`가 아닌 요구사항",
        "스키마 값 공간 밖이다. 파종은 `M`으로 채우지 않고 원본을 남긴다.",
        report.undeclared_priority,
    )
    section(
        "3.3 태그가 어휘 밖이거나 없는 요구사항",
        "`확정`으로 기본값을 주면 **확인되지 않은 것이 확인된 것으로** 승격된다. "
        "보수적으로 `미확인`으로 매핑하고 원본을 `provenance`에 남겼다.",
        report.undeclared_tag,
    )
    section(
        "3.4 번호 매긴 수용 항목이 0개인 WP",
        "`CG-*`는 수용 항목에서 위치로 도출된다(`06` §2.4a). 항목이 없으면 도출값도 없고, "
        "`PG-*`도 없으면 CI-04(게이트 없는 WP)에 걸린다.",
        report.packages_without_acceptance,
    )
    section(
        "3.5 카탈로그가 다단계로 선언한 WP",
        "형상·실행클래스 칸에 토큰이 둘 이상이다. 스칼라 칸에 토큰 2개는 금지이므로 "
        "`phases[]`로 인코딩했고, 각 스테이지의 `cancel_policy`는 실행 클래스에서 도출했다 — "
        "리그를 점유하는 스테이지는 `latch-to-hold`.",
        report.multi_stage_packages,
    )

    if errors:
        lines += ["## 4. 스키마 위반", ""] + [f"- {error}" for error in errors[:40]] + [""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Seed the registry, validate it, and write the reconciliation report.

    Returns:
        (int) 0 when the registry validates, 1 otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-dir", type=Path, default=REPO_ROOT / "docs" / "plan")
    parser.add_argument("--spec-dir", type=Path, default=REPO_ROOT / "docs" / "spec")
    parser.add_argument("--check", action="store_true", help="validate without writing")
    args = parser.parse_args(argv)

    document, report = build(args.plan_dir, args.spec_dir, f"{SPINE_DOC}@{_head_commit()}")
    validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
    errors = [
        f"{'/'.join(str(part) for part in error.absolute_path)}: {error.message}"
        for error in validator.iter_errors(document)
    ]

    if not args.check:
        REGISTRY_PATH.write_text(
            yaml.dump(
                document,
                Dumper=_NoAliasDumper,
                allow_unicode=True,
                sort_keys=False,
                width=100,
            ),
            encoding="utf-8",
        )
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(_render_report(document, report, errors), encoding="utf-8")

    packages = len({entry["wp"] for entry in document["entries"]} - {"DEFERRED", "OUT"})
    print(f"records={len(document['entries'])} packages={packages}/177 schema_errors={len(errors)}")
    for error in errors[:10]:
        print(f"  {error}", file=sys.stderr)
    return 0 if not errors and packages == 177 else 1


if __name__ == "__main__":
    raise SystemExit(main())
