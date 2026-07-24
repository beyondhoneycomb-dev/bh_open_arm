// The lineage viewer (WP-4A-05, FR-TRN-054, FR-GUI-127). It renders the backend
// `LineageRecord`'s eight immutable elements (a)-(h) as-is and offers the bidirectional
// query: the per-source episode-index map (source episode -> merged episode) and the
// union of merged indices this run consumed (the axis the reverse checkpoint->episode
// query keys on). It synthesises no element and edits nothing — the record is an
// immutable snapshot, and the screen is a reader of it.

import type { LineageRecord } from "./types";

export interface LineageViewProps {
  lineage: LineageRecord | null;
}

// The merged-dataset episode indices this run consumed: the union of every merge map's
// target values, ascending and unique — element (c) presented, not a second source.
function consumedEpisodes(lineage: LineageRecord): number[] {
  const merged = new Set<number>();
  for (const entry of lineage.mergeHistory) {
    for (const target of Object.values(entry.episodeIndexMap)) {
      merged.add(target);
    }
  }
  return [...merged].sort((a, b) => a - b);
}

export function LineageView({ lineage }: LineageViewProps) {
  if (lineage === null) {
    return (
      <section className="oa-trn__panel" aria-labelledby="oa-trn-lineage-title" data-testid="lineage">
        <h2 id="oa-trn-lineage-title" className="oa-trn__section-title">
          계보
        </h2>
        <p data-testid="lineage-empty">선택된 실행의 계보 레코드가 없습니다.</p>
      </section>
    );
  }

  const consumed = consumedEpisodes(lineage);

  return (
    <section className="oa-trn__panel" aria-labelledby="oa-trn-lineage-title" data-testid="lineage">
      <h2 id="oa-trn-lineage-title" className="oa-trn__section-title">
        계보 (불변 스냅샷 · 8요소)
      </h2>

      <dl className="oa-trn__lineage">
        <dt>(a) 데이터셋</dt>
        <dd data-testid="lineage-dataset">
          {lineage.dataset.repoId} · {lineage.dataset.revision}
          <span className="oa-trn__muted"> · info {lineage.dataset.infoHash} · stats {lineage.dataset.statsHash}</span>
        </dd>

        <dt>(b) 관측 구성</dt>
        <dd data-testid="lineage-observation">
          use_velocity_and_torque={String(lineage.observation.useVelocityAndTorque)} · state{" "}
          {lineage.observation.stateShape} · action {lineage.observation.actionShape} · names{" "}
          {lineage.observation.names.length}개
        </dd>

        <dt>(c) 세션 병합 이력 · 원본 id ↔ episode_index</dt>
        <dd data-testid="lineage-merge">
          <table className="oa-trn__merge-table">
            <thead>
              <tr>
                <th scope="col">원본 세션</th>
                <th scope="col">원본 → 병합 episode_index</th>
              </tr>
            </thead>
            <tbody>
              {lineage.mergeHistory.map((entry) => (
                <tr key={entry.sourceSession} data-testid={`lineage-merge-${entry.sourceSession}`}>
                  <td>{entry.sourceSession}</td>
                  <td>
                    {Object.entries(entry.episodeIndexMap)
                      .map(([source, merged]) => `${source}→${merged}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="oa-trn__muted" data-testid="lineage-consumed">
            소비된 병합 episode_index: [{consumed.join(", ")}]
          </p>
        </dd>

        <dt>(d) train_config.json (전문)</dt>
        <dd>
          <pre className="oa-trn__log" data-testid="lineage-train-config">
            {JSON.stringify(lineage.trainConfig, null, 2)}
          </pre>
        </dd>

        <dt>(e)-(g) 버전 핀</dt>
        <dd data-testid="lineage-pins">
          code {lineage.pins.codeSha} · lerobot {lineage.pins.lerobotVersion} · container{" "}
          {lineage.pins.containerDigest}
        </dd>

        <dt>(h) 퇴화 채널 결정</dt>
        <dd data-testid="lineage-decisions">
          {lineage.degenerateDecisions.length === 0 ? (
            "검사 완료 · 퇴화 채널 없음"
          ) : (
            <ul>
              {lineage.degenerateDecisions.map((decision) => (
                <li key={`${decision.finding.channelName}-${decision.finding.normMode}`}>
                  {decision.finding.channelName} ({decision.finding.normMode}) → {decision.choice}
                  <span className="oa-trn__muted"> — {decision.rationale}</span>
                </li>
              ))}
            </ul>
          )}
        </dd>
      </dl>
    </section>
  );
}
