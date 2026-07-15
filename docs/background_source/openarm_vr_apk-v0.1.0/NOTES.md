# OpenArm VR APK (openarm_vr_apk v0.1.0)

`OpenArm_Pose_Transmitter.apk`(약 86MB)는 **Git에 포함하지 않는다**(`.gitignore`의 `*.apk`).
소스 비공개 바이너리이며 크기 때문에 공개 저장소 히스토리에 넣지 않는다.

## 무엇인가
Meta Quest용 VR 포즈 송신 앱. 헤드셋에서 컨트롤러/손 포즈를 **UDP :5006 평문 JSON**으로 PC에 스트리밍한다(enactic `dora-openarm-vr`의 수신부 `quest_receiver.py`가 이 포맷을 파싱). 프로토콜은 공개되어 있으므로, 우리 `lerobot_teleoperator_openarm_vr`가 동일 포맷을 직접 수신한다.

## 어디서 받나
- enactic `dora-openarm-vr` 릴리스(`openarm_vr_apk-v0.1.0`) / 공식 배포 채널(Google Drive).
- 함께 있던 `openarm_vr_apk/THIRD_PARTY_NOTICES.txt`는 저장소에 유지한다.

## 주의
- **Quest 3 대상 빌드.** Quest **3S** 실동작은 자체 검증 필요(`docs/spec/16-미해결-이슈.md` M-22).
- 대안: `dora-openarm-webxr`(WebXR + HTTPS :8443) — APK 사이드로드 불필요.
