# Crash Report Contract (WP-OPS-05)

This document is the contract for the crash report the telemetry watchdog produces. It exists
because a crash report that *reads* as reassuring is dangerous: the reader must never come away
believing the software could have caught the arm.

## The four required fields (14 FR-OPS-024)

Every crash report carries all four of these; a report missing any one is incomplete:

1. **exit code** — the conventional exit status (`128 + signal` for a signal death).
2. **signal** — the terminating signal number (e.g. `SIGKILL` = 9), when death was by signal.
3. **preceding 30 s diagnostic ring buffer** — the structured diagnostics from the 30 seconds
   before death, replayed from the atomically spooled crash context.
4. **last state transition** — the most recent state change before death.

A backtrace is included *when possible*. SIGKILL and the OOM killer are uncatchable and leave
none, so the backtrace is optional and never one of the four required fields.

## Safety fact — NFR-SAF-009 (this is not negotiable)

The software watchdog cannot prevent a drop; it can only delay one. On process death
(SIGKILL / OOM / deadlock) or CAN bus-off, a soft hold is impossible, so the arm drops. The
fail-safe is mechanical support, drop-zone isolation, and an independent power-cutoff circuit —
never software.

The watchdog in this work package **detects and explains** a drop after the fact. It does not,
and cannot, stop one. Any wording in a report, a dashboard, or an operator prompt that implies
otherwise is a safety defect and must be removed.

## Process boundary — NFR-PRF-038

The MCAP timeseries writer runs in a **different process** from the control loop. Serialization
and disk I/O never execute on the real-time path.
