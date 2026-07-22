"""WP-2C-10 acceptance ②: the feedback path does not go via IPC or a network transport.

The check is exercised in both directions. Against `backend.feedback` it must return clean,
which is the acceptance criterion. Against a package that imports `socket` it must flag the
import — a static check that can never fail is a fake green, and the `SUPERSEDED` negative
branch (an IPC-routed implementation) is only real if the check has teeth against the
transports this project actually uses (sockets, gRPC, WebSockets, an async event loop).
"""

from __future__ import annotations

from pathlib import Path

from backend.feedback import scan_imports
from backend.feedback.locality import BANNED_TRANSPORT_MODULES, is_in_process

_FEEDBACK_DIR = Path(__file__).resolve().parents[2] / "backend" / "feedback"


def test_feedback_package_imports_no_transport() -> None:
    assert scan_imports(_FEEDBACK_DIR) == ()
    assert is_in_process(_FEEDBACK_DIR)


def test_default_scan_self_applies_to_feedback() -> None:
    assert scan_imports() == ()


def test_banned_set_covers_this_projects_transports() -> None:
    # The stacks a real IPC re-implementation would reach for must all be caught, or the
    # SUPERSEDED branch could slip through on the transport someone actually chose.
    for transport in ("socket", "grpc", "websockets", "asyncio", "multiprocessing"):
        assert transport in BANNED_TRANSPORT_MODULES


def test_socket_import_is_flagged(tmp_path: Path) -> None:
    package = tmp_path / "ipc_feedback"
    package.mkdir()
    (package / "bridge.py").write_text(
        "import socket\n\n\ndef send() -> None:\n    socket.socket()\n",
        encoding="utf-8",
    )

    violations = scan_imports(package, root=tmp_path)

    assert len(violations) == 1
    assert violations[0].module == "socket"
    assert violations[0].file == "ipc_feedback/bridge.py"
    assert violations[0].line == 1
    assert not is_in_process(package)


def test_from_import_of_transport_submodule_is_flagged(tmp_path: Path) -> None:
    package = tmp_path / "rpc_feedback"
    package.mkdir()
    (package / "client.py").write_text(
        "from grpc.aio import insecure_channel\n",
        encoding="utf-8",
    )

    violations = scan_imports(package, root=tmp_path)

    assert [v.module for v in violations] == ["grpc"]


def test_relative_import_is_not_a_transport(tmp_path: Path) -> None:
    package = tmp_path / "local_feedback"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text(
        "from . import sinks\nfrom dataclasses import dataclass\n",
        encoding="utf-8",
    )

    assert scan_imports(package, root=tmp_path) == ()
