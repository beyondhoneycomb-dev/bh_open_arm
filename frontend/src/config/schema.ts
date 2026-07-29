// Client-side view of the backend runtime_config.json (FR-GUI-004). The canon
// lives in the backend (XDG, pydantic extra="forbid", atomic write); the browser
// holds only an in-memory copy fetched over REST and never persists it as canon
// (CG-G-00e). This module mirrors the backend's blast-radius isolation on the
// read path: when one subobject arrives malformed, only that subobject falls
// back to its defaults and every other subobject is preserved (CG-G-00d). The
// isolation lives per subobject so a single corrupt field can never wipe the
// user's whole layout.

export type LayoutDensity = "comfortable" | "compact";
export type ThemeMode = "light" | "dark" | "system";

export interface LayoutConfig {
  sidebarCollapsed: boolean;
  density: LayoutDensity;
}

export interface ThemeConfig {
  mode: ThemeMode;
}

export interface PresetsConfig {
  // Per-screen view presets, opaque to the shell — a screen WP owns the meaning
  // of its own entries, the shell only round-trips them through REST.
  viewPresets: Record<string, unknown>;
}

// The arms an end effector can be fitted to, in the backend's order
// (backend.endeffector.rig.SIDES).
export type ArmSide = "left" | "right";
export const ARM_SIDES: readonly ArmSide[] = ["left", "right"];

// What an arm carries until the operator says otherwise: the tool with NO motor
// on CAN id 0x08 (backend.endeffector.DEFAULT_TOOL_ID). The asymmetry is
// deliberate — defaulting to a gripper on a rig that has none makes the arm
// address a motor nobody answers for, which walks the controller to ERROR-PASSIVE
// and degrades the seven joints that ARE present; defaulting this way costs one
// refused gripper command and a message.
export const DEFAULT_TOOL_ID = "fixed_spatula";

// A measured mass is strictly above this. Zero is refused rather than read as
// weightless: an unmeasured tool is null.
const TOOL_MASS_FLOOR_KG = 0;

export interface ArmEndEffector {
  // An id the BACKEND registry knows. Only the shape is checked here: which ids
  // exist is the backend's answer (GET /api/config/tools) and the registry is
  // open, so a browser-side allowlist would reject a tool that was registered
  // after this bundle was built.
  toolId: string;
  // Kilograms, or null for unmeasured. Mass cannot be read with torque off, so
  // null is a steady state and gates nothing on this side.
  toolMassKg: number | null;
}

export interface EndEffectorConfig {
  left: ArmEndEffector;
  right: ArmEndEffector;
}

export interface RuntimeConfig {
  layout: LayoutConfig;
  theme: ThemeConfig;
  presets: PresetsConfig;
  endEffector: EndEffectorConfig;
}

export type ConfigSubobjectKey = keyof RuntimeConfig;

interface SubobjectSpec<T> {
  validate: (value: unknown) => value is T;
  makeDefault: () => T;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const LAYOUT_SPEC: SubobjectSpec<LayoutConfig> = {
  validate: (value): value is LayoutConfig =>
    isObject(value) &&
    typeof value.sidebarCollapsed === "boolean" &&
    (value.density === "comfortable" || value.density === "compact"),
  makeDefault: () => ({ sidebarCollapsed: false, density: "comfortable" }),
};

const THEME_SPEC: SubobjectSpec<ThemeConfig> = {
  validate: (value): value is ThemeConfig =>
    isObject(value) &&
    (value.mode === "light" || value.mode === "dark" || value.mode === "system"),
  makeDefault: () => ({ mode: "system" }),
};

const PRESETS_SPEC: SubobjectSpec<PresetsConfig> = {
  validate: (value): value is PresetsConfig => isObject(value) && isObject(value.viewPresets),
  makeDefault: () => ({ viewPresets: {} }),
};

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

// A mass is null (unmeasured) or a finite positive number. Zero, a negative, a
// NaN and an absent field are all refused: each would otherwise travel on as a
// measurement the rig never took.
function isToolMassKg(value: unknown): value is number | null {
  if (value === null) {
    return true;
  }
  return typeof value === "number" && Number.isFinite(value) && value > TOOL_MASS_FLOOR_KG;
}

function isArmEndEffector(value: unknown): value is ArmEndEffector {
  return isObject(value) && isNonEmptyString(value.toolId) && isToolMassKg(value.toolMassKg);
}

function defaultArmEndEffector(): ArmEndEffector {
  return { toolId: DEFAULT_TOOL_ID, toolMassKg: null };
}

const END_EFFECTOR_SPEC: SubobjectSpec<EndEffectorConfig> = {
  validate: (value): value is EndEffectorConfig =>
    isObject(value) && isArmEndEffector(value.left) && isArmEndEffector(value.right),
  makeDefault: () => ({ left: defaultArmEndEffector(), right: defaultArmEndEffector() }),
};

// One spec per subobject. The key set is closed: an unknown top-level field in
// the incoming document is dropped, mirroring the backend's extra="forbid".
const CONFIG_SCHEMA: { [K in ConfigSubobjectKey]: SubobjectSpec<RuntimeConfig[K]> } = {
  layout: LAYOUT_SPEC,
  theme: THEME_SPEC,
  presets: PRESETS_SPEC,
  endEffector: END_EFFECTOR_SPEC,
};

const SUBOBJECT_KEYS = Object.keys(CONFIG_SCHEMA) as ConfigSubobjectKey[];

export function defaultConfig(): RuntimeConfig {
  return {
    layout: LAYOUT_SPEC.makeDefault(),
    theme: THEME_SPEC.makeDefault(),
    presets: PRESETS_SPEC.makeDefault(),
    endEffector: END_EFFECTOR_SPEC.makeDefault(),
  };
}

export interface ParsedConfig {
  config: RuntimeConfig;
  // Subobjects that arrived malformed and were replaced by their defaults. Empty
  // when the incoming document validated whole.
  defaulted: ConfigSubobjectKey[];
}

// Parse a raw config document with per-subobject blast-radius isolation: a
// malformed subobject defaults on its own, the rest are kept verbatim.
export function parseConfig(raw: unknown): ParsedConfig {
  const source = isObject(raw) ? raw : {};
  const config = defaultConfig();
  const defaulted: ConfigSubobjectKey[] = [];

  for (const key of SUBOBJECT_KEYS) {
    const spec = CONFIG_SCHEMA[key];
    const incoming = source[key];
    if (incoming === undefined) {
      continue;
    }
    if (spec.validate(incoming)) {
      // Typed by the validator's narrowing; assigned through a helper so the
      // per-key union stays sound.
      assignSubobject(config, key, incoming);
    } else {
      defaulted.push(key);
    }
  }

  return { config, defaulted };
}

function assignSubobject<K extends ConfigSubobjectKey>(
  target: RuntimeConfig,
  key: K,
  value: RuntimeConfig[K],
): void {
  target[key] = value;
}
