import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ForceTakeoverDialog } from "./ForceTakeoverDialog";
import type { ForceTakeoverPlan } from "./takeover";

function renderDialog(onConfirm: (plan: ForceTakeoverPlan) => void) {
  return render(
    <ForceTakeoverDialog
      role="admin"
      user="op-1"
      outgoingSession="sess-old"
      incomingSession="sess-new"
      currentGeneration={7}
      now={() => 123}
      onConfirm={onConfirm}
      onCancel={() => {}}
    />,
  );
}

describe("ForceTakeoverDialog (FR-GUI-085, CG-G-04f)", () => {
  it("shows a standing torque-not-released warning", () => {
    renderDialog(() => {});
    expect(screen.getByRole("alert")).toHaveTextContent(/토크를 해제하지 않습니다/);
  });

  it("blocks confirmation until reason and both confirmations are present", () => {
    const onConfirm = vi.fn();
    renderDialog(onConfirm);
    fireEvent.click(screen.getByRole("button", { name: "강제 회수" }));
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByText("사유를 입력해야 합니다.")).toBeInTheDocument();
    expect(screen.getByText("두 번의 확인이 모두 필요합니다.")).toBeInTheDocument();
  });

  it("confirms with a torque-retained plan and a generation bump when complete", () => {
    const onConfirm = vi.fn();
    renderDialog(onConfirm);
    fireEvent.change(screen.getByLabelText("회수 사유"), {
      target: { value: "교착 복구" },
    });
    fireEvent.click(screen.getByLabelText("1차 확인"));
    fireEvent.click(screen.getByLabelText("2차 확인"));
    fireEvent.click(screen.getByRole("button", { name: "강제 회수" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    const plan = onConfirm.mock.calls[0][0] as ForceTakeoverPlan;
    expect(plan.torqueRetainedAsStopHold).toBe(true);
    expect(plan.nextLeaseGeneration).toBe(8);
    expect(plan.audit.reason).toBe("교착 복구");
    expect(plan.audit.action).toBe("force_takeover");
  });
});
