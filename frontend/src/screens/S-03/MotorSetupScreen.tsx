// The motor-setup screen (S-03, route /motors). A facade: it renders the
// backend-owned MOT state its `source` carries and emits user intent through its
// `sink`. It owns no motor truth. Composition order mirrors 02d §2.1: CAN-ID map /
// motor type, gain-limit profile editor+switch+validate, ERR-code view, temp view,
// gripper POS_FORCE + endpoint capture.
//
// Two always-on facts sit in the header: the active profile name is shown at all
// times, and while no profile is loaded the control-blocked banner is shown and
// control is refused (CG-G-S03e) — an undefined stiffness must never be commanded.

import { CanIdMotorTable } from "./CanIdMotorTable";
import { ErrorCodeReference } from "./ErrorCodeReference";
import { GripperPanel } from "./GripperPanel";
import { MotorStatePanel } from "./MotorStatePanel";
import { ProfileEditor } from "./ProfileEditor";
import { controlAllowed, type MotorSetupSink, type MotorSetupSource } from "./motorDomain";
import "./motors.css";

export interface MotorSetupScreenProps {
  source: MotorSetupSource;
  sink: MotorSetupSink;
}

export function MotorSetupScreen({ source, sink }: MotorSetupScreenProps) {
  const allowed = controlAllowed(source.activeProfileName);
  return (
    <section className="oa-motors" aria-labelledby="oa-motors-title">
      <header className="oa-motors__head">
        <p className="oa-motors__id">S-03 · MOT (03)</p>
        <h1 id="oa-motors-title" className="oa-motors__title">
          모터 설정
        </h1>
        <span
          className={`oa-motors__active-profile ${
            allowed ? "oa-motors__active-profile--loaded" : "oa-motors__active-profile--unloaded"
          }`}
          data-active-profile
        >
          활성 프로파일: {source.activeProfileName ?? "미로드 (none loaded)"}
        </span>
      </header>

      {!allowed && (
        <p className="oa-motors__control-block" data-control-blocked role="alert">
          프로파일 미로드 — 제어 시작 불가. 게인이 정의되지 않은 상태로 명령하지 않는다.
        </p>
      )}

      <CanIdMotorTable motors={source.motors} />

      <ProfileEditor
        profiles={source.profiles}
        activeProfileName={source.activeProfileName}
        mechanicalLimitsRad={source.mechanicalLimitsRad}
        onLoad={sink.loadProfile}
        onSave={sink.saveProfile}
      />

      <ErrorCodeReference errorRegistry={source.errorRegistry} />

      <MotorStatePanel motorStates={source.motorStates} errorRegistry={source.errorRegistry} />

      <GripperPanel gripper={source.gripper} onCaptureEndpoint={sink.captureGripperEndpoint} />
    </section>
  );
}
