// Unit tests for the names-indexed channel resolution (CG-G-S08a/g). The load-bearing
// case is the last one: the SAME channel name must resolve to the right column in both
// the 8-dim (pos-only) and 24-dim (pos+vel+torque) state families, so a fixed index
// — which would read a different physical quantity after the toggle — is provably
// wrong. If resolution used a constant column, this test would fail.

import { describe, expect, it } from "vitest";

import {
  ChannelResolutionError,
  axisLabel,
  resolveStateChannel,
  unitForChannel,
} from "./channels";
import type { EpisodeSignals } from "./types";

function signalsWith(stateNames: string[], state: number[][]): EpisodeSignals {
  const frames = state.length;
  return {
    episodeIndex: 0,
    timeAxis: {
      fps: 30,
      frameIndices: Array.from({ length: frames }, (_v, i) => i),
      timestamps: Array.from({ length: frames }, (_v, i) => i / 30),
      isWallClock: false,
      domainNote: "synthetic",
    },
    stateNames,
    actionNames: [],
    state,
    action: [],
  };
}

describe("unitForChannel / axisLabel (CG-G-S08g)", () => {
  it("maps each suffix to its CTR-REC unit", () => {
    expect(unitForChannel("left_joint_1.pos")).toBe("deg");
    expect(unitForChannel("left_joint_1.vel")).toBe("deg/s");
    expect(unitForChannel("left_gripper.torque")).toBe("Nm");
  });

  it("shows an explicit unknown unit rather than blanking", () => {
    expect(unitForChannel("weird_channel")).toBe("?");
  });

  it("annotates the axis label with the bracketed unit", () => {
    expect(axisLabel("right_joint_2.torque")).toBe("right_joint_2.torque [Nm]");
  });
});

describe("resolveStateChannel by names index (CG-G-S08a)", () => {
  it("pulls the column named, not a positional slot", () => {
    const signals = signalsWith(
      ["a.pos", "b.pos", "c.pos"],
      [
        [10, 20, 30],
        [11, 21, 31],
      ],
    );
    const series = resolveStateChannel(signals, "b.pos");
    expect(series.values).toEqual([20, 21]);
    expect(series.unit).toBe("deg");
  });

  it("raises on a channel the dataset does not carry", () => {
    const signals = signalsWith(["a.pos"], [[1]]);
    expect(() => resolveStateChannel(signals, "missing.pos")).toThrow(ChannelResolutionError);
  });

  it("resolves the SAME name correctly across an 8-dim <-> 24-dim toggle", () => {
    // pos-only (8-dim family, here 2 motors): the torque channel does not exist,
    // and a motor's .pos sits at a different column than in the full family.
    const posOnly = signalsWith(
      ["m0.pos", "m1.pos"],
      [
        [100, 200],
        [101, 201],
      ],
    );

    // pos+vel+torque (24-dim family, here 2 motors): every column has moved, and the
    // torque channel now exists. A fixed index tuned for either shape would read the
    // wrong physical quantity in the other.
    const full = signalsWith(
      ["m0.pos", "m0.vel", "m0.torque", "m1.pos", "m1.vel", "m1.torque"],
      [
        [100, 5, 0.4, 200, 6, 0.5],
        [101, 5, 0.41, 201, 6, 0.51],
      ],
    );

    // m1.pos is column 1 in the pos-only family and column 3 in the full family; both
    // must return the pos values, never the vel/torque that a frozen index would hit.
    expect(resolveStateChannel(posOnly, "m1.pos").values).toEqual([200, 201]);
    expect(resolveStateChannel(full, "m1.pos").values).toEqual([200, 201]);

    // The torque channel exists only in the full family and resolves to its own column.
    const torque = resolveStateChannel(full, "m0.torque");
    expect(torque.values).toEqual([0.4, 0.41]);
    expect(torque.unit).toBe("Nm");
    expect(() => resolveStateChannel(posOnly, "m0.torque")).toThrow(ChannelResolutionError);
  });
});
