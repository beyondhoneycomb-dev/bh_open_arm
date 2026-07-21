"""WP-0A-03 acceptance ⑤ — an edit to an unowned file is rejected.

⑤ A file that no ownership glob claims has no owner to attribute an edit to, so
   the attempt is rejected. A file inside an owned tree is accepted.
"""

from __future__ import annotations

from ownership.prover import unowned_paths

_OWNED_TREE = ("backend/actuation/**",)
_OWNED_FILE = "backend/actuation/scheduler.py"
_UNOWNED_FILE = "web/screens/S-01/App.tsx"


def test_edit_to_an_unowned_file_is_rejected() -> None:
    """Acceptance ⑤ — a path matched by no glob is returned as unowned."""
    assert unowned_paths((_UNOWNED_FILE,), _OWNED_TREE) == (_UNOWNED_FILE,)


def test_edit_inside_an_owned_tree_is_accepted() -> None:
    """A path an owned glob claims is not reported as unowned."""
    assert unowned_paths((_OWNED_FILE,), _OWNED_TREE) == ()


def test_mixed_batch_reports_only_the_unowned_paths() -> None:
    """An edit set spanning both owned and unowned files reports only the latter."""
    assert unowned_paths((_OWNED_FILE, _UNOWNED_FILE), _OWNED_TREE) == (_UNOWNED_FILE,)
