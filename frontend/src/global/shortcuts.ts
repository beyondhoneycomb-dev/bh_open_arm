// The keyboard-shortcut registry (FR-GUI-067). It provides the default mapping,
// a query by action, and a rebind that returns a new mapping. The minimum action
// set is fixed by the spec: emergency stop, soft stop, the four episode
// transitions, mode switch, and 3D view preset. Rebinding is pure so the caller
// holds the mapping in its own state; conflict detection flags two actions bound
// to the same chord, which a rebind UI must surface before committing.

export const SHORTCUT_ACTIONS = [
  "emergency_stop",
  "soft_stop",
  "episode_start",
  "episode_success",
  "episode_fail",
  "episode_cancel",
  "mode_switch",
  "view_preset",
] as const;

export type ShortcutAction = (typeof SHORTCUT_ACTIONS)[number];

export interface ShortcutBinding {
  action: ShortcutAction;
  // Normalised chord, e.g. "Shift+Escape" or "F1".
  keys: string;
  label: string;
}

export const DEFAULT_SHORTCUTS: readonly ShortcutBinding[] = [
  { action: "emergency_stop", keys: "Escape", label: "비상정지 (하드 E-Stop)" },
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
// are preserved.
export function rebind(
  bindings: readonly ShortcutBinding[],
  action: ShortcutAction,
  keys: string,
): ShortcutBinding[] {
  return bindings.map((binding) =>
    binding.action === action ? { ...binding, keys } : binding,
  );
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
