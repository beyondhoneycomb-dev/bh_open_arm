// Dummy-mode banner (FR-GUI-070). When the backend runs without hardware (the
// enactic dummy node), every screen must carry a clear banner so an operator
// never mistakes simulated state for a live robot. Rendered only in dummy mode;
// returns null otherwise so the live UI stays uncluttered.

export interface DummyModeBannerProps {
  dummyMode: boolean;
}

export function DummyModeBanner({ dummyMode }: DummyModeBannerProps) {
  if (!dummyMode) {
    return null;
  }
  return (
    <div className="oa-dummy-banner" role="alert">
      더미 모드 — 하드웨어 없음. 표시 상태는 실제 로봇이 아닙니다.
    </div>
  );
}
