// First-connect wizard (FR-GUI-112, 02 §2 wizard flow). It walks the operator
// through the onboarding sequence: bus scan -> motor discovery -> ID/type compare
// -> firmware/error check -> rest-pose confirm. The scan results (discovered
// motors, their types and error nibbles) are the BACKEND's readback; the wizard
// renders them and reports which motors carry an error. It runs no CAN itself and
// decodes no error nibble — both are the backend's.

import type { DiscoveredMotor } from "./connectionSource";

interface FirstConnectWizardProps {
  discoveredMotors: readonly DiscoveredMotor[];
}

const WIZARD_STEPS: readonly string[] = [
  "버스 스캔",
  "모터 발견",
  "ID/타입 대조",
  "펌웨어·에러코드 확인",
  "rest 자세 확인",
];

export function FirstConnectWizard({ discoveredMotors }: FirstConnectWizardProps) {
  const motorsWithError = discoveredMotors.filter((motor) => motor.errorCode !== null);

  return (
    <section
      className="oa-s02-wizard"
      aria-labelledby="oa-s02-wizard-title"
      data-panel="wizard"
    >
      <h2 id="oa-s02-wizard-title" className="oa-s02__panel-title">
        첫 연결 마법사
      </h2>

      <ol className="oa-s02-wizard__steps">
        {WIZARD_STEPS.map((step, index) => (
          <li key={step}>{`${index + 1}. ${step}`}</li>
        ))}
      </ol>

      {discoveredMotors.length === 0 ? (
        <p role="status">발견된 모터가 없습니다 — 버스 스캔을 실행하세요.</p>
      ) : (
        <table className="oa-s02-wizard__motors">
          <thead>
            <tr>
              <th scope="col">CAN ID</th>
              <th scope="col">관절</th>
              <th scope="col">모터 타입</th>
              <th scope="col">side</th>
              <th scope="col">에러</th>
            </tr>
          </thead>
          <tbody>
            {discoveredMotors.map((motor) => (
              <tr key={`${motor.side}-${motor.canId}`} data-motor-can-id={motor.canId}>
                <td>{`0x${motor.canId.toString(16)}`}</td>
                <td>{motor.jointName}</td>
                <td>{motor.motorType}</td>
                <td>{motor.side}</td>
                <td data-motor-error={motor.errorCode ?? "clear"}>
                  {motor.errorCode ?? "정상"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {motorsWithError.length > 0 && (
        <p className="oa-s02-wizard__errors" role="alert">
          {`에러 코드가 있는 모터 ${motorsWithError.length}개 — clear_error 후 재스캔 필요`}
        </p>
      )}
    </section>
  );
}
