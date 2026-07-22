// CG-G-S07b: the dataset name shown is the backend `stamp_repo_id()` result, never
// the operator's raw input. The name display carries the stamped id; the raw
// request appears only as labelled context, so it can never be mistaken for the name.

import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DatasetIdentityView } from "./DatasetIdentityView";

const REQUESTED = "openarm/pick_place";
const STAMPED = "openarm/pick_place_20260723_061500";

describe("DatasetIdentityView (CG-G-S07b)", () => {
  it("shows the stamped repo_id as the dataset name", () => {
    render(<DatasetIdentityView dataset={{ requestedRepoId: REQUESTED, stampedRepoId: STAMPED }} />);
    const name = screen.getByTestId("dataset-name");
    expect(name).toHaveTextContent(STAMPED);
  });

  it("never renders the raw request AS the name", () => {
    render(<DatasetIdentityView dataset={{ requestedRepoId: REQUESTED, stampedRepoId: STAMPED }} />);
    const name = screen.getByTestId("dataset-name");
    // The name element carries the stamped id, whose text differs from the bare
    // request; the request shows only inside its own labelled context.
    expect(name.textContent).not.toBe(REQUESTED);
    const request = screen.getByTestId("dataset-request");
    expect(request).toHaveTextContent(REQUESTED);
    expect(request).toHaveTextContent("스탬프 부착됨");
  });

  it("omits the request context when nothing was stamped onto it", () => {
    render(<DatasetIdentityView dataset={{ requestedRepoId: STAMPED, stampedRepoId: STAMPED }} />);
    expect(screen.queryByTestId("dataset-request")).toBeNull();
    expect(screen.getByTestId("dataset-name")).toHaveTextContent(STAMPED);
  });
});
