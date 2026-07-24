// The names-indexed channel resolution — the load-bearing rule of S-08 (CG-G-S08a/g).
//
// observation.state is ONE vector whose columns mix three units. Which column is
// `left_joint_1.pos` and which is `right_gripper.torque` is declared by the
// info.json `names` list, and it MOVES the instant `use_velocity_and_torque` toggles
// the state between its 24-dim (pos+vel+torque) and 8-dim (pos-only) shape. So a
// channel is only ever resolved by `stateNames.indexOf(name)` — a compiled-in column
// index would silently scramble every plot on that toggle (CG-G-S08a).
//
// The unit convention (.pos->deg, .vel->deg/s, .torque->Nm) is CTR-REC@v1's, consumed
// through the `names` suffixes exactly as the backend viewer does (backend/dataset/
// viewer/constants.py). `contract.test.ts` reads that backend constants file and
// asserts this mirror equals it, so a convention change fails the lane rather than
// drifting. `observation.effort` is deliberately absent — it is not a key that exists
// (CG-G-S08b), so nothing here names it.

import type { EpisodeSignals } from "./types";

// The per-motor channel suffixes and their display units (CTR-REC@v1, mirrored via
// the info.json name suffixes). A single state vector mixes all three, so an
// unlabelled plot misreads a torque as degrees — every axis label carries its unit.
export const POSITION_SUFFIX = ".pos";
export const VELOCITY_SUFFIX = ".vel";
export const TORQUE_SUFFIX = ".torque";

export const POSITION_UNIT = "deg";
export const VELOCITY_UNIT = "deg/s";
export const TORQUE_UNIT = "Nm";

// Ordered longest-suffix-first is unnecessary here (the three suffixes share no
// prefix), but the map is the single source both `unitForChannel` and the contract
// mirror read, so the convention lives in exactly one place.
export const SUFFIX_UNITS: ReadonlyArray<readonly [string, string]> = [
  [POSITION_SUFFIX, POSITION_UNIT],
  [VELOCITY_SUFFIX, VELOCITY_UNIT],
  [TORQUE_SUFFIX, TORQUE_UNIT],
];

// Shown when a channel name carries no recognised suffix — never silently blank, so a
// missing unit is visible rather than mistaken for dimensionless (backend UNKNOWN_UNIT).
export const UNKNOWN_UNIT = "?";

// Return a channel's display unit from its name suffix.
export function unitForChannel(name: string): string {
  for (const [suffix, unit] of SUFFIX_UNITS) {
    if (name.endsWith(suffix)) {
      return unit;
    }
  }
  return UNKNOWN_UNIT;
}

// Return a channel's axis label with its bracketed unit, e.g. `left_joint_1.pos [deg]`
// — the per-channel unit annotation a mixed-unit state vector needs (CG-G-S08g).
export function axisLabel(name: string): string {
  return `${name} [${unitForChannel(name)}]`;
}

// Raised when a channel name is asked for that the dataset's `names` list does not
// carry — surfaced rather than returning a wrong column (which is exactly what a fixed
// index would do after the dimension toggles).
export class ChannelResolutionError extends Error {
  readonly channel: string;

  constructor(channel: string) {
    super(`'${channel}' is not an observation.state channel of this dataset`);
    this.name = "ChannelResolutionError";
    this.channel = channel;
  }
}

// One resolved channel series: the per-frame values pulled by the `names` index, plus
// the channel's unit for the axis label.
export interface ChannelSeries {
  name: string;
  values: readonly number[];
  unit: string;
}

// Resolve one observation.state channel's series by its `names` index — the only
// permitted access (CG-G-S08a). The column is `signals.stateNames.indexOf(name)`,
// computed per dataset, so the same channel name lands on the right column whether the
// dataset is 8-dim or 24-dim.
export function resolveStateChannel(signals: EpisodeSignals, name: string): ChannelSeries {
  const index = signals.stateNames.indexOf(name);
  if (index < 0) {
    throw new ChannelResolutionError(name);
  }
  const values = signals.state.map((frame) => frame[index]);
  return { name, values, unit: unitForChannel(name) };
}
