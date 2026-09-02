// RT / permission verification (CG-G-S13b, CG-G-S13g). The mlockall verdict is
// derived from /proc/<pid>/status VmLck, never from the syscall return value:
// 14 FR-OPS-023 mandates VmLck as the evidence, and a silent mlockall failure
// (return OK, nothing actually locked) would otherwise stand as "success" and
// mislead the PG-RT-001b interpretation (CG-G-S13a negative branch). The
// condition->code judgement for RT deficiencies is the backend's; this module
// only reads the numbers it is given.

import type { ProcessRtStatus, RtEnvironment } from "./types";

// mlockall took effect iff the kernel actually locked pages, which VmLck reports. An
// unread VmLck is not evidence of locking, so it reads the same as nothing locked.
export function mlockallLocked(status: ProcessRtStatus): boolean {
  return status.vmlckKb !== null && status.vmlckKb > 0;
}

// The exact failure the gate targets: the syscall claimed success while VmLck
// shows nothing locked. Surfacing this keeps a false "RT ready" off the screen.
export function mlockallSilentFailure(status: ProcessRtStatus): boolean {
  // Only a syscall that actually reported success can fail silently. A process that never
  // called mlockall has nothing to disagree with, and flagging it would put a red line
  // beside every process on a rig nobody has promoted yet.
  return status.mlockallReturnedOk === true && (status.vmlckKb ?? 0) <= 0;
}

// PREEMPT_RT absence is a reported environment fact (14 FR-OPS-023); its remedy is
// rendered from the backend-declared RtFinding code, not decided here.
export function preemptRtAbsent(env: RtEnvironment): boolean {
  return env.preemptRt === false;
}

// Whether a process is under a realtime scheduling class. Presentation only — the
// promotion policy (which threads get `chrt -f`) is the backend's (FR-OPS-063).
export const REALTIME_SCHED_POLICIES: readonly string[] = ["SCHED_FIFO", "SCHED_RR"];

export function isRealtimeScheduled(status: ProcessRtStatus): boolean {
  return REALTIME_SCHED_POLICIES.includes(status.schedPolicy);
}
