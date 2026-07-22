// The /viewport route content and the reusable viewport surface (FR-GUI-003). It
// composes the shared canvas with the controls and status the viewport's gates
// require: the asset provenance and its block banner (CG-G-02b), the render-mode
// selector and layer toggles with the point-cloud layer gone (CG-G-02g, negative
// branch), view presets, the stream-age stale badge that blocks control input
// (CG-G-02e), the collision-coverage gap surfaced in Collision mode (CG-G-02g),
// and the resolved publish rate (CG-G-02i).
//
// It renders only from its `source` prop — a backend-derived input bundle — and
// converts no units and issues no reconnect. All the deciding logic lives in the
// pure modules; this component wires their results to the DOM.

import { useState } from "react";

import "./viewport.css";
import { ViewportCanvas } from "./ViewportCanvas";
import { POINTCLOUD_REDUCTION_NOTICE } from "./constants";
import { evaluateAsset } from "./loader/provenance";
import { collisionCoverage, hasCollisionGaps } from "./scene/collisionModel";
import {
  DEFAULT_LAYER_STATE,
  RENDER_MODES,
  RENDER_MODE_LABELS,
  layersForMode,
  type LayerState,
  type RenderMode,
} from "./scene/layers";
import { VIEW_PRESETS, VIEW_PRESET_IDS, type ViewPresetId } from "./scene/viewPresets";
import { acceptSnapshot } from "./state/jointSnapshot";
import { resolvePublishRate } from "./state/publishRate";
import { controlInputAllowed, evaluateStreamAge } from "./state/streamAge";
import { defaultViewportSource, type ViewportSource } from "./viewportSource";

interface ViewportPanelProps {
  source?: ViewportSource;
}

const LAYER_LABELS: Readonly<Record<keyof LayerState, string>> = {
  visualMeshes: "비주얼 메시",
  collisionGeoms: "충돌 지오메트리",
  jointFrames: "관절 프레임",
  grid: "바닥 그리드",
};

export function ViewportPanel({ source = defaultViewportSource() }: ViewportPanelProps) {
  const [mode, setMode] = useState<RenderMode>("auto");
  const [baseLayers, setBaseLayers] = useState<LayerState>(DEFAULT_LAYER_STATE);
  const [presetId, setPresetId] = useState<ViewPresetId>("iso");

  const asset = evaluateAsset(source.assetProvenance, source.acceptedRobotVersion);

  const snapshotResult = source.latestFrame
    ? acceptSnapshot(source.latestFrame, source.expectedJointNames)
    : null;
  const accepted = snapshotResult?.accepted ? snapshotResult : null;
  const lastAcceptedMonoMs = accepted ? accepted.frameMonoMs : null;
  const ageState = evaluateStreamAge(lastAcceptedMonoMs, source.nowMonoMs);
  const inputAllowed = controlInputAllowed(ageState);

  const publishRate = resolvePublishRate(source.requestedPublishRateHz);
  const coverage = collisionCoverage(source.urdfLinks, source.declaredCollisionLinks);
  const effectiveLayers = layersForMode(mode, baseLayers);

  const canvasSnapshot = asset.blocked ? null : (accepted?.positionsRad ?? null);
  const canvasRobot = asset.blocked ? null : source.robotHandle;

  function toggleLayer(key: keyof LayerState): void {
    setBaseLayers((current) => ({ ...current, [key]: !current[key] }));
  }

  return (
    <section className="oa-viewport" aria-labelledby="oa-viewport-title">
      <header className="oa-viewport__head">
        <p className="oa-viewport__id">/viewport</p>
        <h1 id="oa-viewport-title" className="oa-viewport__title">
          3D 뷰포트
        </h1>
      </header>

      {asset.blocked && (
        <div className="oa-viewport__blocked" role="alert">
          <strong>자산 로드 차단</strong>
          <span>{asset.reason}</span>
        </div>
      )}

      <dl className="oa-viewport__provenance" aria-label="자산 프로버넌스">
        <div>
          <dt>source_repo</dt>
          <dd>{source.assetProvenance.source_repo}</dd>
        </div>
        <div>
          <dt>commit_sha</dt>
          <dd>{source.assetProvenance.commit_sha}</dd>
        </div>
        <div>
          <dt>robot_version</dt>
          <dd>{source.assetProvenance.robot_version}</dd>
        </div>
      </dl>

      <ViewportCanvas
        presetId={presetId}
        snapshot={canvasSnapshot}
        robotHandle={canvasRobot}
        stale={ageState.stale}
      />

      <p
        className={`oa-viewport__control-status oa-viewport__control-status--${
          inputAllowed ? "ok" : "blocked"
        }`}
        role="status"
      >
        {`제어 입력: ${inputAllowed ? "허용" : "차단"}${ageState.stale ? " · STALE" : ""}`}
      </p>

      <fieldset className="oa-viewport__modes">
        <legend>렌더 모드</legend>
        {RENDER_MODES.map((candidate) => (
          <label key={candidate}>
            <input
              type="radio"
              name="oa-viewport-mode"
              value={candidate}
              checked={mode === candidate}
              onChange={() => setMode(candidate)}
            />
            {RENDER_MODE_LABELS[candidate]}
          </label>
        ))}
      </fieldset>

      <fieldset className="oa-viewport__layers">
        <legend>레이어</legend>
        {(Object.keys(LAYER_LABELS) as (keyof LayerState)[]).map((key) => (
          <label key={key}>
            <input
              type="checkbox"
              checked={effectiveLayers[key]}
              onChange={() => toggleLayer(key)}
            />
            {LAYER_LABELS[key]}
          </label>
        ))}
        <p className="oa-viewport__reduction" role="note">
          {POINTCLOUD_REDUCTION_NOTICE}
        </p>
      </fieldset>

      <fieldset className="oa-viewport__presets">
        <legend>뷰 프리셋</legend>
        {VIEW_PRESET_IDS.map((id) => (
          <button
            key={id}
            type="button"
            aria-pressed={presetId === id}
            onClick={() => setPresetId(id)}
          >
            {VIEW_PRESETS[id].label}
          </button>
        ))}
      </fieldset>

      {mode === "collision" && hasCollisionGaps(coverage) && (
        <div className="oa-viewport__collision-gap" role="alert">
          <strong>충돌 지오메트리 결손</strong>
          <span>collisions.yaml 미선언: {coverage.missing.join(", ")}</span>
        </div>
      )}

      <p
        className={`oa-viewport__rate oa-viewport__rate--${publishRate.ok ? "ok" : "rejected"}`}
        role="status"
      >
        {publishRate.ok
          ? `발행율: ${publishRate.hz} Hz`
          : `발행율 설정 거부: ${publishRate.reason}`}
      </p>
    </section>
  );
}
