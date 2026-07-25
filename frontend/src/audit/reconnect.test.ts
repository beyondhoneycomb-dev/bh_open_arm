// CG-5-04d — zero "reconnect" buttons anywhere (SPINE §2-2). A reconnect button is a
// zero-destruction button: connect() unconditionally calls set_zero_position(). Real
// tree: no shipped source carries a reconnect symbol or a reconnect-labelled button —
// the word appears only in comments (stripped) and in a sanctioned rezero WARNING
// string and a negative-assertion state transition, neither of which is a button.
// Synthetic: a latin reconnect handler and a Korean-labelled reconnect button both
// make the audit fire. These patterns carry the forbidden token, so they live here.

import { describe, expect, it } from "vitest";

import { scanForPatterns } from "./scan";
import type { NamedPattern } from "./types";
import { shippedSpaSources } from "./testSupport/collect";

const RECONNECT_AFFORDANCES: NamedPattern[] = [
  // Latin reconnect identifier/handler/label. In the committed tree this appears only
  // inside comments, which are stripped before scanning.
  { label: "reconnect symbol", pattern: /reconnect/i },
  // A button element whose text child is a reconnect action label. The rezero warning
  // string and the "session-reconnect" negative transition are not <button> children,
  // so they are not matched.
  {
    label: "reconnect button",
    pattern: /<button\b[^>]*>[^<]*(?:재연결|재접속|다시\s*연결)[^<]*<\/button>/,
  },
];

describe("CG-5-04d 0 reconnect buttons (SPINE §2-2)", () => {
  it("no shipped source carries a reconnect symbol or reconnect-labelled button", () => {
    expect(scanForPatterns(shippedSpaSources(), RECONNECT_AFFORDANCES, "CG-5-04d")).toEqual([]);
  });

  it("fires on a latin reconnect handler", () => {
    const findings = scanForPatterns(
      [{ path: "fake/x.tsx", code: "const onReconnect = () => reopenRobot();" }],
      RECONNECT_AFFORDANCES,
      "CG-5-04d",
    );
    expect(findings.length).toBeGreaterThan(0);
  });

  it("fires on a Korean-labelled reconnect button", () => {
    const findings = scanForPatterns(
      [{ path: "fake/x.tsx", code: '<button type="button" onClick={go}>재연결</button>' }],
      RECONNECT_AFFORDANCES,
      "CG-5-04d",
    );
    expect(findings.length).toBeGreaterThan(0);
  });

  it("does not fault a rezero warning string that merely mentions reconnection", () => {
    // Shaped like S-02 constants.ts: a warning note, not a button.
    const findings = scanForPatterns(
      [{ path: "fake/constants.ts", code: 'export const WARN = "재연결은 현재 물리 자세를 새 영점으로 확정합니다";' }],
      RECONNECT_AFFORDANCES,
      "CG-5-04d",
    );
    expect(findings).toEqual([]);
  });
});
