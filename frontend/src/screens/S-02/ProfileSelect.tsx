// Profile select (FR-GUI-112, 02 §2 import/export). Lists the robot profiles for
// the chosen side and reports the operator's selection upward. Profiles are the
// backend's; editing gains/limits is S-03's job, not this screen's — here they are
// only chosen. With no side chosen there is nothing to filter to, so the control
// is inert and says so.

import { canProceedWithSide, followerSidesFor, type SideSelection } from "./sideSelection";
import type { RobotProfile } from "./connectionSource";

interface ProfileSelectProps {
  profiles: readonly RobotProfile[];
  side: SideSelection;
  selectedProfile: string | null;
  onSelect: (name: string) => void;
}

function profileMatchesSide(profile: RobotProfile, side: SideSelection): boolean {
  if (!canProceedWithSide(side)) {
    return false;
  }
  if (side === "bimanual") {
    return profile.side === "bimanual";
  }
  return profile.side === side || followerSidesFor(side).includes(profile.side as "left" | "right");
}

export function ProfileSelect({ profiles, side, selectedProfile, onSelect }: ProfileSelectProps) {
  const chosen = canProceedWithSide(side);
  const applicable = profiles.filter((profile) => profileMatchesSide(profile, side));

  return (
    <section
      className="oa-s02-profile"
      aria-labelledby="oa-s02-profile-title"
      data-panel="profile"
    >
      <h2 id="oa-s02-profile-title" className="oa-s02__panel-title">
        프로파일 선택
      </h2>

      {!chosen ? (
        <p role="status">side를 먼저 선택하면 해당 팔의 프로파일이 표시됩니다.</p>
      ) : applicable.length === 0 ? (
        <p role="status">선택한 side에 맞는 프로파일이 없습니다.</p>
      ) : (
        <ul className="oa-s02-profile__list">
          {applicable.map((profile) => (
            <li key={profile.name}>
              <label>
                <input
                  type="radio"
                  name="oa-s02-profile"
                  value={profile.name}
                  checked={selectedProfile === profile.name}
                  onChange={() => onSelect(profile.name)}
                />
                {`${profile.name} (${profile.side})`}
              </label>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
