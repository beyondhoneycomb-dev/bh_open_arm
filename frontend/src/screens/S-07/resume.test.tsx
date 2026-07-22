// CG-G-S07e: an interrupted session Resumes via its STAMPED repo_id, unchanged. The
// resume intent carries exactly the stamped id the backend detected — no re-stamp.

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResumeView } from "./ResumeView";
import type { ResumableSession } from "./types";

const SESSION: ResumableSession = {
  stampedRepoId: "openarm/pick_place_20260723_061500",
  recordedEpisodes: 12,
  reason: "crash-footerless-parquet",
  requiresUserJudgment: true,
};

describe("ResumeView (CG-G-S07e)", () => {
  it("resumes with the exact stamped repo_id", () => {
    const onResume = vi.fn();
    render(<ResumeView sessions={[SESSION]} onResume={onResume} />);
    expect(screen.getByTestId("resume-id")).toHaveTextContent(SESSION.stampedRepoId);
    fireEvent.click(screen.getByRole("button", { name: "재개" }));
    expect(onResume).toHaveBeenCalledWith(SESSION.stampedRepoId);
  });

  it("shows an empty state when there is nothing to resume", () => {
    render(<ResumeView sessions={[]} onResume={vi.fn()} />);
    expect(screen.getByTestId("resume-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("resume-row")).toBeNull();
  });
});
