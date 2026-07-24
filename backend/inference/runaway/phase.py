"""The inference phase the detector observes and the FAULT (P8) it drives to.

`11` §4.1 fixes a nine-state inference machine on one connected robot; this module
carries only the two states the runaway detector is concerned with, because the
detector neither owns nor drives P0..P2/P4..P7 — the load/pause/takeover/recover
transitions live above it. What the detector *does* effect is the one arrow
`11` §4.2 gives it: **P3 RUNNING -> P8 FAULT** on a runaway, an outlier storm, or a
remote disconnect (queue discarded, hold held, error coded).

P8 is one-way here on purpose (`11` §4.3 forbids `P8 -> P3`): once faulted the
detector publishes only hold intents and refuses fresh policy output until an
explicit acknowledgement routes recovery through P7. That refusal, not the
scheduler's latch, is the publisher-side "no auto-resume" — the detector is a
producer (SPINE §2-1) and never touches the scheduler's `SafetyLatch`.
"""

from __future__ import annotations

from enum import Enum


class InferencePhase(Enum):
    """The two inference phases the runaway detector distinguishes (`11` §4.1).

    RUNNING is P3 (autonomous execution, policy output gated and published); FAULT
    is P8 (queue discarded, hold intent published, alarm raised). The remaining
    seven states of the `11` §4.1 machine are not this component's to manage.
    """

    RUNNING = "P3"
    FAULT = "P8"


class FaultKind(Enum):
    """Why the detector drove P3 -> P8, kept distinct so the audit attributes cause.

    A runaway (one of the four `FR-INF-043` conditions) and a remote disconnect
    (`FR-INF-046`) are different failures with different recoveries and different
    error codes, so a single "faulted" bucket would erase the distinction the
    failure taxonomy (`11` §3.4 / 4C) depends on.
    """

    RUNAWAY = "runaway"
    REMOTE_DISCONNECT = "remote_disconnect"
