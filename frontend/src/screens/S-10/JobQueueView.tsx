// The job queue / execution list (FR-GUI-120, CG-G-S10h). One row per job showing the
// FR-GUI-120 fields — id, name, policy, dataset+revision, requested GPUs, state, times,
// output — with filter, sort and cancel controls. The screen renders the backend's job
// set and emits filter/cancel intent; it never sorts or filters a second truth (the
// backend `apply_filter` is canon). A GPU-absent QUEUED job carries a DISTINCT badge (a
// "waiting for GPU" pill) from an about-to-preflight one (a "waiting for validation"
// pill), so a job stuck because no GPU is free is never mistaken for one next in line.

import type { JobQuery, JobState, JobSummary, QueuedReason } from "./types";
import { JOB_STATES } from "./types";

export interface JobQueueViewProps {
  jobs: readonly JobSummary[];
  query: JobQuery;
  onQuery: (query: JobQuery) => void;
  onCancel: (jobId: string) => void;
}

const QUEUED_REASON_LABEL: Readonly<Record<QueuedReason, string>> = {
  awaiting_gpu: "GPU 대기",
  awaiting_preflight: "검증 대기",
};

const CANCELLABLE_STATES: ReadonlySet<JobState> = new Set<JobState>([
  "QUEUED",
  "PREFLIGHT",
  "RUNNING",
]);

// The state pill text. A QUEUED job appends its wait reason so the two waits read
// differently (CG-G-S10h); every other state shows the state name alone.
function stateLabel(job: JobSummary): string {
  if (job.state === "QUEUED" && job.queuedReason !== null) {
    return `QUEUED · ${QUEUED_REASON_LABEL[job.queuedReason]}`;
  }
  return job.state;
}

function formatTime(iso: string | null): string {
  return iso ?? "—";
}

export function JobQueueView({ jobs, query, onQuery, onCancel }: JobQueueViewProps) {
  function toggleState(state: JobState): void {
    const has = query.states.includes(state);
    const states = has
      ? query.states.filter((other) => other !== state)
      : [...query.states, state];
    onQuery({ ...query, states });
  }

  return (
    <section className="oa-trn__panel" aria-labelledby="oa-trn-jobs-title" data-testid="job-queue">
      <h2 id="oa-trn-jobs-title" className="oa-trn__section-title">
        잡 큐 / 실행 목록
      </h2>

      <div className="oa-trn__jobs-controls">
        <label className="oa-trn__field">
          <span>이름 필터</span>
          <input
            type="text"
            value={query.nameContains}
            data-testid="job-name-filter"
            onChange={(event) => onQuery({ ...query, nameContains: event.target.value })}
          />
        </label>

        <label className="oa-trn__field">
          <span>정렬</span>
          <select
            value={query.sortBy}
            data-testid="job-sort"
            onChange={(event) =>
              onQuery({ ...query, sortBy: event.target.value as JobQuery["sortBy"] })
            }
          >
            <option value="created">생성 시각</option>
            <option value="name">이름</option>
            <option value="state">상태</option>
          </select>
        </label>

        <button
          type="button"
          className="oa-trn__toggle"
          data-testid="job-sort-dir"
          aria-pressed={query.descending}
          onClick={() => onQuery({ ...query, descending: !query.descending })}
        >
          {query.descending ? "내림차순" : "오름차순"}
        </button>

        <div className="oa-trn__state-filters" role="group" aria-label="상태 필터">
          {JOB_STATES.map((state) => (
            <button
              key={state}
              type="button"
              className="oa-trn__chip"
              data-testid={`job-state-filter-${state}`}
              aria-pressed={query.states.includes(state)}
              onClick={() => toggleState(state)}
            >
              {state}
            </button>
          ))}
        </div>
      </div>

      <table className="oa-trn__jobs-table">
        <thead>
          <tr>
            <th scope="col">ID</th>
            <th scope="col">이름</th>
            <th scope="col">정책</th>
            <th scope="col">데이터셋 · revision</th>
            <th scope="col">GPU</th>
            <th scope="col">상태</th>
            <th scope="col">생성</th>
            <th scope="col">종료</th>
            <th scope="col">출력</th>
            <th scope="col">동작</th>
          </tr>
        </thead>
        <tbody>
          {jobs.map((job) => (
            <tr key={job.jobId} data-testid={`job-${job.jobId}`}>
              <td>{job.jobId}</td>
              <td>{job.name}</td>
              <td>{job.policyId}</td>
              <td>
                {job.datasetRepoId}
                <span className="oa-trn__muted"> · {job.datasetRevision}</span>
              </td>
              <td>{job.requestedGpus}</td>
              <td
                className="oa-trn__job-state"
                data-testid={`job-state-${job.jobId}`}
                data-state={job.state}
                data-queued-reason={job.queuedReason ?? ""}
              >
                {stateLabel(job)}
              </td>
              <td>{formatTime(job.createdIso)}</td>
              <td>{formatTime(job.endedIso)}</td>
              <td className="oa-trn__muted">{job.outputDir}</td>
              <td>
                {CANCELLABLE_STATES.has(job.state) && (
                  <button
                    type="button"
                    className="oa-trn__danger"
                    data-testid={`job-cancel-${job.jobId}`}
                    onClick={() => onCancel(job.jobId)}
                  >
                    취소
                  </button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
