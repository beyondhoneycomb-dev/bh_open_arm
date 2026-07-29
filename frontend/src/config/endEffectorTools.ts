// The end-effector choices an operator may pick from, read from the backend
// registry (GET /api/config/tools). The browser holds no copy of that list: the
// registry is open and more tools are expected, so a bundled list would hide a
// tool that was just registered and offer one that was removed. Same injectable-
// fetch idiom as client.ts, so the selector's tests need no live backend.
//
// A malformed list is refused whole rather than repaired entry by entry.
// `gripperMotor` is the one field that decides whether CAN id 0x08 is addressed
// on that arm: read as false it hides a fitted gripper, read as true it addresses
// a motor that is not on the bus, and nobody ACKs that frame — the transmit error
// counter climbs and the controller drops to ERROR-PASSIVE, degrading the seven
// joints that are present. No coercion is safe, so there is none.

import { ConfigRequestError, type FetchLike } from "./client";
import { CONFIG_TOOLS_ENDPOINT } from "./endpoints";

export interface ToolChoice {
  toolId: string;
  // Operator-facing name, the backend's (ToolDefinition.label).
  label: string;
  // Whether this tool puts an actuated motor on CAN id 0x08.
  gripperMotor: boolean;
}

export class ToolChoiceError extends Error {
  constructor(message: string) {
    super(`tool list refused: ${message}`);
    this.name = "ToolChoiceError";
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

function isToolChoice(value: unknown): value is ToolChoice {
  return (
    isObject(value) &&
    isNonEmptyString(value.toolId) &&
    isNonEmptyString(value.label) &&
    typeof value.gripperMotor === "boolean"
  );
}

// Validate the registry's answer. Every rejection throws with the offending entry
// named, because the caller's only safe move is to offer no choices at all: a
// selector that silently drops the entry it could not read would present a
// shorter list as if it were the whole one.
export function parseToolChoices(raw: unknown): ToolChoice[] {
  if (!Array.isArray(raw)) {
    throw new ToolChoiceError(`expected an array, got ${JSON.stringify(raw)}`);
  }

  const choices: ToolChoice[] = [];
  const seenIds = new Set<string>();
  for (const entry of raw) {
    if (!isToolChoice(entry)) {
      throw new ToolChoiceError(`malformed entry ${JSON.stringify(entry)}`);
    }
    // Two rows under one id can disagree about gripperMotor, and there is no way
    // to tell which one the rig is wearing.
    if (seenIds.has(entry.toolId)) {
      throw new ToolChoiceError(`duplicate tool id ${entry.toolId}`);
    }
    seenIds.add(entry.toolId);
    choices.push({
      toolId: entry.toolId,
      label: entry.label,
      gripperMotor: entry.gripperMotor,
    });
  }
  return choices;
}

export async function fetchToolChoices(fetchImpl: FetchLike = fetch): Promise<ToolChoice[]> {
  const response = await fetchImpl(CONFIG_TOOLS_ENDPOINT, {
    method: "GET",
    headers: { Accept: "application/json" },
  });
  if (!response.ok) {
    throw new ConfigRequestError(response.status, response.statusText);
  }
  return parseToolChoices(await response.json());
}
