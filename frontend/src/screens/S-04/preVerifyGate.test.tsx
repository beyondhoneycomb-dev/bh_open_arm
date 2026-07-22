// CG-G-S04h: replay and home-return execute buttons are disabled when the backend
// trajectory pre-verify fails. The pre-verify (joint limits, velocity/accel,
// self/env collision) is the backend's (FR-MAN-044); the screen renders the
// verdict and gates execute on it — it runs no collision check. A blocked button
// also emits nothing when its handler is invoked.

import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { HomePanel } from "./HomePanel";
import { TeachReplayPanel } from "./TeachReplayPanel";
import { defaultManualSource, type PreVerifyReport } from "./manualSource";

const FAILING: PreVerifyReport = {
  passed: false,
  firstViolationIndex: 3,
  checks: [
    { id: "joint_limits", label: "관절 리밋", passed: true },
    { id: "self_collision", label: "자기충돌", passed: false, detail: "#3에서 접촉" },
  ],
};

const PASSING: PreVerifyReport = {
  passed: true,
  firstViolationIndex: null,
  checks: [{ id: "joint_limits", label: "관절 리밋", passed: true }],
};

describe("CG-G-S04h home execute gated on pre-verify", () => {
  it("disables Home execute when pre-verify fails", () => {
    const base = defaultManualSource();
    const onCommand = vi.fn();
    const { container } = render(
      <HomePanel
        home={{ ...base.home, preVerify: FAILING }}
        side="right"
        activeProfileId={base.home.activeProfileId}
        onProfileChange={vi.fn()}
        canMove
        onCommand={onCommand}
      />,
    );
    const execute = container.querySelector('[data-field="home-execute"]') as HTMLButtonElement;
    expect(execute).toBeDisabled();
    fireEvent.click(execute);
    expect(onCommand).not.toHaveBeenCalled();
  });

  it("enables Home execute and emits home_execute when pre-verify passes", () => {
    const base = defaultManualSource();
    const onCommand = vi.fn();
    const { container } = render(
      <HomePanel
        home={{ ...base.home, preVerify: PASSING }}
        side="right"
        activeProfileId={base.home.activeProfileId}
        onProfileChange={vi.fn()}
        canMove
        onCommand={onCommand}
      />,
    );
    const execute = container.querySelector('[data-field="home-execute"]') as HTMLButtonElement;
    expect(execute).toBeEnabled();
    fireEvent.click(execute);
    expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({ op: "home_execute" }));
  });
});

describe("CG-G-S04h replay gated on pre-verify (and zero match)", () => {
  function renderTeach(preVerify: PreVerifyReport, zeroMismatch: boolean, onCommand = vi.fn()) {
    const base = defaultManualSource();
    return {
      onCommand,
      ...render(
        <TeachReplayPanel
          teach={{
            preVerify,
            points: [
              {
                id: "tp-1",
                name: "p1",
                armSide: "right",
                qUrdfRad: [0, 0, 0, 1.5708, 0, 0, 0, 0],
                zeroMethod: "jig",
                zeroMismatch,
                gainProfile: base.gains.replayProfile,
              },
            ],
          }}
          side="right"
          canMove
          onCapture={vi.fn()}
          onDelete={vi.fn()}
          onDuplicate={vi.fn()}
          onReorder={vi.fn()}
          onCommand={onCommand}
        />,
      ),
    };
  }

  it("disables replay when pre-verify fails", () => {
    const { container } = renderTeach(FAILING, false);
    expect(container.querySelector('[data-field="teach-replay"]')).toBeDisabled();
  });

  it("disables replay on a zero-method mismatch even if pre-verify passes", () => {
    const { container } = renderTeach(PASSING, true);
    expect(container.querySelector('[data-field="teach-replay"]')).toBeDisabled();
  });

  it("enables replay and emits replay_execute when pre-verify passes and zero matches", () => {
    const { container, onCommand } = renderTeach(PASSING, false);
    const replay = container.querySelector('[data-field="teach-replay"]') as HTMLButtonElement;
    expect(replay).toBeEnabled();
    fireEvent.click(replay);
    expect(onCommand).toHaveBeenCalledWith(expect.objectContaining({ op: "replay_execute" }));
  });
});
