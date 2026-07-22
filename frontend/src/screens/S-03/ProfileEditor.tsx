// The gain/limit profile editor + switch + validate. It renders the backend's
// named profiles (03 §2.8), shows which is active, and lets the operator load a
// different one or edit and save. The save is GUARDED by validateProfileSave
// before it reaches the sink: an out-of-MIT-range gain (CG-G-S03c) or an
// operational limit that is not a subset of the mechanical limit (CG-G-S03d) is
// refused with reasons and the sink is never called. The guard uses the frozen
// contract bounds and the backend-supplied mechanical set — it clamps nothing and
// sends nothing of its own (the backend would silently clamp; the screen refuses).

import { useMemo, useState } from "react";

import {
  MIT_KD_RANGE,
  MIT_KP_RANGE,
  validateProfileSave,
  type GainLimitProfile,
  type JointLimitRad,
  type ProfileSaveDraft,
} from "./motorDomain";

interface ProfileEditorProps {
  profiles: readonly GainLimitProfile[];
  activeProfileName: string | null;
  mechanicalLimitsRad: readonly JointLimitRad[];
  onLoad: (name: string) => void;
  onSave: (draft: ProfileSaveDraft) => void;
}

function toDraft(profile: GainLimitProfile): ProfileSaveDraft {
  return {
    name: profile.name,
    kp: [...profile.kp],
    kd: [...profile.kd],
    operationalLimitsRad: profile.operationalLimitsRad.map((limit) => ({ ...limit })),
  };
}

export function ProfileEditor({
  profiles,
  activeProfileName,
  mechanicalLimitsRad,
  onLoad,
  onSave,
}: ProfileEditorProps) {
  const [selectedName, setSelectedName] = useState<string>(
    activeProfileName ?? profiles[0]?.name ?? "",
  );
  const [draft, setDraft] = useState<ProfileSaveDraft | null>(null);

  const selected = useMemo(
    () => profiles.find((profile) => profile.name === selectedName) ?? null,
    [profiles, selectedName],
  );
  const editing = draft ?? (selected ? toDraft(selected) : null);
  const validation = useMemo(
    () => (editing ? validateProfileSave(editing, mechanicalLimitsRad) : null),
    [editing, mechanicalLimitsRad],
  );

  if (profiles.length === 0) {
    return (
      <section className="oa-motors__panel" aria-labelledby="oa-motors-profile-title">
        <h2 id="oa-motors-profile-title" className="oa-motors__panel-title">
          게인/리밋 프로파일
        </h2>
        <p className="oa-motors__hint" role="status">
          프로파일 미가용 — 백엔드 대기 (awaiting backend)
        </p>
      </section>
    );
  }

  function editKp(index: number, value: number) {
    if (!editing) {
      return;
    }
    const kp = [...editing.kp];
    kp[index] = value;
    setDraft({ ...editing, kp });
  }

  function editKd(index: number, value: number) {
    if (!editing) {
      return;
    }
    const kd = [...editing.kd];
    kd[index] = value;
    setDraft({ ...editing, kd });
  }

  return (
    <section className="oa-motors__panel" aria-labelledby="oa-motors-profile-title">
      <h2 id="oa-motors-profile-title" className="oa-motors__panel-title">
        게인/리밋 프로파일
      </h2>

      <label className="oa-motors__field">
        <span>프로파일 선택</span>
        <select
          value={selectedName}
          aria-label="프로파일 선택"
          onChange={(event) => {
            setSelectedName(event.target.value);
            setDraft(null);
          }}
        >
          {profiles.map((profile) => (
            <option key={profile.name} value={profile.name}>
              {profile.name}
              {profile.name === activeProfileName ? " (활성)" : ""}
            </option>
          ))}
        </select>
      </label>

      <button
        type="button"
        className="oa-motors__button"
        data-action="load-profile"
        disabled={!selected || selected.name === activeProfileName}
        onClick={() => selected && onLoad(selected.name)}
      >
        이 프로파일 활성화 (load)
      </button>

      {editing && (
        <div className="oa-motors__scroll">
          <table className="oa-motors__table">
            <thead>
              <tr>
                <th>관절</th>
                <th>kp [{MIT_KP_RANGE.min}, {MIT_KP_RANGE.max}]</th>
                <th>kd [{MIT_KD_RANGE.min}, {MIT_KD_RANGE.max}]</th>
              </tr>
            </thead>
            <tbody>
              {editing.kp.map((kp, index) => (
                <tr key={index}>
                  <td>J{index + 1}</td>
                  <td>
                    <input
                      type="number"
                      aria-label={`J${index + 1} kp`}
                      value={kp}
                      onChange={(event) => editKp(index, Number(event.target.value))}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      aria-label={`J${index + 1} kd`}
                      value={editing.kd[index] ?? 0}
                      onChange={(event) => editKd(index, Number(event.target.value))}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {validation && !validation.ok && (
        <ul className="oa-motors__refusal" data-refusal="profile-save" role="alert">
          {validation.reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      )}

      <button
        type="button"
        className="oa-motors__button"
        data-action="save-profile"
        disabled={!editing || !validation || !validation.ok}
        onClick={() => {
          if (editing && validation && validation.ok) {
            onSave(editing);
          }
        }}
      >
        프로파일 저장 (save)
      </button>
    </section>
  );
}
