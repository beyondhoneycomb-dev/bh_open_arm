"""The `/api/system/report` payload, against the browser's `SystemData` shape and this host.

S-13 is a facade holding none of the canon, so everything it draws has to arrive in this one
response. What these tests pin is that it does, that the values are read rather than declared —
the kernel this test is running on, the socket it just opened — and that absence survives as
absence: an owner that could not be read, a syscall that was never made.
"""

from __future__ import annotations

import os
import socket
from http import HTTPStatus
from pathlib import Path

from fastapi.testclient import TestClient

from backend.config.serve import build_server_app
from backend.config.store import RuntimeConfigStore
from backend.system.bindings import read_bindings
from backend.system.bundle import PRODUCIBLE_ITEM_IDS
from backend.system.constants import SYSTEM_REPORT_ROUTE
from backend.system.report import system_report
from backend.system.rt import NO_RT_PRIVILEGE_NOTE, read_environment, read_process
from contracts.errors import load_registry
from contracts.ports import load_port_canon, served_component

LOOPBACK = "127.0.0.1"
ANY_FREE_PORT = 0


def _client(tmp_path: Path) -> TestClient:
    app, _websocket, _spa = build_server_app(RuntimeConfigStore(tmp_path))
    return TestClient(app)


def test_the_route_answers_with_the_four_sections_the_screen_reads(tmp_path: Path) -> None:
    response = _client(tmp_path).get(SYSTEM_REPORT_ROUTE)

    assert response.status_code == HTTPStatus.OK
    assert set(response.json()) == {"ports", "rt", "bundle", "errorRegistry"}


def test_the_canon_is_the_declaration_and_not_a_copy_of_it(tmp_path: Path) -> None:
    """A third copy of the port map is what `13` §2.7 forbids, so the served rows are the file's."""
    served = _client(tmp_path).get(SYSTEM_REPORT_ROUTE).json()["ports"]["canon"]

    assert [row["component"] for row in served] == [row.component for row in load_port_canon()]
    assert [row["port"] for row in served] == [row.port for row in load_port_canon()]


def test_the_component_with_no_network_boundary_travels_as_null_not_as_a_gap(
    tmp_path: Path,
) -> None:
    """The compare view renders null as "no port expected"; an omitted row would read as
    a component that lost its binding."""
    served = _client(tmp_path).get(SYSTEM_REPORT_ROUTE).json()["ports"]["canon"]

    assert any(row["port"] is None for row in served)


def test_the_actual_bindings_are_read_from_the_host() -> None:
    """A socket opened here appears in the report, which a declared list could not do."""
    listener = socket.socket()
    listener.bind((LOOPBACK, ANY_FREE_PORT))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        rows = read_bindings(served_component(), os.getpid(), frozenset({port}))
    finally:
        listener.close()

    assert [(row.port, row.pid) for row in rows] == [(port, os.getpid())]


def test_this_processs_own_socket_is_labelled_with_the_canon_component_name() -> None:
    """The compare view lines bindings up against the canon BY COMPONENT NAME, and this
    process's `comm` is `python`, which matches nothing in the canon."""
    listener = socket.socket()
    listener.bind((LOOPBACK, ANY_FREE_PORT))
    listener.listen()
    port = listener.getsockname()[1]
    try:
        rows = read_bindings(served_component(), os.getpid(), frozenset({port}))
    finally:
        listener.close()

    assert rows[0].component == served_component()


def test_a_socket_on_no_declared_port_and_owned_by_nobody_here_is_left_out() -> None:
    """A desktop has scores of listening sockets and none is a component of this rig.

    Reporting them would fill the "bound but not declared" list with the operating system and
    bury the one row that matters.
    """
    rows = read_bindings(served_component(), os.getpid(), frozenset())
    foreign = [row for row in rows if row.pid != os.getpid()]

    assert foreign == []


def test_the_environment_is_this_kernel_and_this_interpreter() -> None:
    """Read, not declared: the assertion is against what the test process itself reports."""
    import platform

    env = read_environment()

    assert env.kernel_release == platform.release()
    assert env.python_version == platform.python_version()


def test_a_process_reports_its_real_scheduling_class() -> None:
    process = read_process(os.getpid())

    assert process is not None
    assert process.pid == os.getpid()
    assert process.sched_policy.startswith("SCHED_")
    assert os.sched_getaffinity(os.getpid()) == set(process.cpu_affinity)


def test_a_syscall_never_made_is_reported_as_never_made() -> None:
    """Nothing in this repository calls mlockall. False would say it failed, which is a
    different fact from not having been attempted — and `14` FR-OPS-023 keeps this field
    beside `VmLck` precisely so the two can be seen disagreeing."""
    process = read_process(os.getpid())

    assert process is not None
    assert process.mlockall_returned_ok is None


def test_a_process_with_no_realtime_policy_is_named_with_its_registry_code(
    tmp_path: Path,
) -> None:
    """The test process is on SCHED_OTHER, so the finding is the true reading of this host."""
    findings = _client(tmp_path).get(SYSTEM_REPORT_ROUTE).json()["rt"]["findings"]

    assert [finding["code"] for finding in findings] == ["OA-SYS-003"]
    assert findings[0]["note"] == NO_RT_PRIVILEGE_NOTE


def test_the_manifest_claims_only_what_this_report_carries(tmp_path: Path) -> None:
    """An id listed here is one the screen will stop showing as missing, so it has to be true."""
    body = _client(tmp_path).get(SYSTEM_REPORT_ROUTE).json()

    assert body["bundle"]["includedItemIds"] == list(PRODUCIBLE_ITEM_IDS)
    assert body["bundle"]["includeVideo"] is False
    assert body["bundle"]["includePii"] is False


def test_the_error_registry_is_the_frozen_one_whole(tmp_path: Path) -> None:
    """Served rather than mirrored into the browser: `14` §2.10 is the single source."""
    served = _client(tmp_path).get(SYSTEM_REPORT_ROUTE).json()["errorRegistry"]
    registry = load_registry()

    assert set(served) == set(registry.codes)
    entry = served["OA-SYS-003"]
    assert entry["messageKo"] == registry.codes["OA-SYS-003"].message_ko
    assert entry["recoveryHint"] == registry.codes["OA-SYS-003"].recovery_hint
    assert entry["subsystem"] == registry.codes["OA-SYS-003"].subsystem


def test_the_report_is_readable_without_an_arm() -> None:
    """Assembled from host files only. A diagnostic that needed the robot to be up could not
    answer the question it exists for."""
    assert set(system_report()) == {"ports", "rt", "bundle", "errorRegistry"}
