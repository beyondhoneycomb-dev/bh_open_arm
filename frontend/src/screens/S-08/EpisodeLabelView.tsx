// The episode list with its success/fail labels (CG-G-S08d). The label is a SIDECAR
// attribute (WP-3B-12), not a parquet column, and the screen reads it as one: the
// automatic suggestion and the human verdict are both shown, the human's governs when
// present, and a disagreement is flagged. The screen never fabricates a verdict — an
// episode the backend has not judged reads as unlabelled, and a crash-recovered
// episode held for judgment reads as pending. Rendering a verdict emits a set_verdict
// intent; the backend's label store persists it (with_manual), the screen only asks.

import type { EpisodeLabel, EpisodeSummary, Judgment } from "./types";

export interface EpisodeLabelViewProps {
  episodes: readonly EpisodeSummary[];
  selectedEpisodeIndex: number;
  onSelectEpisode: (episodeIndex: number) => void;
  onSetVerdict: (episodeIndex: number, verdict: "success" | "fail") => void;
}

const STATUS_LABELS: Record<EpisodeLabel["status"], string> = {
  judged: "판정됨",
  pending_judgment: "판정 대기",
  aborted: "중단됨",
};

// The verdict that governs: the human's when present, else the auto suggestion, else
// none — read straight off the sidecar, not recomputed from data.
function effectiveVerdict(label: EpisodeLabel | null): Judgment["verdict"] | null {
  if (label === null) {
    return null;
  }
  if (label.manual !== null) {
    return label.manual.verdict;
  }
  if (label.auto !== null) {
    return label.auto.verdict;
  }
  return null;
}

function isConflicting(label: EpisodeLabel | null): boolean {
  return (
    label !== null &&
    label.auto !== null &&
    label.manual !== null &&
    label.auto.verdict !== label.manual.verdict
  );
}

function verdictText(verdict: Judgment["verdict"] | null): string {
  if (verdict === "success") {
    return "성공";
  }
  if (verdict === "fail") {
    return "실패";
  }
  return "미판정";
}

export function EpisodeLabelView({
  episodes,
  selectedEpisodeIndex,
  onSelectEpisode,
  onSetVerdict,
}: EpisodeLabelViewProps) {
  return (
    <section className="oa-ds__labels" aria-labelledby="oa-ds-labels-title">
      <h2 id="oa-ds-labels-title" className="oa-ds__section-title">
        에피소드 라벨
      </h2>
      <ul className="oa-ds__label-list">
        {episodes.map((episode) => {
          const label = episode.label;
          const effective = effectiveVerdict(label);
          const selected = episode.episodeIndex === selectedEpisodeIndex;
          return (
            <li
              key={episode.episodeIndex}
              className="oa-ds__label-row"
              data-selected={selected}
              data-testid={`episode-${episode.episodeIndex}`}
            >
              <button
                type="button"
                className="oa-ds__label-select"
                aria-pressed={selected}
                onClick={() => onSelectEpisode(episode.episodeIndex)}
              >
                에피소드 {episode.episodeIndex} · {episode.length} 프레임
              </button>

              <span className="oa-ds__label-status" data-status={label?.status ?? "unlabelled"}>
                {label === null ? "미판정" : STATUS_LABELS[label.status]}
              </span>

              <span
                className="oa-ds__label-effective"
                data-verdict={effective ?? "none"}
                data-testid={`verdict-${episode.episodeIndex}`}
              >
                {verdictText(effective)}
              </span>

              <span className="oa-ds__label-provenance">
                auto: {verdictText(label?.auto?.verdict ?? null)} · manual:{" "}
                {verdictText(label?.manual?.verdict ?? null)}
              </span>

              {isConflicting(label) && (
                <span
                  className="oa-ds__label-conflict"
                  role="status"
                  data-testid={`conflict-${episode.episodeIndex}`}
                >
                  자동↔수동 불일치
                </span>
              )}

              <span className="oa-ds__label-verdict-set">
                <button
                  type="button"
                  className="oa-ds__label-btn oa-ds__label-btn--success"
                  onClick={() => onSetVerdict(episode.episodeIndex, "success")}
                >
                  성공 판정
                </button>
                <button
                  type="button"
                  className="oa-ds__label-btn oa-ds__label-btn--fail"
                  onClick={() => onSetVerdict(episode.episodeIndex, "fail")}
                >
                  실패 판정
                </button>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
