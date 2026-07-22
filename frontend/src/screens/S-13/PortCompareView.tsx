// Port-compare view (CG-G-S13a, CG-G-S13d). Renders the backend-served canon
// diffed against the actual bindings. It shows discrepancies, never resolves
// them, and holds no port of its own — the numbers come entirely from props.

import { comparePorts, isDiscrepant, type PortRowStatus } from "./portCompare";
import type { ActualBinding, CanonPortEntry } from "./types";

interface PortCompareViewProps {
  canon: CanonPortEntry[];
  actual: ActualBinding[];
}

const STATUS_LABEL: Record<PortRowStatus, string> = {
  match: "일치",
  mismatch: "불일치",
  unbound: "미바인딩",
  unexpected: "미등재 바인딩",
  no_port: "포트 없음",
};

function portText(value: number | null): string {
  return value === null ? "—" : String(value);
}

export function PortCompareView({ canon, actual }: PortCompareViewProps) {
  const comparison = comparePorts(canon, actual);
  return (
    <section
      className="oa-sys-view"
      aria-labelledby="oa-sys-ports-title"
      data-testid="port-compare"
      data-has-mismatch={comparison.hasMismatch}
    >
      <h2 id="oa-sys-ports-title" className="oa-sys-view__title">
        포트 대조 — 정본 01 §2.17 + 14 §2.1
      </h2>
      <p className="oa-sys-view__note">
        포트맵 정본은 백엔드가 소유한다(13 §2.7). 이 뷰는 정본과 실제 바인딩을 대조만 한다.
      </p>

      {comparison.hasMismatch ? (
        <p className="oa-sys-alert" role="alert" data-testid="port-mismatch-alert">
          정본과 실제 바인딩이 불일치합니다.
        </p>
      ) : (
        <p className="oa-sys-ok" role="status" data-testid="port-match-ok">
          모든 바인딩이 정본과 일치합니다.
        </p>
      )}

      {comparison.clashes.length > 0 && (
        <ul className="oa-sys-alert" role="alert" data-testid="port-clashes">
          {comparison.clashes.map((clash) => (
            <li key={clash.port} data-testid={`port-clash-${clash.port}`}>
              포트 충돌: {clash.components.join(", ")} 가 동일 포트를 점유
            </li>
          ))}
        </ul>
      )}

      <table className="oa-sys-table">
        <thead>
          <tr>
            <th scope="col">컴포넌트</th>
            <th scope="col">프로토콜</th>
            <th scope="col">정본 포트</th>
            <th scope="col">실제 포트</th>
            <th scope="col">판정</th>
          </tr>
        </thead>
        <tbody>
          {comparison.rows.map((row) => (
            <tr
              key={row.component}
              data-testid={`port-row-${row.component}`}
              data-status={row.status}
              data-discrepant={isDiscrepant(row.status)}
            >
              <td>{row.component}</td>
              <td>{row.protocol ?? "—"}</td>
              <td>{portText(row.canonPort)}</td>
              <td>{portText(row.actualPort)}</td>
              <td>{STATUS_LABEL[row.status]}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
