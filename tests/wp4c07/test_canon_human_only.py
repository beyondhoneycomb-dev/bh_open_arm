"""CG-4C-07a — a MODEL label never enters the success-rate canon.

`FR-INF-079`: until the auto-judge is validated the success-rate canon is the human
label. This test is behavioural (a mixed set of human/model labels yields only the
human ones for the canon) and static (the package never imports the WP-4C-03
aggregator, so there is no in-package path that could feed it a model label, and the
one canon bridge filters on `LabelSource.HUMAN` rather than being a constant stub).
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from backend.eval.autojudge import canon_episodes, model_labels_excluded_from_canon
from backend.eval.autojudge import labels as labels_module
from backend.eval.stats.episode import EpisodeRecord
from tests.wp4c07.support import human, model

_AUTOJUDGE_DIR = Path(inspect.getfile(labels_module)).parent
_FORBIDDEN_CANON_IMPORTS = {"aggregate", "compare_checkpoints"}


def test_canon_drops_model_labels() -> None:
    """A mixed set yields only the human-labelled episodes' committed records."""
    judged = [
        human("pick", 1, True),
        model("pick", 2, True),
        human("pick", 3, False, failure_tags=("collision",)),
        model("pick", 4, False),
    ]
    canon = canon_episodes(judged)
    assert len(canon) == 2
    assert all(isinstance(record, EpisodeRecord) for record in canon)
    assert {record.seed for record in canon} == {1, 3}


def test_canon_excludes_all_model_when_only_model() -> None:
    """An all-model set yields an empty canon — no model label becomes a success number."""
    judged = [model("pick", 1, True), model("pick", 2, True)]
    assert canon_episodes(judged) == ()
    assert model_labels_excluded_from_canon(judged) == 2


def test_canon_positive_control_keeps_human() -> None:
    """An all-human set is kept whole — the guard is a filter, not a constant-empty stub."""
    judged = [human("pick", 1, True), human("pick", 2, False, failure_tags=("timeout",))]
    canon = canon_episodes(judged)
    assert len(canon) == 2
    assert model_labels_excluded_from_canon(judged) == 0


def test_static_autojudge_never_imports_the_canon_aggregator() -> None:
    """Static: no autojudge module imports WP-4C-03's `aggregate`/`compare_checkpoints`.

    The canon aggregation is WP-4C-03's job; this WP only prepares the human-only set.
    If nothing here imports the aggregator, there is no call site that could hand it a
    model label, so CG-4C-07a holds by construction, not by discipline.
    """
    offenders: dict[str, set[str]] = {}
    for source_path in _AUTOJUDGE_DIR.glob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "backend.eval.stats.aggregator":
                names = {alias.name for alias in node.names} & _FORBIDDEN_CANON_IMPORTS
                if names:
                    offenders.setdefault(source_path.name, set()).update(names)
            if isinstance(node, ast.ImportFrom) and node.module == "backend.eval.stats":
                names = {alias.name for alias in node.names} & _FORBIDDEN_CANON_IMPORTS
                if names:
                    offenders.setdefault(source_path.name, set()).update(names)
    assert not offenders, f"autojudge must not import the canon aggregator; found {offenders}"


def test_static_canon_bridge_filters_on_human_source() -> None:
    """Static: `canon_episodes` gates on `LabelSource.HUMAN`, not a blanket pass.

    Pairs with the behavioural tests: the filter both keeps humans and drops models,
    and the source it filters on is provably `HUMAN`.
    """
    source = inspect.getsource(canon_episodes)
    tree = ast.parse(source)
    references_human = any(
        isinstance(node, ast.Attribute)
        and node.attr == "HUMAN"
        and isinstance(node.value, ast.Name)
        and node.value.id == "LabelSource"
        for node in ast.walk(tree)
    )
    assert references_human, "canon_episodes must filter on LabelSource.HUMAN"
