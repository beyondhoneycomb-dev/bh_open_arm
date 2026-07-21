"""The `WP-0B-06` measurement artifact and its lock-guarded publication path.

The deliverable of `WP-0B-06` is a single artifact carrying the USB topology, the
RTT distribution, per-arm `f_max_can`, the frames-per-cycle record, the CAN bus
statistics and the HOL report — and, as a hard contract, `lock_held=true` evidence
(`15` §2.10 M-1 precondition). Publication is *refused* when the flock was not held.

Two honesty rules are enforced here, not left to the caller:

- The lock guard: `publish_artifact` calls `require_lock_for_measurement` before it
  writes anything, so a lock-not-held publish leaves no file on disk.
- The provenance rule: every artifact declares its `source`. A `SYNTHETIC_FIXTURE`
  artifact is what the on-host tests produce and it never claims to be a hardware
  measurement; only the deferred live path stamps `HARDWARE_CAPTURE`. This is what
  keeps a fixture-built artifact from being read as a real green.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from backend.can.lock.manager import LockManager
from ops.hw.usb.distribution import Distribution
from ops.hw.usb.fmax import FmaxResult
from ops.hw.usb.frames import FramesPerCycle
from ops.hw.usb.hol import HolReport
from ops.hw.usb.iplink import CanBusStats
from ops.hw.usb.precondition import LockHeldEvidence, require_lock_for_measurement
from ops.hw.usb.topology import TopologyReport

ARTIFACT_SCHEMA = "openarm.wp0b06.measurement/v1"


class ArtifactSource(StrEnum):
    """Where an artifact's numbers came from — the anti-fake-green marker.

    HARDWARE_CAPTURE is only ever set by the live measurement path against a real
    adapter. SYNTHETIC_FIXTURE marks data built from fixtures or the re-verification
    harness on a host with no adapter, so no fixture artifact can pose as hardware.
    """

    HARDWARE_CAPTURE = "hardware_capture"
    SYNTHETIC_FIXTURE = "synthetic_fixture"


@dataclass(frozen=True)
class MeasurementArtifact:
    """The assembled `WP-0B-06` measurement, before it is lock-cleared for publish.

    `lock_evidence` is populated by `publish_artifact` at publish time, not by the
    builder, so the evidence proves the lock was held *when the artifact was
    published*, not merely when its parts were computed.

    Attributes:
        source: Provenance of the data (hardware vs fixture).
        topology: The USB topology / adapter-membership report.
        rtt: The RTT distribution (with histogram).
        fmax_per_arm: Per-arm `f_max_can` verdicts.
        frames: The frames-per-cycle record and `PG-CAN-001` input.
        bus_stats: Per-interface CAN bus statistics.
        hol: The HOL characteristic report.
        lock_evidence: The `lock_held=true` evidence, or None before publish.
    """

    source: ArtifactSource
    topology: TopologyReport
    rtt: Distribution
    fmax_per_arm: tuple[FmaxResult, ...]
    frames: FramesPerCycle
    bus_stats: tuple[CanBusStats, ...]
    hol: HolReport
    lock_evidence: LockHeldEvidence | None = None

    def as_dict(self) -> dict[str, object]:
        """Project the whole artifact to a JSON-serialisable mapping.

        Returns:
            (dict[str, object]) The artifact as plain data.
        """
        return {
            "schema": ARTIFACT_SCHEMA,
            "source": self.source.value,
            "usb_topology": self.topology.as_dict(),
            "rtt_distribution": self.rtt.as_dict(),
            "f_max_can": [result.as_dict() for result in self.fmax_per_arm],
            "frames_per_cycle": self.frames.as_dict(),
            "bus_stats": [stats.as_dict() for stats in self.bus_stats],
            "hol_report": self.hol.as_dict(),
            "lock_evidence": (
                self.lock_evidence.as_dict() if self.lock_evidence is not None else None
            ),
        }


def publish_artifact(
    manager: LockManager,
    ifaces: Sequence[str],
    artifact: MeasurementArtifact,
    out_path: Path,
) -> LockHeldEvidence:
    """Publish the artifact to `out_path`, but only while the flock is held.

    The lock check strictly precedes the write: on a refusal nothing is written, so
    a caller cannot leave a partial or unproven artifact on disk. On success the
    `lock_held=true` evidence is stamped into the written JSON and also returned.

    Args:
        manager: The lock manager expected to hold `ifaces`.
        ifaces: The channels the measurement covers; all must be held.
        artifact: The assembled measurement (its `lock_evidence` is overwritten).
        out_path: Destination JSON path; created only when the lock is held.

    Returns:
        (LockHeldEvidence) The evidence written into the artifact.

    Raises:
        MeasurementRefusedError: If any channel is not held; `out_path` is not written.
    """
    evidence = require_lock_for_measurement(manager, ifaces)
    cleared = MeasurementArtifact(
        source=artifact.source,
        topology=artifact.topology,
        rtt=artifact.rtt,
        fmax_per_arm=artifact.fmax_per_arm,
        frames=artifact.frames,
        bus_stats=artifact.bus_stats,
        hol=artifact.hol,
        lock_evidence=evidence,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(cleared.as_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return evidence
