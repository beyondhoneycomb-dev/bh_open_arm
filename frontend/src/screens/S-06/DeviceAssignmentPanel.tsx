// Pick which physical camera fills which slot, against a live preview.
//
// This rig's wrist pair is two of one model reporting one serial: the driver
// hands back the same `card` string for both, so the row list alone cannot tell
// them apart. Each row therefore carries THREE things — the port the kernel
// reports, the preview the camera is sending right now, and the slot it fills —
// and the operator decides from the picture. The port is what the assignment is
// keyed on; the picture is what makes it the right port.
//
// Rows are derived from `discovered`, never from a constant: a camera is here
// because it answered the last scan, and gone when it is unplugged.

import { useEffect, useRef, useState } from "react";
import { cameraPreviewEndpoint } from "../../config/endpoints";
import {
  deviceForSlot,
  isAssignable,
  refusalMessage,
  refuseAssignment,
  shareCardName,
} from "./assign";
import type { DiscoveredCamera } from "./source";

// The pause between one preview frame arriving and the next being asked for. NOT a
// polling period: the next request is scheduled when the previous one settles, so
// the rate is whatever the devices can actually sustain.
//
// A fixed period was the first shape and it was wrong. One frame off an Arducam
// measures 0.48 s here — open, warm up, grab, encode, release — and a timer firing
// every 0.5 s starts the next open before the previous release lands, which the
// driver answers with EBUSY. That surfaced as a preview that worked for a minute
// and then went permanently 503 on the two wrist cameras while the ZED, being
// faster, kept going. Pacing off completion cannot produce that overlap at all,
// where a longer period would only have made it rarer.
const PREVIEW_GAP_MS = 150;

interface DeviceAssignmentPanelProps {
  discovered: readonly DiscoveredCamera[];
  // The slots the operator may fill. Comes from the backend's registered set, so
  // the panel offers no slot the robot does not have.
  slots: readonly string[];
  onRescanDevices: () => void;
  onAssignDevice: (portPath: string, slot: string) => void;
  onReleaseDevice: (portPath: string) => void;
}

// The live preview for one candidate device, keyed on its port. Rendered for
// every discovered device including the unassigned ones — an unassigned camera is
// exactly the one the operator needs to look at before deciding.
//
// Polled stills rather than a stream. The slot's real stream belongs to the
// capture run; a second reader on the same node takes frames that run is
// counting, and the run cannot tell that from a camera that started dropping.
//
// The cache-buster is not decoration: without it the browser serves the first
// frame forever and the panel shows a still picture that looks like a working
// preview of a camera pointed somewhere it no longer is.
function DevicePreview({ portPath }: { portPath: string }) {
  const [tick, setTick] = useState(0);
  const [failed, setFailed] = useState<boolean>(false);

  // Armed by whichever of onLoad/onError fires, and cancelled on unmount so a
  // navigation away does not leave a device being opened for a panel nobody is
  // looking at.
  const pending = useRef<number | null>(null);

  useEffect(() => {
    return () => {
      if (pending.current !== null) {
        window.clearTimeout(pending.current);
      }
    };
  }, []);

  const scheduleNext = () => {
    if (pending.current !== null) {
      window.clearTimeout(pending.current);
    }
    pending.current = window.setTimeout(() => {
      pending.current = null;
      setTick((previous) => previous + 1);
    }, PREVIEW_GAP_MS);
  };

  return (
    <div className="oa-cam-assign__preview" data-preview-port={portPath}>
      {failed ? (
        <p className="oa-cam-assign__preview-off" data-testid={`preview-off-${portPath}`}>
          프리뷰 없음 — 캡처가 이 카메라를 쥐고 있거나 열리지 않는다
          <img
            className="oa-cam-assign__retry"
            src={`${cameraPreviewEndpoint(portPath)}?t=${tick}`}
            alt=""
            aria-hidden="true"
            onError={scheduleNext}
            onLoad={() => {
              setFailed(false);
              scheduleNext();
            }}
          />
        </p>
      ) : (
        <img
          className="oa-cam-assign__frame"
          data-testid={`preview-${portPath}`}
          src={`${cameraPreviewEndpoint(portPath)}?t=${tick}`}
          alt={`${portPath} 프리뷰`}
          onError={() => {
            // Kept as a frame that failed rather than a dead preview: a camera a
            // capture run is holding answers 503 for the length of that run and
            // then starts answering again, and an operator who navigated here
            // mid-run should see it come back without reloading.
            setFailed(true);
            scheduleNext();
          }}
          onLoad={() => {
            setFailed(false);
            scheduleNext();
          }}
        />
      )}
    </div>
  );
}

export function DeviceAssignmentPanel({
  discovered,
  slots,
  onRescanDevices,
  onAssignDevice,
  onReleaseDevice,
}: DeviceAssignmentPanelProps) {
  const [refusal, setRefusal] = useState<string | null>(null);

  const assign = (portPath: string, slot: string) => {
    if (slot === "") {
      return;
    }
    const refused = refuseAssignment(discovered, portPath, slot);
    if (refused !== null) {
      setRefusal(refusalMessage(refused));
      return;
    }
    setRefusal(null);
    onAssignDevice(portPath, slot);
  };

  return (
    <section className="oa-cam-assign" aria-label="카메라 장치 지정">
      <header className="oa-cam-assign__head">
        <h2 className="oa-cam-assign__title">장치 지정</h2>
        <button type="button" className="oa-cam-assign__rescan" onClick={onRescanDevices}>
          다시 스캔
        </button>
      </header>

      <p className="oa-cam-assign__note">
        손목 카메라 두 대는 모델명과 시리얼이 같다. 이름으로는 구분되지 않으므로,
        프리뷰 그림을 보고 포트로 지정한다.
      </p>

      {discovered.length === 0 ? (
        <p className="oa-cam-assign__empty" role="status">
          붙어 있는 카메라가 없다 — 연결한 뒤 다시 스캔한다
        </p>
      ) : null}

      {refusal === null ? null : (
        <p className="oa-cam-assign__refusal" role="alert">
          {refusal}
        </p>
      )}

      <ul className="oa-cam-assign__list">
        {discovered.map((device) => {
          const ambiguousName = shareCardName(discovered, device.card);
          return (
            <li
              className="oa-cam-assign__row"
              key={device.portPath}
              data-port={device.portPath}
            >
              <DevicePreview portPath={device.portPath} />

              <div className="oa-cam-assign__identity">
                <span className="oa-cam-assign__card">{device.card}</span>
                {/* The port is the identity, so it is rendered as such rather than
                    as a tooltip: on this hardware it is the only distinguishing text. */}
                <code className="oa-cam-assign__port">{device.portPath}</code>
                <span className="oa-cam-assign__node">{device.devicePath}</span>
                {ambiguousName ? (
                  <span className="oa-cam-assign__ambiguous">
                    같은 이름의 장치가 하나 더 있다 — 프리뷰로 확인
                  </span>
                ) : null}
              </div>

              <div className="oa-cam-assign__slot">
                <label>
                  슬롯
                  <select
                    value={device.assignedSlot ?? ""}
                    disabled={!isAssignable(device)}
                    onChange={(event) => assign(device.portPath, event.target.value)}
                  >
                    <option value="">지정 안 함</option>
                    {slots.map((slot) => {
                      const holder = deviceForSlot(discovered, slot);
                      const taken = holder !== null && holder.portPath !== device.portPath;
                      return (
                        <option key={slot} value={slot}>
                          {taken ? `${slot} (사용 중)` : slot}
                        </option>
                      );
                    })}
                  </select>
                </label>
                {device.assignedSlot === null ? null : (
                  <button type="button" onClick={() => onReleaseDevice(device.portPath)}>
                    해제
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
