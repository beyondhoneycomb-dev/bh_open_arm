// The motor ERR-code reference: the seven Damiao fault nibbles (8,9,A,B,C,D,E),
// each rendered with its OA-MOT code and recovery hint (CG-G-S03g). The
// nibble→code identity is the frozen mirror in motorDomain; the message and
// recovery-hint text are read from the CTR-ERR registry the backend served — the
// browser reuses the registry and never authors the hint text.

import { motErrReference, type ErrorRegistryEntry } from "./motorDomain";

interface ErrorCodeReferenceProps {
  errorRegistry: Readonly<Record<string, ErrorRegistryEntry>>;
}

export function ErrorCodeReference({ errorRegistry }: ErrorCodeReferenceProps) {
  const entries = motErrReference(errorRegistry);
  return (
    <section className="oa-motors__panel" aria-labelledby="oa-motors-err-title">
      <h2 id="oa-motors-err-title" className="oa-motors__panel-title">
        ERR 코드 (모터 결함 7종)
      </h2>
      <div className="oa-motors__scroll">
        <table className="oa-motors__table">
          <thead>
            <tr>
              <th>Nibble</th>
              <th>코드</th>
              <th>의미</th>
              <th>복구 힌트</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.code} data-err-code={entry.code}>
                <td>{entry.nibble}</td>
                <td>{entry.code}</td>
                <td>{entry.message}</td>
                <td className="oa-motors__hint" data-recovery-hint={entry.code}>
                  {entry.recoveryHint}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
