// Consume the frozen CTR-WS@v1 envelope schema as a test target: parse the
// backend-frozen JSON and assert the browser role mirror agrees with it, so a
// change to the transport roles or the named control holder breaks this test
// rather than desynchronising the E-Stop reachability matrix.

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

import {
  CONTROL_ROLES,
  OBSERVER_MAY_SEND_CONTROL_FRAME,
  WS_CONTROL_HOLDER_ROLE,
  WS_ROLES,
} from "./wsRoles";
import { repoFile } from "../testSupport/repoRoot";

interface FrozenEnvelope {
  roles: {
    values: string[];
    control_holder_role: string;
    observer_may_send_control_frame: boolean;
  };
}

const FROZEN = JSON.parse(
  readFileSync(repoFile("contracts/ws/envelope.schema.json"), "utf-8"),
) as FrozenEnvelope;

describe("CTR-WS@v1 role mirror agrees with the frozen envelope", () => {
  it("pins the same transport roles", () => {
    expect(WS_ROLES).toEqual(FROZEN.roles.values);
  });

  it("pins the same single control holder", () => {
    expect(WS_CONTROL_HOLDER_ROLE).toBe(FROZEN.roles.control_holder_role);
  });

  it("agrees that an observer may not send a control frame", () => {
    expect(OBSERVER_MAY_SEND_CONTROL_FRAME).toBe(FROZEN.roles.observer_may_send_control_frame);
  });

  it("collapses the transport roles onto the observer/controller acceptance axis", () => {
    expect(CONTROL_ROLES).toEqual(["observer", "controller"]);
  });
});
