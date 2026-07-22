// The virtual-wall editor. It embeds the shared 3D viewport for spatial context
// and lets the operator define a keep-out box or plane, but a wall edit reaches
// the scene through exactly one path: onInjectWall, the backend geom injector
// (CG-G-S12d). The editor holds only the DRAFT the operator is typing; the
// authoritative walls come from the backend (props.walls) and the collision
// judgement is entirely the backend's — this component runs no intersection,
// distance, or containment test. Removing a wall is likewise an intent the
// backend applies.

import { useState } from "react";

import { ViewportPanel } from "../../viewport";
import type { VirtualWall, VirtualWallSpec, WallShape } from "./source";

interface VirtualWallEditorProps {
  walls: readonly VirtualWall[];
  onInjectWall: (spec: VirtualWallSpec) => void;
  onRemoveWall: (id: string) => void;
}

interface WallDraft {
  label: string;
  shape: WallShape;
  center: [number, number, number];
  halfExtents: [number, number, number];
  normal: [number, number, number];
}

function emptyDraft(): WallDraft {
  return {
    label: "",
    shape: "box",
    center: [0, 0, 0.5],
    halfExtents: [0.1, 0.1, 0.1],
    normal: [0, 0, 1],
  };
}

const AXES = ["x", "y", "z"] as const;

export function VirtualWallEditor({ walls, onInjectWall, onRemoveWall }: VirtualWallEditorProps) {
  const [draft, setDraft] = useState<WallDraft>(emptyDraft);

  function setVectorComponent(
    field: "center" | "halfExtents" | "normal",
    axis: number,
    value: number,
  ): void {
    setDraft((current) => {
      const next = [...current[field]] as [number, number, number];
      next[axis] = value;
      return { ...current, [field]: next };
    });
  }

  function inject(): void {
    onInjectWall({
      label: draft.label.trim() || "가상벽",
      shape: draft.shape,
      center: draft.center,
      halfExtents: draft.halfExtents,
      normal: draft.normal,
      enabled: true,
    });
    setDraft(emptyDraft());
  }

  return (
    <section className="oa-safety__panel" aria-labelledby="oa-safety-wall-title">
      <h2 id="oa-safety-wall-title" className="oa-safety__panel-title">
        가상벽 · 금지영역 3D 편집
      </h2>

      <ViewportPanel />

      <div className="oa-wall">
        <ul className="oa-wall__list" aria-label="주입된 가상벽">
          {walls.length === 0 ? (
            <li className="oa-safety__status-line">주입된 가상벽 없음</li>
          ) : (
            walls.map((wall) => (
              <li key={wall.id} className="oa-wall__item" data-wall={wall.id}>
                <span className="oa-contact__geoms">
                  {wall.label} · {wall.shape} · center [{wall.center.join(", ")}]
                </span>
                <button
                  type="button"
                  className="oa-safety__btn oa-safety__btn--danger"
                  data-action="remove-wall"
                  onClick={() => onRemoveWall(wall.id)}
                >
                  제거
                </button>
              </li>
            ))
          )}
        </ul>

        <div className="oa-wall__form" role="group" aria-label="가상벽 정의">
          <label className="oa-wall__field">
            이름
            <input
              type="text"
              value={draft.label}
              onChange={(event) => setDraft((current) => ({ ...current, label: event.target.value }))}
            />
          </label>

          <label className="oa-wall__field">
            형상
            <select
              value={draft.shape}
              onChange={(event) =>
                setDraft((current) => ({ ...current, shape: event.target.value as WallShape }))
              }
            >
              <option value="box">직육면체 (box)</option>
              <option value="plane">평면 (plane)</option>
            </select>
          </label>

          {AXES.map((axis, index) => (
            <label key={`center-${axis}`} className="oa-wall__field">
              center {axis} (m)
              <input
                type="number"
                step="0.01"
                value={draft.center[index]}
                onChange={(event) =>
                  setVectorComponent("center", index, Number(event.target.value))
                }
              />
            </label>
          ))}

          {draft.shape === "box"
            ? AXES.map((axis, index) => (
                <label key={`half-${axis}`} className="oa-wall__field">
                  half {axis} (m)
                  <input
                    type="number"
                    step="0.01"
                    value={draft.halfExtents[index]}
                    onChange={(event) =>
                      setVectorComponent("halfExtents", index, Number(event.target.value))
                    }
                  />
                </label>
              ))
            : AXES.map((axis, index) => (
                <label key={`normal-${axis}`} className="oa-wall__field">
                  normal {axis}
                  <input
                    type="number"
                    step="0.1"
                    value={draft.normal[index]}
                    onChange={(event) =>
                      setVectorComponent("normal", index, Number(event.target.value))
                    }
                  />
                </label>
              ))}

          <p className="oa-wall__note">
            편집 결과는 백엔드 geom 주입기로만 반영된다 — 화면은 충돌을 판정하지 않는다.
          </p>
          <button
            type="button"
            className="oa-safety__btn"
            data-action="inject-wall"
            onClick={inject}
          >
            geom 주입
          </button>
        </div>
      </div>
    </section>
  );
}
