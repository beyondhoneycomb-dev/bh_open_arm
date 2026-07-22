// CG-G-S07g: the storage prediction is shown, and a headroom under one hour raises
// the start-blocked notice. The view reads the backend-supplied `headroomHours`;
// the block threshold is the shared global DISK_MIN_HEADROOM_HOURS.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StoragePredictionView } from "./StoragePredictionView";
import type { StoragePrediction } from "./types";

const GIB = 1024 * 1024 * 1024;

function storage(headroomHours: number): StoragePrediction {
  return {
    freeBytes: 100 * GIB,
    totalBytes: 500 * GIB,
    bytesPerHour: 20 * GIB,
    headroomHours,
  };
}

describe("StoragePredictionView (CG-G-S07g)", () => {
  it("shows the prediction with the predicted headroom", () => {
    render(<StoragePredictionView storage={storage(5)} />);
    expect(screen.getByTestId("storage-prediction")).toBeInTheDocument();
    expect(screen.getByTestId("storage-headroom")).toHaveTextContent("5.00");
  });

  it("raises the start-blocked notice below one hour of headroom", () => {
    render(<StoragePredictionView storage={storage(0.5)} />);
    expect(screen.getByTestId("storage-block")).toBeInTheDocument();
  });

  it("shows no block at or above one hour", () => {
    render(<StoragePredictionView storage={storage(1)} />);
    expect(screen.queryByTestId("storage-block")).toBeNull();
  });
});
