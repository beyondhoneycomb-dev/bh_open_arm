// Home panel (WP-G-S04). Two home definitions exist and are physically different
// poses (§2.10), so the active profile's NAME and TARGET pose are shown before
// execution (CG-G-S04j) — an operator must never press Home not knowing which pose
// it drives to. The backend pre-verifies the whole return trajectory (FR-MAN-048);
// the screen disables execute when that verdict fails (CG-G-S04h) and renders the
// first violation, but runs no collision check itself.

import { PreVerifyReport } from "./PreVerifyReport";
import type { ManualCommand } from "./commands";
import type { ArmSide, HomeStatus } from "./manualSource";

export interface HomePanelProps {
  home: HomeStatus;
  side: ArmSide;
  activeProfileId: string;
  onProfileChange: (id: string) => void;
  canMove: boolean;
  onCommand: (command: ManualCommand) => void;
}

export function HomePanel({
  home,
  side,
  activeProfileId,
  onProfileChange,
  canMove,
  onCommand,
}: HomePanelProps) {
  const profile = home.profiles.find((candidate) => candidate.id === activeProfileId) ?? null;
  const executable = canMove && home.preVerify.passed && profile !== null;

  function execute(): void {
    if (executable && profile) {
      onCommand({ op: "home_execute", profileId: profile.id, side });
    }
  }

  return (
    <section className="oa-man-home" aria-labelledby="oa-man-home-title">
      <h2 id="oa-man-home-title">홈 복귀</h2>

      <label className="oa-man-home__select">
        홈 프로파일
        <select value={activeProfileId} onChange={(event) => onProfileChange(event.target.value)}>
          {home.profiles.map((candidate) => (
            <option key={candidate.id} value={candidate.id}>
              {candidate.name}
            </option>
          ))}
        </select>
      </label>

      {profile && (
        <div className="oa-man-home__preview" data-field="home-preview">
          <p data-field="home-profile-name">활성 프로파일: {profile.name}</p>
          <p data-field="home-target-pose" data-unit="rad">
            목표 자세 (rad): [{profile.targetRad.map((value) => value.toFixed(4)).join(", ")}]
          </p>
          {profile.note && (
            <p className="oa-man-home__warn" role="alert">
              {profile.note}
            </p>
          )}
        </div>
      )}

      <PreVerifyReport report={home.preVerify} label="홈 궤적 사전 검증" />

      <button
        type="button"
        className="oa-man-home__execute"
        data-field="home-execute"
        disabled={!executable}
        onClick={execute}
      >
        홈 복귀 실행
      </button>
    </section>
  );
}
