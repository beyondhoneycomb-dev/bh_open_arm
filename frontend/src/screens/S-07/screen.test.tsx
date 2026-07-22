// WP-G-S07 screen composition. It mounts under /collect via the plugin seam, renders
// every panel that carries a CG-G-S07 gate, and wires the start gate:
//  - CG-G-S07f: starting with push_to_hub on defers behind the explicit confirm.
//  - CG-G-S07g: disk headroom under an hour blocks the start.
//  - CG-G-S07a: the session-stop control emits `session_stop`, an episode control,
//    never a safety stop; the loop note says as much.
//  - 3C gates render gracefully as pending and do NOT block the start.

import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import CollectScreen from "./screen";
import { resolveScreen } from "../../routes/screenResolver";
import { defaultCollectData } from "./collectSource";
import type { RecorderCommand } from "./commands";
import type { CollectData, CollectDataSource } from "./types";

function sourceWith(overrides: Partial<CollectData>): CollectDataSource {
  const base = defaultCollectData();
  return { load: () => ({ ...base, ...overrides }) };
}

function recordingSink(): { sink: { send: (c: RecorderCommand) => void }; sent: RecorderCommand[] } {
  const sent: RecorderCommand[] = [];
  return { sink: { send: (c) => sent.push(c) }, sent };
}

describe("CollectScreen (WP-G-S07)", () => {
  it("is discovered by the screen resolver at /collect's S-07 id", () => {
    expect(resolveScreen("S-07")).not.toBeNull();
  });

  it("renders the route id and every gated panel", () => {
    render(<CollectScreen />);
    expect(screen.getByRole("heading", { name: "데이터 수집", level: 1 })).toBeInTheDocument();
    expect(screen.getByText("/collect")).toBeInTheDocument();
    for (const title of [
      "데이터셋",
      "태스크 프롬프트",
      "에피소드 루프",
      "저장량 예측",
      "드롭 리포트",
      "중단 세션 재개",
      "3C 게이트 상태",
    ]) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
    // The always-on push_to_hub badge (WP-G-03) is present in the header.
    expect(document.querySelector('[data-flag="push_to_hub"]')).not.toBeNull();
  });

  it("renders the 3C gates as pending and does not block the start on them (CG-G-S07a scope)", () => {
    const { sink, sent } = recordingSink();
    render(<CollectScreen source={sourceWith({})} commandSink={sink} />);
    // PG-STO-001 shows a pending badge, not a fabricated verdict.
    expect(screen.getByTestId("gate-PG-STO-001")).toHaveTextContent("대기");
    // Start is enabled (preflight ok, headroom ok, push off) despite the pending gate.
    const start = screen.getByRole("button", { name: "세션 시작" });
    expect(start).toBeEnabled();
    fireEvent.click(start);
    expect(sent).toEqual([{ op: "session_start", task: defaultCollectData().taskPrompt.text }]);
  });

  it("defers a push_to_hub start behind the explicit confirm (CG-G-S07f)", () => {
    const { sink, sent } = recordingSink();
    render(
      <CollectScreen
        source={sourceWith({ pushToHub: { enabled: true, private: false, tags: ["demo"] } })}
        commandSink={sink}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "세션 시작" }));
    // The confirm dialog opens; no session_start has been sent yet.
    const confirm = screen.getByRole("alertdialog");
    expect(sent).toEqual([]);
    fireEvent.click(within(confirm).getByRole("button", { name: /계속/ }));
    expect(sent).toEqual([{ op: "session_start", task: defaultCollectData().taskPrompt.text }]);
  });

  it("blocks the start when disk headroom is under an hour (CG-G-S07g)", () => {
    render(
      <CollectScreen
        source={sourceWith({
          storage: { freeBytes: 1, totalBytes: 2, bytesPerHour: 1, headroomHours: 0.5 },
        })}
      />,
    );
    expect(screen.getByRole("button", { name: "세션 시작" })).toBeDisabled();
    expect(screen.getByTestId("storage-block")).toBeInTheDocument();
  });

  it("session-stop emits session_stop, not a safety stop (CG-G-S07a)", () => {
    const { sink, sent } = recordingSink();
    render(<CollectScreen source={sourceWith({ sessionActive: true })} commandSink={sink} />);
    fireEvent.click(screen.getByRole("button", { name: "세션 정지" }));
    expect(sent).toEqual([{ op: "session_stop" }]);
  });
});
