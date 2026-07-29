// The tool choices come from the backend registry and nowhere else: whatever ids
// it sends are the choices, and anything it sends that cannot be read as a choice
// is refused rather than dropped or coerced.

import { describe, expect, it, vi } from "vitest";

import { ConfigRequestError, type FetchLike } from "./client";
import { CONFIG_TOOLS_ENDPOINT } from "./endpoints";
import { ToolChoiceError, fetchToolChoices, parseToolChoices } from "./endEffectorTools";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const asFetch = (mock: ReturnType<typeof vi.fn>): FetchLike => mock as unknown as FetchLike;

describe("registered tool choices", () => {
  it("GETs the registry endpoint and returns every entry it sent", async () => {
    const registry = [
      { toolId: "fixed_spatula", label: "고정 스페츌러", gripperMotor: false },
      { toolId: "gripper", label: "v2 핀치 그리퍼", gripperMotor: true },
      { toolId: "suction_cup_v3", label: "석션 컵", gripperMotor: false },
    ];
    const fetchImpl = vi.fn(async () => jsonResponse(registry));

    const choices = await fetchToolChoices(asFetch(fetchImpl));

    expect(fetchImpl).toHaveBeenCalledWith(
      CONFIG_TOOLS_ENDPOINT,
      expect.objectContaining({ method: "GET" }),
    );
    expect(CONFIG_TOOLS_ENDPOINT).toBe("/api/config/tools");
    expect(choices).toEqual(registry);
  });

  it("returns an empty list as an empty list", () => {
    expect(parseToolChoices([])).toEqual([]);
  });

  it("refuses an entry whose gripperMotor is missing or not a boolean", () => {
    expect(() => parseToolChoices([{ toolId: "gripper", label: "그리퍼" }])).toThrow(
      ToolChoiceError,
    );
    expect(() =>
      parseToolChoices([{ toolId: "gripper", label: "그리퍼", gripperMotor: "true" }]),
    ).toThrow(ToolChoiceError);
  });

  it("refuses the whole list when one entry is malformed, rather than dropping it", () => {
    const withOneBadEntry = [
      { toolId: "fixed_spatula", label: "고정 스페츌러", gripperMotor: false },
      { toolId: "", label: "이름 없음", gripperMotor: true },
    ];
    expect(() => parseToolChoices(withOneBadEntry)).toThrow(ToolChoiceError);
  });

  it("refuses two rows under one id — they can disagree about the motor", () => {
    expect(() =>
      parseToolChoices([
        { toolId: "gripper", label: "그리퍼", gripperMotor: true },
        { toolId: "gripper", label: "그리퍼(구형)", gripperMotor: false },
      ]),
    ).toThrow(/duplicate tool id gripper/);
  });

  it("refuses a payload that is not an array", () => {
    expect(() => parseToolChoices({ tools: [] })).toThrow(ToolChoiceError);
    expect(() => parseToolChoices(null)).toThrow(ToolChoiceError);
  });

  it("throws ConfigRequestError on a non-ok response", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse([], 503));
    await expect(fetchToolChoices(asFetch(fetchImpl))).rejects.toBeInstanceOf(ConfigRequestError);
  });
});
