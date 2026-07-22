"""WP-3A-03 ③ — get_action() is non-blocking, and the no-redefinition scan bites.

`02b` §5.2 WP-3A-03 ③ makes "`get_action()` has zero blocking IO" a static check; the
teleoperator is a Wave-3B deliverable, so the scanner is proven here on synthetic
modules — one that receives inside `get_action()` (must fire) and one that reads a
snapshot (must stay silent). The no-redefinition scan reuses the frozen `CTR-PRIM`
scanner: a teleop module that forks a primitive is caught, and the real schema is clean.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import contracts.prim as prim
import contracts.teleop as tel

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write(path: Path, source: str) -> Path:
    """Write a synthetic teleoperator module and return its path."""
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


def test_blocking_recv_inside_get_action_fires(tmp_path: Path) -> None:
    """A teleoperator that receives a UDP packet inside `get_action()` blocks the loop."""
    module = _write(
        tmp_path / "vr_blocking.py",
        """
        import time

        class OpenArmVR:
            def get_action(self):
                packet = self._sock.recv(4096)   # blocking receive on the loop thread
                time.sleep(0.001)
                return self._decode(packet)
        """,
    )
    hits = tel.scan_blocking_io(module)
    assert {h.call for h in hits} == {"recv", "sleep"}
    assert not tel.get_action_is_non_blocking(module)


def test_snapshot_read_in_get_action_is_silent(tmp_path: Path) -> None:
    """A teleoperator that reads the latest snapshot performs no blocking IO."""
    module = _write(
        tmp_path / "vr_snapshot.py",
        """
        class OpenArmVR:
            def get_action(self):
                sample = self._latest_sample        # snapshot written by the receiver thread
                return dict(sample.action)
        """,
    )
    assert tel.scan_blocking_io(module) == []
    assert tel.get_action_is_non_blocking(module)


def test_non_blocking_queue_get_is_exempt(tmp_path: Path) -> None:
    """An explicitly non-blocking `queue.get(block=False)` does not count as blocking."""
    module = _write(
        tmp_path / "vr_queue.py",
        """
        class OpenArmVR:
            def get_action(self):
                try:
                    return self._q.get(block=False)
                except Exception:
                    return self._latest
        """,
    )
    assert tel.scan_blocking_io(module) == []


def test_blocking_scan_only_reads_the_named_method(tmp_path: Path) -> None:
    """A blocking call in the receiver thread body is fine; only `get_action` is guarded."""
    module = _write(
        tmp_path / "vr_receiver.py",
        """
        class OpenArmVR:
            def _receive_loop(self):
                while True:
                    packet = self._sock.recv(4096)   # blocking, but this is the receiver thread
                    self._latest = self._decode(packet)

            def get_action(self):
                return dict(self._latest)
        """,
    )
    assert tel.scan_blocking_io(module, method="get_action") == []
    assert tel.scan_blocking_io(module, method="_receive_loop")


def test_real_teleop_schema_redefines_no_primitive() -> None:
    """The shipped CTR-TEL@v1 modules consume CTR-PRIM by import and fork no primitive."""
    assert tel.scan_teleop_redefinitions(REPO_ROOT) == []


def test_a_teleop_module_forking_the_timestamp_domain_is_caught(tmp_path: Path) -> None:
    """A teleop schema that declares its own clock source or ClockRole is a redefinition."""
    forked = _write(
        tmp_path / "tel_schema.py",
        """
        from contracts.prim import ErrorEnvelope

        CLOCK_SOURCE = "CLOCK_REALTIME"

        class ClockRole:
            SERVER = "server"
        """,
    )
    hits = prim.check_no_redefinition([forked])
    assert {h.symbol for h in hits} == {"CLOCK_SOURCE", "ClockRole"}
