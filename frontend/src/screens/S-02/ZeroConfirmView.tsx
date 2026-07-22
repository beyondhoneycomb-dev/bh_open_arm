// The explicit-zero confirm view (CG-G-S02d, FR-GUI-084). It REUSES the shared 3D
// viewport (WP-G-02) to show the current pose and, beside it, the per-joint
// current-vs-rest delta so the operator can judge whether the arm is at the URDF
// rest pose before an explicit set_zero. Both poses are backend radian numbers; the
// delta is a display subtraction (zeroConfirm.ts) and is shown in radians — the
// browser converts no units. The view invents no closeness gate: the operator
// judges, manually.

import { ViewportPanel, defaultViewportSource, type ViewportSource } from "../../viewport";
import { JOINT_ANGLE_UNIT, SET_ZERO_SESSION_NOTICE } from "./constants";
import { maxAbsDelta, perJointDelta } from "./zeroConfirm";

interface ZeroConfirmViewProps {
  jointNames: readonly string[];
  restPositionsRad: Readonly<Record<string, number>>;
  currentPositionsRad: Readonly<Record<string, number>> | null;
  nowMonoMs: number;
}

function radLabel(value: number): string {
  return Number.isFinite(value) ? `${value.toFixed(4)} ${JOINT_ANGLE_UNIT}` : "—";
}

function poseViewportSource(
  jointNames: readonly string[],
  currentPositionsRad: Readonly<Record<string, number>>,
  nowMonoMs: number,
): ViewportSource {
  const base = defaultViewportSource();
  return {
    ...base,
    expectedJointNames: jointNames,
    latestFrame: { positionsRad: currentPositionsRad, frameMonoMs: nowMonoMs },
    nowMonoMs,
  };
}

export function ZeroConfirmView({
  jointNames,
  restPositionsRad,
  currentPositionsRad,
  nowMonoMs,
}: ZeroConfirmViewProps) {
  const deltas = currentPositionsRad
    ? perJointDelta(currentPositionsRad, restPositionsRad, jointNames)
    : null;
  const worst = deltas ? maxAbsDelta(deltas) : Number.NaN;

  return (
    <section
      className="oa-s02-zero"
      aria-labelledby="oa-s02-zero-title"
      data-panel="zero-confirm"
    >
      <h2 id="oa-s02-zero-title" className="oa-s02__panel-title">
        영점 확인 (현재 자세 vs rest)
      </h2>

      <p className="oa-s02-zero__notice" role="note">
        {SET_ZERO_SESSION_NOTICE}
      </p>

      {currentPositionsRad ? (
        <div className="oa-s02-zero__compare">
          <ViewportPanel
            source={poseViewportSource(jointNames, currentPositionsRad, nowMonoMs)}
          />

          <table className="oa-s02-zero__deltas" data-table="joint-delta">
            <caption>{`관절별 현재-rest 차이 (${JOINT_ANGLE_UNIT})`}</caption>
            <thead>
              <tr>
                <th scope="col">관절</th>
                <th scope="col">{`현재 (${JOINT_ANGLE_UNIT})`}</th>
                <th scope="col">{`rest (${JOINT_ANGLE_UNIT})`}</th>
                <th scope="col">{`Δ (${JOINT_ANGLE_UNIT})`}</th>
              </tr>
            </thead>
            <tbody>
              {deltas?.map((delta) => (
                <tr key={delta.joint} data-joint={delta.joint}>
                  <td>{delta.joint}</td>
                  <td>{radLabel(delta.currentRad)}</td>
                  <td>{radLabel(delta.restRad)}</td>
                  <td data-delta-rad={Number.isFinite(delta.deltaRad) ? delta.deltaRad : "unknown"}>
                    {radLabel(delta.deltaRad)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <p className="oa-s02-zero__worst" role="status">
            {`최대 |Δ|: ${radLabel(worst)}`}
          </p>
        </div>
      ) : (
        <p className="oa-s02-zero__no-telemetry" role="status" data-telemetry="none">
          텔레메트리 없음 — 현재 자세를 읽을 수 없어 영점 확인 불가
        </p>
      )}
    </section>
  );
}
