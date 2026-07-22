// CG-G-S13b: the mlockall check actually reads VmLck, not the syscall return.
// CG-G-S13g: a PREEMPT_RT-absent environment shows a code plus its remedy.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RtCheckView } from "./RtCheckView";
import { mlockallLocked, mlockallSilentFailure, preemptRtAbsent } from "./rtCheck";
import { loadErrorRegistry } from "./testSupport";
import type { ProcessRtStatus, RtCheckData, RtEnvironment } from "./types";

const REGISTRY = loadErrorRegistry();

function proc(overrides: Partial<ProcessRtStatus> = {}): ProcessRtStatus {
  return {
    pid: 4242,
    name: "openarm-backend",
    schedPolicy: "SCHED_FIFO",
    schedPriority: 80,
    cpuAffinity: [2, 3],
    vmlckKb: 2048,
    mlockallReturnedOk: true,
    ...overrides,
  };
}

function env(overrides: Partial<RtEnvironment> = {}): RtEnvironment {
  return { kernelRelease: "6.8.0-rt", preemptRt: true, pythonVersion: "3.11.9", ...overrides };
}

function rt(overrides: Partial<RtCheckData> = {}): RtCheckData {
  return { env: env(), processes: [proc()], findings: [], ...overrides };
}

describe("mlockall verified via VmLck (CG-G-S13b)", () => {
  it("counts locked only when VmLck is positive", () => {
    expect(mlockallLocked(proc({ vmlckKb: 2048 }))).toBe(true);
    expect(mlockallLocked(proc({ vmlckKb: 0 }))).toBe(false);
  });

  it("flags a silent failure: return OK but VmLck zero", () => {
    expect(mlockallSilentFailure(proc({ mlockallReturnedOk: true, vmlckKb: 0 }))).toBe(true);
    expect(mlockallSilentFailure(proc({ mlockallReturnedOk: true, vmlckKb: 512 }))).toBe(false);
  });

  it("renders unlocked and a silent-failure alert when the return value lies", () => {
    render(<RtCheckView rt={rt({ processes: [proc({ mlockallReturnedOk: true, vmlckKb: 0 })] })} registry={REGISTRY} />);
    expect(screen.getByTestId("rt-mlockall-4242")).toHaveTextContent("미잠김");
    expect(screen.getByTestId("rt-silent-4242")).toBeInTheDocument();
    expect(screen.getByTestId("rt-proc-4242")).toHaveAttribute("data-mlockall-locked", "false");
  });

  it("renders locked from a positive VmLck even if the process reads it back plainly", () => {
    render(<RtCheckView rt={rt({ processes: [proc({ vmlckKb: 4096 })] })} registry={REGISTRY} />);
    expect(screen.getByTestId("rt-mlockall-4242")).toHaveTextContent("잠김");
    expect(screen.getByTestId("rt-vmlck-4242")).toHaveTextContent("4096");
    expect(screen.queryByTestId("rt-silent-4242")).toBeNull();
  });
});

describe("PREEMPT_RT absence shows code + remedy (CG-G-S13g)", () => {
  it("detects the absent environment", () => {
    expect(preemptRtAbsent(env({ preemptRt: false }))).toBe(true);
    expect(preemptRtAbsent(env({ preemptRt: true }))).toBe(false);
  });

  it("renders the backend-declared code with its registry remedy", () => {
    const data = rt({
      env: env({ preemptRt: false }),
      findings: [{ code: "OA-SYS-003", note: null }],
    });
    render(<RtCheckView rt={data} registry={REGISTRY} />);
    const remedy = screen.getByTestId("rt-preempt-remedy");
    expect(remedy).toBeInTheDocument();
    expect(screen.getByTestId("error-entry-OA-SYS-003")).toBeInTheDocument();
    expect(screen.getByTestId("error-recovery")).toHaveTextContent(REGISTRY["OA-SYS-003"].recoveryHint);
    expect(screen.getByTestId("rt-preempt")).toHaveAttribute("data-present", "false");
  });

  it("does not show the remedy block when PREEMPT_RT is present", () => {
    render(<RtCheckView rt={rt({ env: env({ preemptRt: true }) })} registry={REGISTRY} />);
    expect(screen.queryByTestId("rt-preempt-remedy")).toBeNull();
  });
});
