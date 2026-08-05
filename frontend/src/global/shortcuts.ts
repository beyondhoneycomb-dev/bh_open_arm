// The keyboard-shortcut registry (FR-GUI-067). It provides the default mapping,
// a query by action, and a rebind that returns a new mapping. The minimum action
// set is fixed by the spec: STOP_HOLD, the four episode transitions, mode switch,
// and 3D view preset. Rebinding is pure so the caller holds the mapping in its own
// state; conflict detection flags two actions bound to the same chord, which a
// rebind UI must surface before committing.
//
// There is no POWER_CUT shortcut and there must never be one. `13` §2.7 enumerates
// every network edge this system has and none of them opens a contactor, so the key
// would have nothing to press (FR-GUI-067, NORM-007). STOP_HOLD is the only stop a
// key can reach, which is also why its chord is reserved below.

export const SHORTCUT_ACTIONS = [
  "soft_stop",
  "episode_start",
  "episode_success",
  "episode_fail",
  "episode_cancel",
  "mode_switch",
  "view_preset",
] as const;

export type ShortcutAction = (typeof SHORTCUT_ACTIONS)[number];

// STOP_HOLD's chord is a reserved key: FR-GUI-067 makes it non-rebindable, because an
// operator who has moved it cannot find it under the hand they trained, and the moment
// they need it is the moment they cannot go looking.
export const RESERVED_ACTION: ShortcutAction = "soft_stop";

export class ReservedShortcutError extends Error {
  readonly action: ShortcutAction;

  constructor(action: ShortcutAction) {
    super(`'${action}' is a reserved key and cannot be rebound (FR-GUI-067)`);
    this.name = "ReservedShortcutError";
    this.action = action;
  }
}

export interface ShortcutBinding {
  action: ShortcutAction;
  // Normalised chord, e.g. "Shift+Escape" or "F1".
  keys: string;
  label: string;
}

export const DEFAULT_SHORTCUTS: readonly ShortcutBinding[] = [
  { action: "soft_stop", keys: "Space", label: "소프트 스톱" },
  { action: "episode_start", keys: "Enter", label: "에피소드 시작" },
  { action: "episode_success", keys: "S", label: "에피소드 성공" },
  { action: "episode_fail", keys: "F", label: "에피소드 실패" },
  { action: "episode_cancel", keys: "C", label: "에피소드 취소" },
  { action: "mode_switch", keys: "M", label: "모드 전환" },
  { action: "view_preset", keys: "V", label: "3D 뷰 프리셋" },
];

// The binding for one action, or undefined if the mapping omits it.
export function getBinding(
  bindings: readonly ShortcutBinding[],
  action: ShortcutAction,
): ShortcutBinding | undefined {
  return bindings.find((binding) => binding.action === action);
}

// Rebind one action to a new chord, returning a new mapping. The other bindings
// are preserved. Rebinding the reserved action throws rather than returning the
// mapping unchanged: a silent refusal leaves the UI showing a chord the registry
// never accepted, so the operator learns the wrong key for the one action they
// cannot afford to hunt for.
export function rebind(
  bindings: readonly ShortcutBinding[],
  action: ShortcutAction,
  keys: string,
): ShortcutBinding[] {
  if (action === RESERVED_ACTION) {
    throw new ReservedShortcutError(action);
  }
  return bindings.map((binding) => (binding.action === action ? { ...binding, keys } : binding));
}

// Actions that share a chord with another action. A rebind UI must resolve these
// before the mapping is used, so a single key never fires two actions.
export function conflictingActions(bindings: readonly ShortcutBinding[]): ShortcutAction[] {
  const byChord = new Map<string, ShortcutAction[]>();
  for (const binding of bindings) {
    const chord = binding.keys.toLowerCase();
    const group = byChord.get(chord) ?? [];
    group.push(binding.action);
    byChord.set(chord, group);
  }
  const conflicts: ShortcutAction[] = [];
  for (const group of byChord.values()) {
    if (group.length > 1) {
      conflicts.push(...group);
    }
  }
  return conflicts;
}
