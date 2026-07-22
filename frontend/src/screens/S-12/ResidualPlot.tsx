// The residual plot. Each joint gets ONE SVG that carries both the residual
// timeseries and its threshold line, sharing a single y-scale (CG-G-S12c). They
// are never split across two views: the threshold only means anything against the
// residual it bounds, and the crossing is the event an operator is watching for.
// The threshold value is the backend's (FR-SAF-060); this component draws it and
// marks the samples that exceed it, and computes no threshold of its own.

import { buildResidualPlotGeometry, type JointResidual } from "./residualGeometry";

interface ResidualPlotProps {
  residuals: readonly JointResidual[];
}

const PLOT_WIDTH = 360;
const PLOT_HEIGHT = 96;

function JointPlot({ joint }: { joint: JointResidual }) {
  const geometry = buildResidualPlotGeometry(joint, PLOT_WIDTH, PLOT_HEIGHT);
  const seriesClass = geometry.breached
    ? "oa-residual__series oa-residual__series--breached"
    : "oa-residual__series";

  return (
    <div className="oa-residual" data-plot="residual" data-joint={joint.jointName}>
      <div className="oa-residual__head">
        <span className="oa-residual__joint">{joint.jointName}</span>
        <span className="oa-residual__note-value">
          임계 ±{joint.thresholdNm} Nm · effort {joint.effortLimitNm} Nm
        </span>
      </div>

      <svg
        className="oa-residual__svg"
        viewBox={`0 0 ${PLOT_WIDTH} ${PLOT_HEIGHT}`}
        preserveAspectRatio="none"
        role="img"
        aria-label={`${joint.jointName} 잔차와 임계선`}
      >
        <line
          className="oa-residual__grid-line"
          x1={0}
          y1={geometry.zeroY}
          x2={PLOT_WIDTH}
          y2={geometry.zeroY}
        />
        <polyline className={seriesClass} data-series="residual" points={geometry.residualPoints} />
        <line
          className="oa-residual__threshold"
          data-series="threshold"
          x1={0}
          y1={geometry.thresholdY}
          x2={PLOT_WIDTH}
          y2={geometry.thresholdY}
        />
        <line
          className="oa-residual__threshold"
          data-series="threshold-neg"
          x1={0}
          y1={geometry.negThresholdY}
          x2={PLOT_WIDTH}
          y2={geometry.negThresholdY}
        />
        {geometry.breachPoints.map((point, index) => (
          <circle
            key={index}
            className="oa-residual__breach"
            data-series="breach"
            cx={point.x}
            cy={point.y}
            r={2.5}
          />
        ))}
      </svg>

      {geometry.breached && (
        <p className="oa-residual__note" role="status">
          임계 초과 — 잔차가 백엔드 임계선을 넘었다
        </p>
      )}
    </div>
  );
}

export function ResidualPlot({ residuals }: ResidualPlotProps) {
  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-residual-title">
      <h2 id="oa-safety-residual-title" className="oa-safety__panel-title">
        GMO 잔차 · 임계선
      </h2>
      {residuals.length === 0 ? (
        <p className="oa-safety__status-line">잔차 데이터 없음 — 백엔드 미제공</p>
      ) : (
        residuals.map((joint) => <JointPlot key={joint.jointName} joint={joint} />)
      )}
    </section>
  );
}
