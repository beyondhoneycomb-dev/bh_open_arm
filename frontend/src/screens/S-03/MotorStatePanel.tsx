// Per-motor live state: MOSFET/coil temperature and the current ERR nibble. Every
// value here rode in on the WS state frame (03 §2.6) — there is no temperature
// poll, no request path (CG-G-S03b). The current fault, if any, is mapped through
// the frozen nibble→code mirror and its recovery hint read from the CTR-ERR
// registry (the same reuse as the reference view).

import {
  MOT_DISABLE_NIBBLE,
  MOT_ENABLE_NIBBLE,
  isFaultNibble,
  motErrCodeForNibble,
  type ErrorRegistryEntry,
  type MotorRuntimeState,
} from "./motorDomain";

interface MotorStatePanelProps {
  motorStates: readonly MotorRuntimeState[];
  errorRegistry: Readonly<Record<string, ErrorRegistryEntry>>;
}

function temp(value: number): string {
  return Number.isNaN(value) ? "—" : `${value} °C`;
}

function faultLabel(
  nibble: string,
  errorRegistry: Readonly<Record<string, ErrorRegistryEntry>>,
): string {
  if (nibble === MOT_DISABLE_NIBBLE) {
    return "Disable";
  }
  if (nibble === MOT_ENABLE_NIBBLE) {
    return "Enable (정상)";
  }
  const code = motErrCodeForNibble(nibble);
  if (!code) {
    return `미상 nibble ${nibble}`;
  }
  const entry = errorRegistry[code];
  return entry ? `${code} — ${entry.recoveryHint}` : code;
}

export function MotorStatePanel({ motorStates, errorRegistry }: MotorStatePanelProps) {
  return (
    <section className="oa-motors__panel" aria-labelledby="oa-motors-state-title">
      <h2 id="oa-motors-state-title" className="oa-motors__panel-title">
        모터 상태 · 온도 (상태 프레임)
      </h2>
      {motorStates.length === 0 ? (
        <p className="oa-motors__hint" role="status">
          상태 프레임 미수신 (awaiting state frame)
        </p>
      ) : (
        <div className="oa-motors__scroll">
          <table className="oa-motors__table">
            <thead>
              <tr>
                <th>관절</th>
                <th>T_MOS</th>
                <th>T_Rotor</th>
                <th>현재 ERR</th>
              </tr>
            </thead>
            <tbody>
              {motorStates.map((state) => {
                const fault = isFaultNibble(state.errNibble);
                return (
                  <tr
                    key={state.jointName}
                    data-motor-state={state.jointName}
                    className={fault ? "oa-motors__err-row--fault" : undefined}
                  >
                    <td>{state.jointName}</td>
                    <td data-temp-mos>{temp(state.tempMosC)}</td>
                    <td data-temp-rotor>{temp(state.tempRotorC)}</td>
                    <td data-err-nibble={state.errNibble}>
                      {faultLabel(state.errNibble, errorRegistry)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
