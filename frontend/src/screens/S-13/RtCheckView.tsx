// RT / permission view (CG-G-S13b, CG-G-S13g). Shows the environment (PREEMPT_RT),
// each process's scheduling class / affinity / VmLck-derived mlockall verdict, and
// the backend-declared RT findings rendered through the frozen error registry. The
// mlockall status keys on VmLck, not the syscall return value.

import { ErrorEntryCard } from "./ErrorEntryCard";
import { lookupError } from "./errorLookup";
import { isRealtimeScheduled, mlockallLocked, mlockallSilentFailure, preemptRtAbsent } from "./rtCheck";
import type { ErrorRegistry, RtCheckData } from "./types";

interface RtCheckViewProps {
  rt: RtCheckData;
  registry: ErrorRegistry;
}

export function RtCheckView({ rt, registry }: RtCheckViewProps) {
  const preemptAbsent = preemptRtAbsent(rt.env);
  return (
    <section className="oa-sys-view" aria-labelledby="oa-sys-rt-title" data-testid="rt-check">
      <h2 id="oa-sys-rt-title" className="oa-sys-view__title">
        RT · 권한 점검
      </h2>

      <dl className="oa-sys-env" data-testid="rt-env">
        <dt>커널</dt>
        <dd>{rt.env.kernelRelease}</dd>
        <dt>PREEMPT_RT</dt>
        <dd data-testid="rt-preempt" data-present={!preemptAbsent}>
          {preemptAbsent ? "부재" : "존재"}
        </dd>
        <dt>Python</dt>
        <dd>{rt.env.pythonVersion}</dd>
      </dl>

      <table className="oa-sys-table" data-testid="rt-process-table">
        <thead>
          <tr>
            <th scope="col">프로세스</th>
            <th scope="col">스케줄 정책</th>
            <th scope="col">우선순위</th>
            <th scope="col">CPU 어피니티</th>
            <th scope="col">VmLck (kB)</th>
            <th scope="col">mlockall</th>
          </tr>
        </thead>
        <tbody>
          {rt.processes.map((proc) => {
            const locked = mlockallLocked(proc);
            const silent = mlockallSilentFailure(proc);
            return (
              <tr
                key={proc.pid}
                data-testid={`rt-proc-${proc.pid}`}
                data-realtime={isRealtimeScheduled(proc)}
                data-mlockall-locked={locked}
                data-mlockall-silent-failure={silent}
              >
                <td>
                  {proc.name} ({proc.pid})
                </td>
                <td>{proc.schedPolicy}</td>
                <td>{proc.schedPriority}</td>
                <td>{proc.cpuAffinity.join(",")}</td>
                <td data-testid={`rt-vmlck-${proc.pid}`}>{proc.vmlckKb}</td>
                <td data-testid={`rt-mlockall-${proc.pid}`}>
                  {locked ? "잠김" : "미잠김"}
                  {silent && (
                    <span className="oa-sys-alert" role="alert" data-testid={`rt-silent-${proc.pid}`}>
                      {" "}
                      반환값은 성공이나 VmLck=0 — 조용한 실패
                    </span>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>

      {preemptAbsent && (
        <div className="oa-sys-warn" data-testid="rt-preempt-remedy">
          <p>PREEMPT_RT 부재 — 아래 코드와 해결 방법을 확인하세요.</p>
          {rt.findings.map((finding) => {
            const entry = lookupError(registry, finding.code);
            return entry ? (
              <ErrorEntryCard key={finding.code} entry={entry} />
            ) : (
              <p key={finding.code} data-testid={`rt-finding-unresolved-${finding.code}`}>
                {finding.code}
                {finding.note ? ` — ${finding.note}` : ""}
              </p>
            );
          })}
        </div>
      )}
    </section>
  );
}
