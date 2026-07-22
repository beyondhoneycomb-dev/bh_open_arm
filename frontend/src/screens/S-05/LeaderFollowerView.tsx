// The leader-vs-follower 3D view (13 §2.6 S-05 main view). The follower is the robot
// the shared viewport renders (WP-G-02); the leader is the VR controller whose
// tracking validity gates whether following is possible at all. The shared viewport
// owns the scene, coordinate transform and stale gating — this view embeds it and
// annotates the leader side; it renders no 3D and transforms no pose itself.

import { ViewportPanel } from "../../viewport";

import type { LeaderStatus, TeleopSource } from "./teleopSource";

function leaderLine(leader: LeaderStatus): string {
  return `${leader.arm} 리더 — tracking ${leader.trackingValidity} · grip ${leader.gripValue.toFixed(2)}`;
}

interface LeaderFollowerViewProps {
  source: TeleopSource;
}

export function LeaderFollowerView({ source }: LeaderFollowerViewProps) {
  return (
    <section className="oa-tel__leaderfollower" aria-label="리더 vs 팔로워 3D">
      <h2 className="oa-tel__h2">리더 vs 팔로워 (3D)</h2>

      <ul className="oa-tel__leaders" aria-label="리더(VR 컨트롤러) 상태">
        {source.leaders.map((leader) => (
          <li key={leader.arm} data-field="leader" data-arm={leader.arm}>
            {leaderLine(leader)}
          </li>
        ))}
      </ul>

      <div className="oa-tel__follower" aria-label="팔로워 (로봇) 3D 뷰">
        <p className="oa-tel__hint">팔로워 (로봇) — 공유 뷰포트</p>
        <ViewportPanel source={source.viewport} />
      </div>
    </section>
  );
}
