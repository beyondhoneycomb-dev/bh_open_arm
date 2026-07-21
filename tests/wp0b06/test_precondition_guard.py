"""Acceptance ① — a measurement without the flock held is refused publication.

This is the pure-guard-logic acceptance that runs in full on this host: it needs
only the `WP-0B-01` lock manager (VFS `flock`), no CAN hardware. It proves both
directions — a lock-not-held publish writes nothing and raises, and a lock-held
publish writes an artifact stamped with `lock_held=true` evidence.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.can.lock.harness import HeldLockProcess
from backend.can.lock.manager import LockManager
from ops.hw.usb.artifact import ArtifactSource, MeasurementArtifact, publish_artifact
from ops.hw.usb.distribution import compute_distribution
from ops.hw.usb.fmax import compute_fmax
from ops.hw.usb.frames import record_frames_per_cycle
from ops.hw.usb.hol import build_hol_report
from ops.hw.usb.iplink import parse_bus_stats
from ops.hw.usb.precondition import (
    MeasurementRefusedError,
    require_lock_for_measurement,
)
from ops.hw.usb.topology import parse_topology

_IFACES = ("can0", "can1")


def _sample_artifact() -> MeasurementArtifact:
    """Build a minimal fixture-sourced artifact to exercise the publish path."""
    return MeasurementArtifact(
        source=ArtifactSource.SYNTHETIC_FIXTURE,
        topology=parse_topology(""),
        rtt=compute_distribution([200.0, 210.0, 260.0], unit="us"),
        fmax_per_arm=(compute_fmax("can0", {500: 499.0}),),
        frames=record_frames_per_cycle([32, 32, 32]),
        bus_stats=(parse_bus_stats("can0", ""),),
        hol=build_hol_report(),
    )


def test_publish_refused_without_lock(tmp_path: Path) -> None:
    """A manager holding no lock cannot publish; the destination stays absent."""
    manager = LockManager(lock_dir=str(tmp_path / "locks"))
    out_path = tmp_path / "artifact.json"

    with pytest.raises(MeasurementRefusedError):
        publish_artifact(manager, _IFACES, _sample_artifact(), out_path)

    assert not out_path.exists(), "a refused publish must write nothing"


def test_publish_refused_when_another_process_holds(tmp_path: Path) -> None:
    """When a *different* process holds the channels, our publish is still refused.

    Holding the lock elsewhere is the real hazard the precondition guards: our
    manager does not hold it, so the measurement would be perturbed and is void.
    """
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    manager = LockManager(lock_dir=str(lock_dir))
    out_path = tmp_path / "artifact.json"

    with HeldLockProcess(str(lock_dir), _IFACES):
        with pytest.raises(MeasurementRefusedError):
            require_lock_for_measurement(manager, _IFACES)
        with pytest.raises(MeasurementRefusedError):
            publish_artifact(manager, _IFACES, _sample_artifact(), out_path)

    assert not out_path.exists()


def test_publish_allowed_with_lock_and_carries_evidence(tmp_path: Path) -> None:
    """Holding every channel lets the publish through and stamps lock-held evidence."""
    lock_dir = tmp_path / "locks"
    manager = LockManager(lock_dir=str(lock_dir))
    result = manager.acquire_all(_IFACES)
    assert result.ok
    try:
        out_path = tmp_path / "artifact.json"
        evidence = publish_artifact(manager, _IFACES, _sample_artifact(), out_path)

        assert evidence.lock_held is True
        assert set(evidence.ifaces) == set(_IFACES)

        written = json.loads(out_path.read_text(encoding="utf-8"))
        assert written["lock_evidence"]["lock_held"] is True
        assert set(written["lock_evidence"]["ifaces"]) == set(_IFACES)
        # Fixture-sourced artifacts must never masquerade as hardware captures.
        assert written["source"] == ArtifactSource.SYNTHETIC_FIXTURE.value
    finally:
        manager.release_all()


def test_partial_hold_is_refused(tmp_path: Path) -> None:
    """Holding some but not all measured channels is refused — all-or-nothing."""
    lock_dir = tmp_path / "locks"
    manager = LockManager(lock_dir=str(lock_dir))
    assert manager.acquire_all(("can0",)).ok
    try:
        with pytest.raises(MeasurementRefusedError):
            require_lock_for_measurement(manager, _IFACES)
    finally:
        manager.release_all()
