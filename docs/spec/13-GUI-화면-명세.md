# 13. GUI 화면 명세 (3D 동작 화면 포함)

## 1. 범위

이 문서는 플랫폼 GUI의 **화면(웹 라우트/페이지) 인벤토리**, **3D 뷰포트(3D 동작 화면)의 기능 계약**, **공통 UI 요소(로봇 상태 배지 · CAN 소유자 표시 · 모드 전환 · 제어권)** 를 정의한다.

> 🔴 **아키텍처 확정 (PyQt6 데스크톱 폐기 → 웹 단일).** 직전 판은 GUI를 **PyQt6 + pyqtgraph.opengl 데스크톱 단일 프로세스 앱**으로 확정하고 GUI↔HW를 인프로세스 Qt 시그널로 두었다. **그 데스크톱 확정을 폐기한다.** 정본 = **헤드리스 파이썬 백엔드 서비스(FastAPI) + 웹 SPA 프런트엔드.** 백엔드가 CAN·LeRobot·안전계층·`Robot` 객체를 소유하고(LeRobot Python API **인프로세스 임베드**), 프런트는 브라우저에서 도는 웹 SPA다. **브라우저↔백엔드 전송 = 단일 WebSocket**(실시간 양방향: 명령 + 텔레메트리 + 카메라 프레임 멀티플렉싱) + **HTTP REST**(비실시간 CRUD). **gRPC는 오직 백엔드↔원격 추론(LeRobot `async_inference` PolicyServer)에만** 쓴다. §2.1을 보라.
> **참조 레포 `bh_indy7_LeRobot`의 PyQt6 GUI는 UI로 재사용하지 않는다.** 단 그 **백엔드 로직 패턴**(robot 임베드·`connect()` 1회·`LiveLinkMode` 상태전이·안전가드·캘리브레이션 SoT·이중추론·tolerant 카메라)은 UI와 무관하게 백엔드로 이식한다.

다루지 않는 것: 각 도메인의 알고리즘과 파라미터(IK·충돌감지·정책·데이터셋 스키마 등)는 해당 영역 문서(`05-텔레오퍼레이션`, `12-충돌감지-및-안전`, `11-추론-및-평가`, `07/08-데이터`, `10-학습`)가 소유하며, 이 문서는 **그것을 화면에 어떻게 노출·조작·검증 가능하게 하는가**만 규정한다. 시각 디자인(색·타이포·위젯 스타일)과 SPA 프레임워크·번들러·CSS 선택도 범위 밖이다.

---

## 2. 확정된 사실 기반

### 2.1 GUI 아키텍처 — FastAPI 백엔드 + 웹 SPA, 단일 WebSocket 전송 [확정]

백엔드는 참조 레포 `bh_indy7_LeRobot`(Neuromeka Indy7 + Seeed reBot B601-DM — DM 모터 공통, **로봇은 다르나 플랫폼 구조는 로봇-무관**)의 **로직 패턴**을 이식한다. 참조 레포의 `HwWorker`가 `Robot` 객체를 직접 소유하고 50/100 Hz로 폴링하며 `connect()`를 세션당 1회만 호출하고 모드를 `LiveLinkMode` 상태전이로 다루는 **소유·수명·상태머신 패턴**은 그대로 유효하다. 다만 그 상태를 **Qt 시그널로 위젯에 전달하던 부분**만 **WebSocket 프레임으로 브라우저에 발행**하는 것으로 바뀐다. UI는 새로 만든 웹 SPA다.

| 항목 | 확정 값 | 근거 |
|---|---|---|
| **백엔드** | **헤드리스 파이썬 서비스(FastAPI 등 ASGI).** `Robot` 인스턴스·CAN·안전계층·제어 루프를 **인프로세스로 소유**하고 LeRobot Python API를 임베드한다. **웹 서버 + 제어 루프가 같은 프로세스**에 있으므로 CLI 스폰이 없다(FR-GUI-083). 프런트엔드 정적 자산도 이 백엔드가 서빙한다(에어갭·자체 호스팅, FR-GUI-008). | 참조 레포 `hw_worker.py:186-239`(Robot 소유·폴링), `:407-408`(커맨드 큐); GROUND §0 아키텍처(LeRobot 인프로세스 임베드) |
| **프런트엔드** | **웹 SPA**(React 등 — **프레임워크는 [결정필요]**, §2.1.1). 브라우저에서 실행. 3D = **Three.js + `urdf-loader`** [확정]. **PyQt6/pyqtgraph/PyOpenGL/QMainWindow/QThread 아님.** | §2.1.1 스택 비교; `urdf-loader`(v2 URDF, 로봇 URDF 툴링 성숙) |
| **브라우저↔백엔드 전송** | 🔴 **단일 WebSocket + HTTP REST.** (a) **WS 1개**로 실시간 양방향 — 텔레옵 명령 + 텔레메트리(관절/토크/상태) + **카메라 프레임(바이너리 JPEG, 카메라ID+채널 태그로 멀티플렉싱)**. (b) **REST**로 비실시간 CRUD(설정 get/set, 데이터셋 목록/조회, 잡 시작/정지) — 표준 FastAPI 패턴이며 프로토콜 분리가 아니다. **별도 WebRTC 스트림으로 분리하지 않는다**(D-2 프로토콜 분리 금지). | §2.4, §2.7; DECISIONS-v3 D-2(단일 WS 통일) |
| **전송 선택 근거** | 🔴 **gRPC-web은 브라우저 양방향 스트리밍 제약(서버→클라 단방향 스트림만, 클라→서버 스트림 미지원)으로 실시간 텔레옵에 부적합** → WebSocket 채택. WebRTC는 카메라 한 종류를 위해 별도 시그널링/ICE 스택을 더하는 오버엔지니어링이라 배제(단일 WS로 흡수). | DECISIONS-v3 D-2; gRPC-web 브라우저 스트리밍 한계 |
| **gRPC의 유일한 용도** | **원격 추론(LeRobot `async_inference` PolicyServer↔RobotClient) 전용, 백엔드↔추론 홉에만.** 브라우저 경계가 아니다. `inference/_transport/*_pb2_grpc.py`(vendored protoc), 포트 **8080**, `actions_per_chunk` 필수, insecure → **LAN 전용**(`0.0.0.0` bind 하드 거부). | `inference/policy_server.py`, `services.proto:42-54`; §2.7 |
| **온보드 추론** | `lerobot-rollout` 엔진 인프로세스 임베드(LeRobot 0.6.x, CLI 스폰 없음). `InferenceMode` **LOCAL**(백엔드 인프로세스, 루프백 gRPC 127.0.0.1:8080) / **ASYNC**(원격 gRPC) 선택 → 원격/로컬이 **동일 코드 경로** | D-11; `policy_service.py`, `policy_server.py` |
| **AppMode** | **CLIENT / LOCAL / SERVER**(백엔드 기동 인자 `--mode`). CLIENT=일반 로봇 백엔드, LOCAL=로봇 백엔드 + 임베드 추론 서버 루프백, SERVER=추론 서버만(로봇 미소유, 제어 루프 미기동). **변경 = 백엔드 재시작**(런타임 HW-lock/스레드 churn 회피). 브라우저는 접속만 바꾸면 되며 재시작 대상이 아니다. | `app.py:26-70`(AppMode 패턴), `main_window.py:111-123` |
| **모드 전환(텔레옵/기록/추론/수동)** | **백엔드 단일 프로세스 내 상태머신**(`LiveLinkMode = NONE/TRIGGER_ONLY/ARM_ONLY/FULL/POLICY`). WS 명령 `SetLiveLinkMode`로 전환, 구조적 mutex(한 값만 활성). **`connect()`는 세션당 1회, CLI 스폰 금지.** | `hw_worker.py:169-183`; F-3′ |
| **연결 규율** | `connect()` 1회, 서브시스템별 관용 연결. **팔로워 = `connect_readonly()`**(torque-OFF 백드라이브 읽기전용 브링업, `12` FR-SAF-075). 다른 `lerobot-record`/teleop가 `flock`을 쥐면 **Observer(읽기전용) 강등** | `hw_worker.py:588-807`; `12` §2.14 |
| **설정 영속(서버측)** | (a) `runtime_config.json`(백엔드 XDG `~/.config/<app>/`) — pydantic `extra="forbid"` + atomic write(tmp→fsync→`os.replace`) + **서브객체 blast-radius 격리**(malformed 필드만 defaults) + lenient/strict 이중 로드. 브라우저는 **REST로 get/set**한다. (b) 캘리브레이션 `~/.cache/huggingface/lerobot/calibration/<kind>/<id>.json`(`save_calibration_atomic`) — LeRobot 레이아웃 미러 | `runtime_config.py:71-297`, `calibration/atomic_io.py:29-94`; `02`(CON)/`03`(MOT)이 스키마 소유 |
| **플러그인 로드(백엔드)** | umbrella dist `lerobot_robot_openarm_rig`(distribution-name 접두사 `lerobot_robot_*`) + shim import로 `@RobotConfig.register_subclass` 발화. OpenArm follower / VR·KER teleop이 이렇게 등록됨 | `lerobot_robot_indy7_rig/__init__.py:22-30`; `import_utils.py:214-228` |

> **폐기된 것(직전 데스크톱 판의 잔재):** PyQt6 `QMainWindow` 3-pane 셸, `pyqtgraph.opengl`/`PyOpenGL` 임베드 3D 뷰어, `HwWorker` **Qt 시그널/슬롯** 전달, 인프로세스-only 상태 전달, "GUI↔HW에 네트워크 경계·직렬화·대역폭이 없다"는 전제, 데스크톱 단일 오퍼레이터 가정. **웹 SPA에서는 브라우저↔백엔드 WS 경계가 실재하며 직렬화·대역폭이 다시 1급 관심사가 된다.**
> **명시적으로 채택하지 않은 것(오버엔지니어링):** WebRTC 별도 스트림/시그널링, `foxglove/ws-protocol`·`foxglove-sdk`, rosbridge CBOR, gRPC-web. **실시간 채널은 단일 WebSocket 하나**로 통일한다(D-2).

### 2.1.1 웹 스택 — 비교와 확정 범위

> 🔴 **원칙: 3D 툴링만 확정하고, SPA 프레임워크는 확정하지 않는다([결정필요]).** 아래는 선택지의 성격 정리이며 이 문서가 프레임워크를 못 박지 않는다.

| 계층 | 후보 | 확정 여부 | 비고 |
|---|---|---|---|
| **SPA 프레임워크** | React / Vue / Svelte 등 | **[결정필요]** | 특정 프레임워크에 과잉 약정하지 않는다. 상태관리·라우팅·번들러는 구현 단계 결정. |
| **3D 뷰포트** | **Three.js + `urdf-loader`** | 🔴 **[확정]** | v2 URDF를 브라우저에서 로드·조작하는 **성숙한 로봇 URDF 툴링**. 관절값 `setJointValue(rad)` API 제공(§2.5). R3F(react-three-fiber) 채택 여부는 프레임워크 결정에 종속. |
| **실시간 시각화 툴** | Foxglove / Rerun (웹) | **미채택** | 3D·시계열·리플레이·카메라 타일은 **자체 Three.js/차트 컴포넌트로 구현**한다. 외부 뷰어 임베드는 안 한다(자체 UI로 충분, 결합도·CSP 부담 회피). |
| **실시간 전송** | **WebSocket** / gRPC-web / WebRTC | 🔴 **WS [확정]** | gRPC-web=브라우저 양방향 스트리밍 부적합, WebRTC=별도 스택 오버엔지니어링. **단일 WS**로 명령+텔레메트리+카메라 통일(D-2). |

### 2.2 GUI가 반드시 노출해야 하는 시스템 제약 (이것이 화면 설계를 지배한다)

> 아래 F-1~F-9는 **런타임(LeRobot)의 확정 사실**이며 GUI 스택과 무관하게 유효하다 — 웹이든 데스크톱이든 GUI가 반드시 노출·강제해야 하는 함정들이다.

| # | 사실 | GUI에 대한 함의 | 출처 |
|---|---|---|---|
| F-1 | **SocketCAN은 배타 bind를 제공하지 않는다.** 두 프로세스가 `can0`을 bind하면 **둘 다 성공**하고, 로컬 루프백이 기본 ON이라 서로의 송신 프레임까지 수신한다. 에러·errno·예외가 **하나도 발생하지 않는다.** | 백엔드는 "연결됨"을 CAN fd 존재로 판정하면 안 된다. **`flock` 락 상태와 `/proc/net/can/raw`의 바인딩 소켓 수**를 1급으로 표시해야 한다(FR-GUI-061/062). | https://docs.kernel.org/networking/can.html · `openarm_can/src/openarm/canbus/can_socket.cpp` |
| F-2 | CAN 클라이언트가 **여럿 실재**: LeRobot `DamiaoMotorsBus`(python-can, **우리 것**), `openarm_can`/`openarm-can-cli`(C++/CLI/영점스크립트), `openarm_driver`(Python), `openarm_teleop`(C++ 1000 Hz), `cansend`. CAN ID 맵(send `0x01–0x08` / recv `0x11–0x18`)은 전부 동일. | ⚠️ **정답은 하나(LeRobot 백엔드)이고 나머지는 전부 침입자다.** GUI는 **침입 프로세스의 PID를 표시하고 제어를 차단**해야 한다(FR-GUI-062). ⚠️ `openarm_teleop`은 `leader=can0`/`follower=can2`로 **LeRobot 관례(can0=follower)와 정반대**다 | `lerobot/src/lerobot/motors/damiao/damiao.py`; `openarm_teleop/control/openarm_bilateral_control.cpp:154-155` |
| **F-3′** | 🔴 **`connect()`가 영점을 파괴한다.** `openarm_follower.py:152-153` → `if self.is_calibrated: self.bus.set_zero_position()`. **현재 물리 자세가 영점으로 확정된다.** | 🔴 **GUI에 "재연결" 버튼을 만들어서는 안 된다.** 모드 전환·에러 복구·E-Stop 해제 어디에서도 `disconnect()`/`connect()`를 호출하지 않는다. 부득이한 재연결은 **rest 자세 확인 + 이중 확인 + 감사 로그**를 강제한다(FR-GUI-084). 브링업은 **`connect_readonly()`**(torque-OFF)로 시작한다(`12` FR-SAF-075). | `openarm_follower.py:152-153`; `motors/damiao/damiao.py:335-340` |
| **F-4′** | 🔴 **`use_velocity_and_torque` 기본값이 `False`다.** (`config_openarm_follower.py:71`) 켜지 않으면 **토크·속도가 조용히 사라지고** 데이터셋이 위치-only(양완 16차원)로 생성된다. | 🔴 **GUI가 상태를 상시 표시하고, 꺼져 있으면 경고해야 한다**(FR-GUI-072). 이 플랫폼의 정체성(힘/컴플라이언스 데이터 수집)이 **플래그 하나에 달려 있다.** 팔로워/리더를 **개별 설정하는 UI를 만들어서는 안 된다** — 불일치 시 record가 `KeyError`로 죽는다 | `config_openarm_follower.py:71`; `feature_utils.py:131-132` (`build_dataset_frame`의 `values[name]` 인덱싱) |
| **F-5′** | 🔴 **`--dataset.push_to_hub` 기본값이 `True`다.** (`configs/dataset.py`) `lerobot_record.py:534-538`의 `finally` 블록이 `dataset.push_to_hub(...)`를 호출한다. | 🔴 **명시적으로 끄지 않으면 사내 데이터(카메라 영상 포함)가 Hugging Face Hub로 나간다.** GUI는 값을 **위험 색상으로 상시 표시**하고, `true`로 수집을 시작하려 하면 **명시적 확인**을 요구해야 한다(FR-GUI-073) | `lerobot/src/lerobot/configs/dataset.py`; `lerobot_record.py:534-538` |
| **F-6′** | 🔴 **`--robot.side` 미지정 시 `joint_limits`가 전 축 ±5°로 잠긴다.** (`config_openarm_follower.py:107-120`) | **팔이 사실상 안 움직인다.** 그런데 에러가 없어서 "리밋이 잘 걸렸다"로 오독하기 쉽다. GUI는 `side` 선택을 **강제**해야 한다(FR-GUI-112). | `config_openarm_follower.py:107-120` |
| **F-7′** | 🔴 **python-can socketcan 백엔드는 `bitrate`/`data_bitrate` 인자를 무시한다.** CAN-FD를 켜는 것은 **`ip link` 단계이며 코드가 대신할 수 없다.** | GUI는 기동 시 **`ip -details link show can{N}`** 으로 CAN-FD(nominal 1 Mbps / data 5 Mbps)와 링크 상태를 **검증**하고, 미설정 시 기동을 차단해야 한다(FR-GUI-062). | python-can socketcan 백엔드; `12` FR-SAF-002b |
| **F-8** | **홀딩 브레이크가 없다.** 공식 Safety Guide: *"if power is lost due to an emergency stop, the load being held will fall rapidly."* E-Stop은 팔 내장이 아니라 **전원 라인 외부 버튼**이다. | **소프트 스톱(토크로 자세 유지)과 하드 E-Stop(전원 차단→낙하)은 GUI에서 서로 다른 컨트롤이어야 한다**(FR-GUI-063, FR-GUI-064). | `00-개요-및-문서규약.md` §3.3 (OpenArm Safety Guide 인용) |
| **F-8b** | 🔴 **LeRobot에는 소프트웨어 E-Stop이 없다.** `record_loop()`의 `events` dict(`{"exit_early","rerecord_episode","stop_recording"}`)는 **에피소드 제어이지 안전 정지가 아니다** — `stop_recording`은 루프를 빠져나갈 뿐 모터를 홀드하지 않는다. | 🔴 **"루프를 멈추는 E-Stop"은 그 자체가 낙하를 부른다**(명령 스트림 중단 → 인에이블 이탈 → 토크 0). GUI의 정지 버튼은 **루프를 계속 돌리면서 명령을 `STOP_HOLD`로 바꾸는 것**에 매핑되어야 한다(`12` FR-SAF-073). | `lerobot/src/lerobot/utils/keyboard_input.py:153-170`; `12` §2.3 |
| F-9 | **8모터 구성에서 1000 Hz 초과 제어 사이클은 CAN 연결을 불안정하게 만든다**(openarm_can 공식 문서 경고). | GUI의 제어 주파수 입력 위젯은 상한을 강제해야 한다(FR-GUI-087). | openarm_can 공식 문서 |
| **F-10′** | 🔴 **제어 루프가 백엔드 프로세스 안에 있다.** LeRobot `record_loop()` / teleop 라이브링크가 **백엔드의 제어 루프 태스크**에서 돈다(브라우저 아님). 이제 **브라우저↔백엔드 WS 경계가 실재**하므로 렌더·조작은 브라우저로 넘어갔지만, **백엔드는 WS 서빙·카메라 JPEG 인코딩이 제어 루프를 방해하지 않도록** 제어 루프를 별도 스레드로 분리하고 우선순위를 승격해야 한다. | 🔴 **NFR-GUI-008**: 제어 루프는 RT 승격 스레드, WS 서빙/JPEG 인코딩은 별도 워커. **LeRobot Python 루프의 실측 사이클 타임은 [미측정]이다** — 카메라 인코딩·WS 직렬화가 제어 루프 지터를 만드는지 감시해야 한다(NFR-GUI-011, §5 Q-14). | GROUND §7 (LeRobot 루프 사이클 타임 [미측정]); `hw_worker.py`(제어 루프 소유 패턴) |

### 2.3 3D 뷰포트가 그려야 하는 대상 — 로봇 모델의 확정 사실

| 항목 | 값 | 출처 |
|---|---|---|
| 로봇 | OpenArm **v2.0**, 팔당 **7-DOF + 그리퍼**. 양팔(bimanual). | https://docs.openarm.dev/hardware/openarm-2.0/general/ |
| URDF 소스 | `openarm_description` — **v2.0 = 프리셋 기반 xacro 파이프라인(active)**, v1.0 = 레거시. **v2.0 자산만 로드한다.** | https://github.com/enactic/openarm_description |
| **관절 이름 (정본)** | `openarm_left_joint1` … `openarm_left_joint7`, `openarm_left_finger_joint1` / right 동일. 즉 **팔당 8개.** | `openarm_description` v2.0 URDF · `openarm_mujoco/v2/joint_resolver.py` |
| 관절 상태 채널 | 🔴 `qpos`/`qvel`/`qtorque` **3채널이 아니다.** LeRobot은 이를 **`observation.state` 벡터 하나로 평탄화**한다 — `use_velocity_and_torque=true`일 때 모터당 `(pos, vel, torque)` 인터리브, **단완 24차원 / 양완 48차원.** `names` 리스트에 `left_joint_1.torque` 같은 **문자열만** 남는다. **`observation.effort` 키는 존재하지 않는다**(전체 트리 grep 0건). GUI는 **`names` 인덱스로 채널을 뽑아야** 하며 고정 인덱스를 하드코딩해서는 안 된다. **단위가 섞인다**: `.pos`=deg, `.vel`=deg/s, `.torque`=**Nm** | `lerobot/src/lerobot/utils/feature_utils.py:68-89`; `motors/damiao/damiao.py:568` |
| 모터 온도 | 상태 피드백 8바이트에 `data[6]=T_MOS`, `data[7]=T_Rotor`가 **매 프레임 실려 온다.** 별도 폴링 불필요. | `openarm_can/src/openarm/damiao_motor/dm_motor_control.cpp` (`parse_motor_state_data`) |
| **관절 리밋 — v2 URDF rad 정본** | (a) **기계 상한 = v2 URDF `joint_limits.yaml`(rad)**: joint1 `[-1.3963, 3.4907]`(−80°/+200°), **joint2 `[-0.17453, 3.3161]`(−10°/+190°) ← v1 ±100°에서 변경**, joint3 ±90°, joint4 0°/+140°, joint5 ±90°, **joint6 ±45°**, joint7 ±90°. (b) **운영 상한 = v2 driver `openarm_cell.yaml`**(좌우 미러). (c) LeRobot `config_openarm_follower.py`의 deg 값(joint_1 −75°/+75° 등)은 **v1-era 소프트 안전 기본값**(*"the default joint limit values are small for safety"*)이며 **정본이 아니다** — 초기 소프트 클램프로만. `side` 미지정 시 전 축 **±5°**. | `openarm_description/.../openarm_v2.0/config/arm/joint/joint_limits.yaml`(정본) · `openarm_driver/configs/openarm_cell.yaml` · `config_openarm_follower.py`(소프트) |
| **PD 게인 — 명명 프로파일** | `compliant`=**70계열**[70,70,70,60,10,10,10,10]/kd[2.75,2.5,2.0,2.0,0.7,0.6,0.5,0.2] **(v1v2 공통 기본, 텔레옵/접촉)** · `stiff`=**230계열**[230,230,190,190,30,30,30,10]/kd[2.7,2.7,2.2,2.2,1.5,1.5,1.5,0.2] **(v2 고유, 트윈·드라이런·평가·VR — sim-real 패리티)** · 240계열=**LeRobot 독자 v1-era**(비정본). **"70=v2 판별자"는 오류(70은 공통), v2 고유는 230.** | `control_gains.yaml`·`openarm_cell.yaml`(70) / `openarm_cell_higher_pd.yaml`(230) / `config_openarm_follower.py`·`openarm_teleop`(240) |
| **그리퍼 — v2 pinch** | **pinch 그리퍼**: revolute **−45°–0°**(−0.7854..0 rad), 2지 mimic(finger2=finger1), **인핸드 카메라 내장.** 네이티브 제어 = **POS_FORCE**(`gripper_posforce_limits:[50 rad/s, 1.0 Nm]`). 로드셀 없음 → open/close **엔드포인트 rad 캡처 → 디스크 영속**(참조 레포 패턴). v1의 88mm/링키지/파지력(N)은 **무효.** | `pinch_gripper/config/joint/joint_limits.yaml`·`joint_mimics.yaml`; `openarm_cell.yaml gripper_posforce`; 참조 레포 `capture_gripper_endpoint` |
| **IK/FK — 별도 스택** | **LeRobot openarm = IK 없음**(URDF 미탑재, 관절공간 leader→follower). IK/FK 정본 = **`enactic/openarm_control`**(kinematics.py, mink+MuJoCo+daqp). 3D 뷰포트 EE 포즈는 이 백엔드 모듈에서 취한다. | `openarm_control/kinematics.py`; `09` |
| ⚠ MuJoCo 모델은 교차확인 근거가 못 된다 | `openarm_mujoco/v2/openarm_bimanual.xml`은 **파일 내부가 불일치**한다: joint7 `class="motor_DM3507"`인데 액추에이터는 `position_DM4310`. J7 정본은 **DM4310**(`09` §2.6). | `09` FR-SIM-007 |

> **함의**: 3D 뷰포트의 조인트 슬라이더 개수 = **팔당 8**(7 + finger). 클램프에 쓸 리밋과 게인은 **단일 값이 아니라 이름 붙은 프로파일**로 다뤄야 한다. **리밋 정본 = v2 URDF rad**(§5 Q-2), 게인 정본 = compliant/stiff/replay 3-프로파일(§5 Q-3). URDF는 브라우저 `urdf-loader`가 로드하며 관절값은 **rad**로 넣는다(§2.5).

### 2.4 실시간 상태 소스 — 브라우저↔백엔드 WebSocket 경계

🔴 **GUI↔HW 사이에 WebSocket 경계가 실재한다.** 관절 상태는 백엔드의 `Robot.get_observation()` 한 곳에서 나오고, 백엔드 제어 루프가 이를 폴링해 **뷰 표시용 데시메이션 후 WS 텔레메트리 프레임**으로 브라우저에 발행한다. 브라우저 3D 뷰포트/차트는 그 WS 프레임을 소비한다. **직렬화·인코딩·대역폭 예산·WS 지연이 다시 존재**하므로(웹 선택의 대가) 발행 주기·프레임 크기를 렌더 예산과 링크 대역폭에 맞춰 관리해야 한다.

**단일 WebSocket이 나르는 것(멀티플렉싱, D-2):**
- **텔레메트리** — 관절 상태(pos/vel/torque, `names` 인덱스), 모드/CAN/안전 상태, 스트림 통계. JSON 또는 소형 바이너리.
- **명령** — 텔레옵/조그/모드 전환/에피소드 이벤트. 브라우저→백엔드.
- **카메라 프레임** — 바이너리 JPEG(RGB)/인코딩된 뎁스, **카메라ID+채널 태그**로 다중화(§3.4). 같은 WS 안에서 텍스트 프레임(텔레메트리)과 바이너리 프레임(카메라)을 구분한다.

**네트워크 경계가 있는 곳 (§2.7 포트 매니페스트):**
- **브라우저↔백엔드** — WS(실시간) + HTTP REST(CRUD). 백엔드가 SPA 정적 자산도 서빙.
- **백엔드↔원격 추론** — gRPC 8080(async PolicyServer). LOCAL 모드는 같은 프로세스 루프백.
- **VR 텔레옵 입력** — Quest 3 네이티브 APK → **UDP 5006**(백엔드 수신), 또는 WebXR → **HTTPS 8443**(헤드셋 브라우저용 별도 서버).
- **카메라** — 물리 장치(USB/CSI)에서 **백엔드로 프레임 grab** → JPEG 인코딩 → WS로 브라우저 전달. raw USB 대역폭은 `06-카메라-서브시스템.md`가 소유한다.

**실측/기준 주파수:**

| 소스 | 주파수 | 근거 |
|---|---|---|
| 🔴 **LeRobot record/teleop 제어 루프(백엔드)** | **[미측정]** ← **이것이 우리 제어 루프다** | GROUND §7. 한 프로세스에 CAN(16모터) + 카메라 grab/인코딩 + IK + WS 서빙이 얹힌다 → NFR-GUI-011, §5 Q-14 |
| WS 텔레메트리 발행(뷰 데시메이션) | 기본 30 Hz(상한 60) | 제어 루프 폴 50/100 Hz → 뷰는 렌더/대역폭 예산에 맞춰 데시메이션 |
| WS 카메라 프레임 | 기본 30 fps, 백프레셔 시 드롭 | LeRobot `DatasetRecordConfig.fps = 30`; 백엔드 인코딩 예산에 종속(§3.4) |
| `openarm_teleop` 리더-팔로워 양방향(상류 참고) | **1000 Hz**(`#define FREQUENCY 1000.0`), 바이래터럴 스레드 500 Hz | `openarm_teleop/src/openarm_constants.hpp`. **500 Hz는 바이래터럴 힘반사 전용 — 우리 LeRobot/dora 주경로 필수 아님**(`12` §2.9) |
| 카메라 fps | **30** | LeRobot `DatasetRecordConfig.fps = 30` |
| VR 포즈 스트림 기준 | **72 Hz**(Quest) | `dora-openarm-vr` / `dora-openarm-data-collection-ui`(`VR_TIMESTAMP_WINDOW=120`) |

**카메라 세트 — `06-카메라-서브시스템.md`가 소유한다.** 13은 이를 **소비만** 한다. 슬롯 정본·해상도·하드웨어 모델(뎁스 RGB-D 포함 여부)은 06이 확정하며, **13은 카메라 하드웨어를 정본으로 재주장하지 않는다.** GUI는 06이 노출하는 `robot.observation_features`의 카메라 키셋에서 타일 수를 **런타임에 유도**한다(FR-GUI-101). 🔴 **UI 라벨과 데이터셋 키가 다를 수 있다**(예: 손목 UI `wrist_left` ↔ 데이터셋 키 `observation.images.left_wrist` — `bi_openarm_follower`가 팔별 접두사 자동 부착) → GUI는 **양쪽을 함께 표시**해야 한다(`bi_openarm_follower.py:99-112`).

### 2.5 3D 렌더링 — Three.js + `urdf-loader` (브라우저) [확정]

| 항목 | 사실 | 근거 |
|---|---|---|
| 뷰어 | **Three.js `WebGLRenderer` + `urdf-loader`를 웹 SPA 안의 `<canvas>`에 렌더.** orbit/pan/zoom은 `OrbitControls` 등으로. 외부 Rerun/RViz/Foxglove 창 없음. | `urdf-loader`(성숙한 로봇 URDF 웹 툴링); §2.1.1 |
| 자산 로드 | **백엔드가 xacro를 전개해 v2.0 URDF XML을 생성**하고, URDF + 링크 메시(STL/DAE/OBJ)를 **백엔드가 정적 경로로 서빙**한다. 브라우저 `urdf-loader`는 백엔드가 준 URL(자체 호스트, CDN 아님)에서 메시를 로드한다. `package://` 경로는 **백엔드가 실제 파일 URL로 재작성**해 프런트에 넘긴다(브라우저가 임의 파일시스템을 못 읽으므로). | `openarm_description` v2.0 xacro; `urdf-loader` `package://` 리라이트 |
| 관절 반영 | 관절각(**rad**)으로 `urdf-loader`의 `robot.setJointValue(name, rad)`를 호출해 링크 변환을 갱신한다. **LeRobot 관측은 deg**이므로 **deg→rad 변환 + 이름공간 매핑은 단일 모듈**(백엔드측 권장)이 소유하고, WS로는 **URDF 관절 이름 + rad**를 실어 보내 브라우저가 바로 소비하게 한다. | `openarm_follower.py:55-57`(`MotorNormMode.DEGREES`); `09` FR-SIM-082; `urdf-loader.setJointValue()` |
| EE 포즈(FK) | **`openarm_control.Kinematics.fk_bimanual(right, left)`**(백엔드) → `float32[7] × 2 = [px,py,pz,qw,qx,qy,qz]`(**MJCF 월드, m/rad**). **실측 0.037 ms**(≈27 kHz) → 부담 0. 백엔드가 계산해 WS로 발행하고 브라우저는 좌표축으로 표시. `dora-openarm-kinematics`는 dora 래퍼이며 우리 경로에 없다 — 본체 `openarm_control`을 직접 쓴다. | `openarm_control/kinematics.py fk_bimanual()` |
| 렌더 규모 | 로봇 2대(링크 8~16) + 그리퍼 = 메시 수십 개. Three.js WebGL로 여유. 병목은 로봇 메시가 아니라 **포인트클라우드/큰 씬**(정본 카메라 구성에 뎁스가 없으면 포인트클라우드 소스 자체가 없다 — 06 소유). | Three.js 성능 상식; `dataviz` |

### 2.6 화면 인벤토리 — 웹 라우트 · 책임 · 도메인 문서 · 기능 참고

> 이 표는 본 문서가 정의하는 **화면(웹 라우트/페이지)의 정본 목록**이다. "구현 FR"은 각 화면이 구현 창구가 되는 다른 명세 문서의 영역 코드다. "기능 참고"는 `bh_indy7_lerobot_gui`(PyQt6)가 이미 구현한 대응 패널로, **UI는 재사용하지 않으나** 우리 화면이 무엇을 해야 하는지의 **기능적 출발점**이다. **3D 뷰포트는 독립 라우트이자 여러 화면에 임베드되는 공유 컴포넌트**다(FR-GUI-003).

| # | 화면 | 웹 라우트(예시) | 책임 | 3D 뷰포트 | 구현 FR(도메인) | 기능 참고(PyQt6 패널, UI 미재사용) |
|---|---|---|---|---|---|---|
| S-01 | **대시보드** | `/` | 시스템 한눈: 로봇 연결/모드, **CAN 소유자**, 카메라 슬롯 상태, 디스크 여유, GPU/VRAM, 최근 세션, 미ack 경고 | 축소(읽기전용) | `SYS`, `OPS`, `NFR` | `LiveStatus` |
| S-02 | **로봇 연결** | `/connection`, `/home-zero` | 하드웨어 인벤토리, SocketCAN 셋업/진단, 첫 연결 마법사, **`connect_readonly` 브링업 + 영점 캘리브레이션**, 프로파일 선택 | 연결 후 자세 확인 | `CON` (`02`) | `HardwareSetup`, `Connection`, `HomeZero`, `Calibration` |
| S-03 | **모터 설정** | `/motors` | CAN ID 맵, 모터 타입, **게인/리밋 프로파일 편집·전환**(compliant/stiff), 에러코드, 온도, **그리퍼(POS_FORCE, 엔드포인트 캡처)** | 리밋 시각화 | `MOT` (`03`) | `GripperMode`, `GripperControl`, `GripperDiagnostics`, `Stiffness` |
| S-04 | **수동 동작** | `/manual` | 관절 조그, 카테시안 조그, Freedrive, 티칭, 홈 복귀 | **주 화면** | `MAN` (`04`) | `ManualControl` |
| S-05 | **텔레옵** | `/teleop` | Quest 3 VR 세션: 정렬 단계, 클러치, **C-Lat 표시**, One-Euro 파라미터, 워치독 | **주 화면**(리더 vs 팔로워) | `TEL` (`05`) | (신규 — Teleoperator) |
| S-06 | **카메라** | `/cameras` | 타일 프리뷰(WS 바이너리 JPEG, 활성 전송 스트림 수 런타임 유도), FPS/지터/드롭, 해상도·fps 조정, **뎁스 컬러맵**, hand-eye 캘리브레이션 | 프러스텀 연동 | `CAM` (`06`) | `camera_settings`/CameraTiles |
| S-07 | **데이터 수집** | `/collect` | 에피소드 루프(start→success/fail/cancel→reset→repeat), 태스크 프롬프트, Resume, 저장량 예측, 드롭 리포트 | 보조 | `REC` (`07`) | `EpisodeRecorder` |
| S-08 | **데이터셋** | `/datasets` | 브라우징, 타임라인 스크럽, **`observation.state` 채널 플롯** + 카메라 동기 재생, 편집, 검증. **포맷 변환 없음**(LeRobot v3.0 정본) | 리플레이 | `DAT` (`08`) | (신규) |
| S-09 | **시뮬레이션** | `/sim` | MuJoCo 디지털 트윈, 드라이런, 합성 데이터. **트윈·드라이런은 실기 stiff(230) 강제**(`09` FR-SIM-028b) | **주 화면**(sim vs real) | `SIM` (`09`) | (신규 — `bi_openarm_mujoco` Robot) |
| S-10 | **학습** | `/training` | 정책 선택, 하이퍼파라미터, 잡 큐/로그/체크포인트, VRAM 사전검증 | 없음 | `TRN` (`10`) | `Training`(train_config) |
| S-11 | **추론/평가** | `/inference` | 추론 루프, **액션 큐 시각화**, 태스크 스위처, 성공률, takeover, 롤아웃. **LOCAL/ASYNC 모드 선택** | **주 화면**(정책 목표 vs 현재) | `INF` (`11`) | `Inference`, `server`(mode_select) |
| S-12 | **충돌·안전** | `/safety` | 가상벽/금지영역 편집, 반응 정책(**소프트 스톱 vs 하드 E-Stop**), 충돌 이벤트 로그 | **주 화면**(편집 대상) | `SAF` (`12`) | `inference_safety`(안전 게이트) |
| S-13 | **시스템/로그** | `/system` | 프로세스·포트 맵, RT 클래스/CPU 어피니티, 진단 번들, 감사 로그, 설정 계층 | 없음 | `OPS` (`14`) | (신규) |

> **3D 뷰포트 라우트/컴포넌트**: 단일 `<canvas>` 3D 컴포넌트가 위 화면들에 임베드되며 독립 라우트(`/viewport`)로도 열 수 있다. 표시 레이어·상호작용 권한(읽기전용/조작가능)은 화면마다 다르게 설정된다(FR-GUI-003).

### 2.7 네트워크 경계 · 포트 매니페스트

> 🔴 웹 SPA에서는 데스크톱 판과 달리 **브라우저↔백엔드 경계가 실재**한다. 아래가 이 시스템의 **전 네트워크 경계**이며, 실시간 브라우저 채널은 **단일 WebSocket 하나**로 통일한다(D-2, 프로토콜 분리 금지). 포트는 설정 가능하고 기동 시 충돌을 감지한다(FR-GUI-006).

| 경계 | 프로토콜/포트 | 방향 | 나르는 것 | 근거 |
|---|---|---|---|---|
| **브라우저 ↔ 백엔드 (실시간)** | **WebSocket**(HTTP(S) 위, 기본 SPA 서빙 포트 공유) | 양방향 | 텔레옵 명령 + 텔레메트리(관절/토크/상태/스트림통계) + **카메라 프레임(바이너리 JPEG/뎁스, 카메라ID+채널 태그)** | §2.1, §2.4; D-2 |
| **브라우저 ↔ 백엔드 (CRUD)** | **HTTP REST**(SPA 서빙 포트) | 요청/응답 | 설정 get/set, 데이터셋 목록/조회, 잡 시작/정지, 프로파일 — 비실시간. 표준 FastAPI, 프로토콜 분리 아님 | §2.1 |
| **브라우저 ↔ 백엔드 (정적)** | **HTTP(S)** | 다운로드 | SPA 번들·폰트·URDF/메시·3D 자산(자체 호스팅, CDN 금지 — 에어갭) | FR-GUI-008 |
| **백엔드 ↔ 원격 추론** | **gRPC :8080**(insecure, LAN 전용) | 양방향 스트림 | async PolicyServer↔RobotClient. LOCAL 모드는 127.0.0.1 루프백. **브라우저 경계 아님** | `services.proto:42-54`; §2.1 |
| **VR 헤드셋 → 백엔드 (네이티브)** | **UDP :5006** | 수신 | Quest 3 네이티브 APK 포즈 스트림 | `dora-openarm-vr` |
| **VR 헤드셋 → 백엔드 (WebXR)** | **HTTPS :8443**(자체서명) | 수신 | WebXR 포즈(헤드셋 브라우저용 **별도** HTTPS 서버, 일반 SPA 서빙과 포트 분리) | `dora-openarm-webxr`; FR-GUI-005 |
| **카메라 장치 → 백엔드** | USB/CSI(네트워크 아님) | 수신 | raw 프레임 grab → 백엔드에서 JPEG/뎁스 인코딩 후 WS로 재전송. raw 대역폭 정본은 `06` | §2.4; `06` |

> **채택하지 않은 실시간 채널**: WebRTC(별도 시그널링/ICE), gRPC-web(브라우저 양방향 스트리밍 부적합), foxglove/rosbridge. 전부 단일 WS로 흡수(오버엔지니어링 회피). S-13 시스템 화면이 이 매니페스트와 각 포트 상태를 표시한다(FR-GUI-109).

---

## 3. 기능 요구사항

> **번호 규약**: FR-GUI는 **절 단위 블록 넘버링**을 쓴다(§3.1=001–, §3.2=010–, §3.3=020–, §3.4=040–, §3.5=060–, §3.6=080–, §3.7=090–, §3.8=100–). 블록 끝의 번호 공백은 **의도적**이며 누락이 아니다. 도메인 문서(`09`/`12` 등)가 참조하는 FR-GUI 번호는 **유지된다** — 데스크톱↔웹 전환으로 ID를 재배정하지 않는다.

### 3.1 앱 셸 · 화면 구성

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-001 | GUI는 **웹 SPA 프런트엔드 + 헤드리스 파이썬 백엔드(FastAPI 등)** 구조여야 한다. 백엔드가 LeRobot Python API를 **인프로세스 임베드**하고 `Robot`·CAN·안전계층을 소유하며, 프런트엔드 정적 자산도 백엔드가 서빙한다. 브라우저는 **최신 WebGL·WebSocket 지원 브라우저** 하나면 되고 데스크톱 설치가 필요 없다. | M | GROUND §0 아키텍처(인프로세스 임베드); DECISIONS-v3 웹 단일 | **[확정] — PyQt6 데스크톱 판을 대체** |
| FR-GUI-002 | GUI는 §2.6의 **13개 화면(S-01…S-13)** 을 웹 라우트로 제공하고, 각 화면이 어느 도메인 명세를 구현하는지 화면 내에서 조회할 수 있어야 한다. | M | §2.6 | [신규구현] |
| FR-GUI-003 | 3D 뷰포트는 **단일 공유 컴포넌트**(Three.js + `urdf-loader` 기반)로 구현되어 S-01/S-02/S-04/S-05/S-06/S-08/S-09/S-11/S-12에 임베드될 수 있어야 하며, 화면마다 표시 레이어와 상호작용 권한(읽기전용/조작가능)이 다르게 설정될 수 있어야 한다. | M | §2.5, §2.6 | [신규구현] |
| FR-GUI-004 | GUI는 패널/뷰 레이아웃과 사용자 프리셋을 **백엔드 `runtime_config.json`(XDG)에 pydantic + atomic write로 영속**해야 하며(브라우저는 REST로 get/set), 서브객체 blast-radius 격리(malformed 필드만 defaults)를 적용해야 한다. | S | 참조 레포 `runtime_config.py:71-297`(atomic + blast-radius) | [신규구현] |
| FR-GUI-005 | **WebXR VR 진입점**(헤드셋 브라우저용)은 HTTPS(자체서명 인증서)로 서빙되어야 하며 인증서 경로를 설정할 수 있어야 한다. **이 HTTPS 서버는 VR 수신 전용 별도 컴포넌트**이며, 일반 GUI SPA 서빙(HTTP/HTTPS)과 포트를 구분한다(§2.7). | M | `dora-openarm-webxr` "WebXR requires HTTPS", `example/prepare_tls.sh`; §2.7 | [확정] |
| FR-GUI-006 | 시스템은 **네트워크 경계가 있는 서비스 포트**(브라우저↔백엔드 HTTP/WS, 원격 추론 gRPC 8080, VR UDP 5006, WebXR HTTPS 8443)를 설정 가능하게 하고, 기동 시 **포트 충돌을 감지·경고**해야 한다. | M | §2.7 | [확정] |
| FR-GUI-007 | GUI는 원격 추론 서버(ASYNC gRPC)에 접속할 때 **스키마/정책 feature 버전을 협상**하고, 불일치 시 추론 제어 UI를 잠그고 명확한 오류를 표시해야 한다. | M | `policy_server.py:587-694`(서버 스키마-권위, mismatch → `INVALID_ARGUMENT`) | [신규구현] |
| FR-GUI-008 | GUI는 **인터넷 연결 없이(에어갭)** 전 기능이 동작해야 하며(원격 추론/Hub 업로드 제외), **외부 CDN·폰트·텔레메트리에 의존해서는 안 된다** — SPA 번들·폰트·3D 자산·URDF/메시를 **전부 백엔드가 자체 호스팅**하고 CSP로 외부 출처를 차단한다. W&B 없는 로컬 손실 곡선 뷰(FR-GUI-124) 등 오프라인 대안을 반드시 제공해야 한다. | M | 웹 SPA 에어갭 요건 | [확정] — **웹이므로 자체 호스팅이 필수 요건** |

### 3.2 3D 뷰포트 — 자산 로딩과 씬 구성

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-010 | 백엔드는 **xacro를 전개하여 v2.0 URDF XML을 생성**하고, URDF + 링크 메시를 **정적 경로로 서빙**하며, 로드한 자산의 `{source_repo, commit_sha, robot_version}`를 기록해 v1 자산 로드를 차단해야 한다(`09` FR-SIM-009와 동일 게이트). 브라우저 `urdf-loader`는 이 URL에서 로드한다. | M | `openarm_description` v2.0 xacro 파이프라인; `urdf-loader` | [확정] |
| FR-GUI-011 | 백엔드는 URDF의 **`package://` 경로를 실제 서빙 URL로 재작성**하고, 메시 확장자 **allowlist(STL/DAE/OBJ)**·경로 화이트리스트를 적용해 브라우저가 허용된 자산만 로드하게 해야 한다. | M | `urdf-loader` `package://` 리라이트; 웹 자산 브리지 | [확정] — **웹 로더로 복원** |
| FR-GUI-012 | GUI는 **양팔(bimanual)을 단일 3D 씬에 동시 렌더링**하고, 좌/우 팔을 개별 표시/숨김할 수 있어야 한다. | M | 관절 이름이 `openarm_left_*` / `openarm_right_*`로 분리 실재 | [확정] |
| FR-GUI-013 | GUI는 시뮬레이션 모델과 실기 모델을 **동일 씬에 오버레이**(반투명 고스트)할 수 있어야 한다. | S | `09` §2.10(`bi_openarm_mujoco` Robot); sim 사전검증이 실기 구동의 전제 | [신규구현] |
| FR-GUI-014 | 3D 뷰포트는 **URDF의 visual 메시와 collision 메시를 토글**할 수 있어야 하며, 표시 모드 **Auto / Visual / Collision** 3종을 제공해야 한다(visual 부재 시 collision 폴백). **URDF `collisions.yaml`에 link7이 없으므로**(`12` FR-SAF-010) 그 결손을 뷰포트가 드러내야 한다. | M | `12` §2.4(link7 충돌 메시 부재) | [확정] |
| FR-GUI-015 | 3D 뷰포트는 씬 요소(로봇 / TF / 궤적 / 가상벽 / 워크스페이스 / 프러스텀 / 그리드 / 고스트)를 **레이어 단위로 on-off** 하고 그 조합을 **뷰 프리셋으로 저장**할 수 있어야 한다. | S | §2.5 | [신규구현] |

### 3.3 3D 뷰포트 — 실시간 상태 반영

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-020 | 3D 뷰포트는 백엔드가 **WS 텔레메트리로 발행하는 관절 상태**를 받아 **URDF 모델의 관절 각도를 실시간 반영**해야 한다. **URDF 관절 이름**은 `openarm_{left\|right}_joint{1..7}` / `openarm_{left\|right}_finger_joint1`(팔당 8), **LeRobot 관측 키**는 `{left\|right}_joint_{1..7}.pos` / `{left\|right}_gripper.pos`(**deg**)다. 🔴 **두 이름 공간의 매핑 테이블과 deg→rad 변환을 단일 모듈**에 두고, WS로는 **URDF 이름 + rad**를 실어 보내 브라우저 `urdf-loader.setJointValue(name, rad)`가 바로 소비하게 해야 한다. | M | `openarm_description` 관절 이름; `bi_openarm_follower._motors_ft`(`:99-104`); `openarm_follower.py:55-57`(deg); `09` FR-SIM-082 | [확정] |
| FR-GUI-021 | 관절 상태 스냅샷은 **매 프레임 전 관절을 포함**해야 하며, 부분 업데이트 병합에 의존해서는 안 된다. | M | 백엔드 스냅샷이 pos+torque를 한 트랜잭션에 읽는다(`12` §2.9.1) | [확정] |
| FR-GUI-022 | 백엔드는 제어 루프 주파수의 관절 상태를 **뷰 표시용으로 데시메이션**(기본 30 Hz, 상한 60 Hz)해 **WS로 발행**해야 한다. 데시메이션은 **렌더 예산 + WS 링크 대역폭**을 위한 것이다. | M | §2.4 | [확정] |
| FR-GUI-023 | 3D 뷰포트는 각 상태 스트림의 **age(마지막 샘플 이후 경과 ms)** 를 표시하고, 임계치 초과 시 로봇 모델을 **stale 시각화**(색상 + 배지)로 전환하며, stale 동안 **모든 제어 입력을 차단**해야 한다. 🔴 **stale 복구를 `Robot` 재연결로 해서는 안 된다** — 영점이 파괴된다(FR-GUI-081). | M | `openarm_follower.get_observation()`이 `state.get("torque", 0.0)`처럼 **결측을 0으로 채운다**(`:239-246`) → 모터 무응답도 관측 dict는 정상 형태 → **age 감시가 유일한 방어선** | [확정] |
| FR-GUI-024 | 3D 뷰포트는 **TF 트리(프레임 계층)** 를 표시하고, 임의 프레임을 **fixed frame**으로 선택하며, 개별 프레임 축을 표시/숨김할 수 있어야 한다. | M | `openarm_control` 프레임 정의 | [확정] |
| FR-GUI-025 | 3D 뷰포트는 **EE 포즈**를 좌표축으로 표시하고, 선택 기준 프레임에 대한 위치(m)·자세(쿼터니언/RPY)를 수치로 병기해야 한다. 양팔 각각 독립 표시. FK 소스는 백엔드 **`openarm_control.Kinematics.fk_bimanual(right, left)`**(**MJCF 월드, m/rad**), WS로 발행. 🔴 **입력은 rad, LeRobot 관측은 deg** — 변환 필수. | M | `openarm_control/kinematics.py fk_bimanual()` 실측 0.037 ms; `09` FR-SIM-082 | [확정] |
| FR-GUI-025b | 뷰포트가 `urdf-loader` 기반 브라우저 FK를 보조로 쓰는 경우 그 결과가 **백엔드 `openarm_control`의 MJCF 기반 FK와 일치하는지 검증**하고, 불일치가 임계를 넘으면 EE 수치를 **백엔드 값으로 강제**하며 경고해야 한다. **명령을 만드는 것은 MJCF(IK)이므로 EE 수치의 정본도 MJCF다.** | S | URDF v2.0와 MJCF v2의 링크/조인트 원점 동일성 **[미확인]**(`09` §5); MJCF 내부 불일치(joint7) | [신규구현] |
| FR-GUI-026 | 3D 뷰포트는 **목표 자세와 현재 자세를 동시 오버레이**(목표 = 반투명 고스트)하고, 관절별 오차(rad/deg)·EE 위치 오차(mm)를 표시해야 한다. | M | 텔레옵 IK가 개루프 → 목표-현재 괴리가 화면에서 보인다 | [확정] |
| FR-GUI-027 | 3D 뷰포트는 **궤적을 폴리라인으로 표시**하고 최소 3종을 구분해야 한다: ① 계획 궤적, ② 실행된 EE 경로, ③ 텔레옵 리더(VR) 입력 경로. 표시 길이는 설정 가능. | S | — | [신규구현] |
| FR-GUI-028 | 3D 뷰포트는 **가상벽/금지영역**을 반투명 지오메트리로 표시하고, 침범/임박 시 하이라이트해야 한다. 편집은 S-12에서. | M | `12`(SAF)이 정의 | [신규구현] |
| FR-GUI-029 | 3D 뷰포트는 **워크스페이스(도달 가능 영역)** 를 표시하고, 목표 포즈가 밖이면 사전 경고해야 한다. | S | — | [신규구현] |
| FR-GUI-030 | 3D 뷰포트는 각 카메라의 **뷰 프러스텀**을 표시할 수 있어야 한다(전송 스트림당 1개). 위치·자세는 hand-eye 캘리브레이션 결과(TF)에서, FOV는 해당 슬롯 하드웨어 스펙에서 취하며 **그 정본은 `06`이 소유**한다. 캘리브레이션이 stale이면 프러스텀을 stale 표시. | S | `06` 카메라 하드웨어 표; `easy_handeye2` 결과 | [확정] |
| FR-GUI-031 | 3D 뷰포트는 **포인트클라우드**를 표시할 수 있어야 하며(다운샘플/LOD 적용, 기본 비활성), **뎁스 스트림이 있는 구성에서만** 적용된다. 정본 카메라 구성의 뎁스 유무는 **`06`이 소유**하며, 뎁스 소스가 없으면 표시할 포인트클라우드가 없다. | C | `06`(뎁스 소스 정본); `dataviz` LOD 상식 | [선택] |
| FR-GUI-032 | 3D 뷰포트는 **orbit / pan / zoom**과 **뷰 프리셋**(정면/좌/우/상단/EE 추종/손목 카메라 시점/마지막 뷰)을 단축키로 제공해야 한다. | M | Three.js `OrbitControls` | [신규구현] |
| FR-GUI-033 | 3D 뷰포트에서 관절 슬라이더 또는 EE 드래그로 **목표를 지정하는 화면(S-04)** 에서는, 입력값이 **활성 리밋 프로파일로 클램프**되고 클램프 발생을 시각 표시해야 한다. **어떤 리밋 세트가 활성인지(v2 URDF rad 정본 vs 소프트 클램프) 항상 화면에 표시**해야 한다. | M | 리밋 정본 = v2 URDF rad(§2.3, §5 Q-2) | [확정] |
| FR-GUI-034 | 3D 뷰포트가 **제어 입력 창구가 되는 모드**에서는 별도의 명시적 **arm/enable 동작** 없이는 명령이 발행되지 않아야 한다. 마우스 조작만으로 로봇이 움직여서는 안 된다. | M | `connect()`가 확인 없이 영점을 바꾸는(F-3′) 은밀한 등가물이 있어 "조작 전 명시적 확인" 원칙이 강화된다 | [확정] |

### 3.4 카메라 · 스트림 상태 표시 (단일 WS 바이너리 프레임)

> 🔴 **이 절이 다시 쓰였다(웹 복원).** 데스크톱 판은 "인프로세스 grab, 브라우저로 스트리밍 안 함"이라 전송 FR을 전부 폐기했었다. 웹 SPA에서는 **카메라 프레임을 백엔드가 인코딩해 브라우저로 스트리밍하는 것이 웹 선택의 실재 비용**이다. 다만 **단일 WebSocket 하나로 멀티플렉싱**하며(D-2), 데스크톱 이전 v1의 오버엔지니어링(WebRTC 분리·foxglove/rosbridge·CBOR·별도 채널 프로토콜)은 **여전히 채택하지 않는다.**

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-040 | GUI는 **단일 WebSocket 위에서 텔레메트리·명령·카메라 프레임을 멀티플렉싱**해야 한다(D-2 프로토콜 분리 금지). 카메라 프레임은 **바이너리 프레임**으로, **카메라ID + 채널 태그**(RGB/뎁스)를 헤더에 실어 다중 카메라를 구분한다. 텔레메트리(텍스트/소형 바이너리)와 카메라(대용량 바이너리)를 같은 WS에서 프레임 타입으로 분리한다. 🔴 **별도 WebRTC 스트림으로 분리하지 않는다.** | M | §2.1, §2.4; DECISIONS-v3 D-2 | **[신규구현] — 웹 전송 복원** |
| FR-GUI-041 | 백엔드는 카메라 프레임을 **인코딩해 WS로 전송**해야 한다: **RGB = JPEG**(품질 설정 가능), **뎁스 = 16-bit PNG 또는 컬러맵 인코딩**(무손실/시각화 선택). 해상도·fps·JPEG 품질은 설정 가능하고 정본은 `06`이 소유한다. 브라우저는 `<canvas>`/`<img>`(또는 `createImageBitmap`)로 렌더한다. | M | DECISIONS-v3(cv2 JPEG 인코딩, 뎁스 16bit PNG/컬러맵); `06`(해상도·fps 정본) | **[신규구현]** |
| FR-GUI-042 | 백엔드는 카메라 스트리밍이 **제어 루프를 굶기지 않도록** 프레임을 **스로틀·드롭(백프레셔)** 하고, 인코딩을 제어 루프와 **별도 워커**에서 수행해야 한다. WS 송신 버퍼가 임계를 넘으면 오래된 프레임을 버리고 **드롭 카운터를 상시 표시**한다. 🔴 카메라 인코딩 부하는 **NFR-GUI-011의 감시 대상**이다. | M | §2.1 F-10′; NFR-GUI-011(제어 루프 지터) | **[신규구현] — 웹 선택의 실재 비용** |
| FR-GUI-043~047 | ~~foxglove-sdk / rosbridge CBOR / WebRTC DataChannel / 채널별 별도 프로토콜 / raw 무압축 전송~~ → **채택하지 않음.** 실시간 채널은 단일 WS 하나로 통일하며 대체 전송 스택을 병행하지 않는다. | — | §2.1(D-2 단일 WS) | **미채택(오버엔지니어링)** |
| FR-GUI-048 | GUI는 각 스트림(**활성 카메라 전송 스트림 · VR 포즈 · 관절 상태**)에 대해 **rolling FPS, `jitter_ms = (max(Δt)−min(Δt))×1e3`, 드롭 수, 수신 지연**을 실시간 계측·표시해야 한다. 계측 대상 수를 **상수로 하드코딩하지 말고 `robot.observation_features`에서 유도**해야 한다. 윈도 기본: 카메라 60 / VR 120 프레임. 목표 대비 **95% 미만이면 WARN**. | M | `dora-openarm-data-collection-ui` `_update_camera_stats`/`_update_vr_stats`; `motor_sampling_check`의 `actual_hz < 0.95 × target_hz → [LOW!]` | [확정] |
| FR-GUI-050 | 브라우저와 백엔드는 **WS 하트비트(ping/pong)** 를 유지하고, WS 링크가 끊기거나 백엔드 제어 루프가 응답하지 않거나 `get_observation()` 예외가 지속되면 실시간 패널을 **stale 표시 + 제어 입력 즉시 차단**해야 한다. 🔴 복구를 `Robot` 재연결로 해서는 안 된다(FR-GUI-081). 브라우저는 WS 재접속만 시도하며 백엔드 `Robot`은 건드리지 않는다. | M | §2.4; F-3′ | [신규구현] |

### 3.5 공통 UI 요소

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-060 | GUI는 **로봇 상태 배지**를 전 화면 상단에 상시 표시해야 한다. 최소: **연결 상태**, **현재 모드**(LiveLinkMode, 모드 배지 = 상태전이), **E-Stop 상태**, **활성 게인/리밋 프로파일명**, **제어권 보유자**. | M | — | [신규구현] |
| FR-GUI-061 | GUI는 **CAN 인터페이스별 상태 배지**를 상시 표시해야 한다: **`flock` 락 보유 · 우리 `Robot`의 `is_connected` · `connect()` 시각 · 바인딩 소켓 수 · 침입 프로세스 PID(있으면)**. 🔴 정본 소유자는 **항상 우리 백엔드 하나**이므로 "누가 소유하는가"가 아니라 "우리가 락을 쥐었는가 + 침입자가 있는가"로 표시한다. | M | SocketCAN 비배타 bind(F-1) → 소유권은 애플리케이션이 만든다 | [확정] |
| FR-GUI-062 | GUI는 CAN 프리플라이트 결과를 표시해야 한다: **ifindex별 바인딩 소켓 수**(`/proc/net/can/raw`), **링크 상태**(`ERROR-ACTIVE`/`BUS-OFF`), **비트레이트**(nominal `1000000` / data `5000000`), **에러 카운터**. **바인딩 소켓 > 1이면 제어 UI 차단.** 🔴 **CAN-FD가 `ip link`에서 켜져 있는지 검증**하고 미설정 시 기동 차단. | M | `ip -details -statistics link show canN`; python-can이 `bitrate`/`data_bitrate`를 무시(F-7′) | [확정] |
| FR-GUI-063 | GUI는 **소프트 스톱**(모터 토크로 자세 유지)과 **하드 E-Stop**(전원 차단)을 **서로 다른 컨트롤**로 제공하고 시각 구분을 명확히 해야 한다. | M | OpenArm은 홀딩 브레이크가 없다 — 전원 차단 시 부하 급락 | [확정] |
| FR-GUI-064 | GUI는 하드 E-Stop 컨트롤 근처에 **"전원 차단 시 파지 중인 물체가 낙하한다"** 경고를 상시 표시해야 한다. | M | 공식 Safety Guide 인용 | [확정] |
| FR-GUI-065 | **비상정지 컨트롤은 모든 화면·모든 모드·제어권 보유 여부와 무관하게 항상 접근 가능**해야 한다. | M | `dora-openarm-evaluation-ui` "Keyboard shortcuts and an emergency stop" | [확정] |
| FR-GUI-066 | GUI는 **알림/경고 센터**를 제공해야 한다: 심각도(INFO/WARN/ERROR/CRITICAL), 소스, 타임스탬프, 상세, **ack 상태**. ERROR 이상은 ack 전까지 배지 유지. | M | — | [신규구현] |
| FR-GUI-067 | GUI는 **단축키**를 제공하고 매핑을 조회·재정의할 수 있어야 한다. 최소: 비상정지, 소프트 스톱, 에피소드 start/success/fail/cancel, 모드 전환, 3D 뷰 프리셋. | M | `dora-openarm-evaluation-ui` "Keyboard shortcuts + emergency stop" | [확정] |
| FR-GUI-068 | GUI는 **현재 활성 게인/리밋 프로파일명과 값**을 조회할 수 있어야 하며, 프로파일 미로드 상태에서 제어를 시작할 수 없어야 한다. | M | 게인·리밋이 명명 프로파일(§2.3) — 어느 게 활성인지 안 보이면 물리 강성이 달라져도 알 수 없다 | [확정] |
| FR-GUI-069 | GUI는 모든 각도 값에 **단위(rad/deg)와 기준 프레임(URDF 프레임 / 캘리브레이션 후 모터 프레임)** 을 명시해야 한다. | M | URDF는 rad, LeRobot 리밋은 캘리브레이션 후 모터 프레임 deg — 혼동 시 조용히 틀린다 | [확정] |
| FR-GUI-070 | GUI는 **더미(하드웨어 없음) 모드**에서 전 화면에 명확한 배너를 표시해야 한다. | M | enactic dummy 노드 실재 | [확정] |
| FR-GUI-071 | GUI는 **프리플라이트 체크** 결과를 배너로 표시하고, 실패 항목이 있으면 데이터 수집·텔레옵 시작을 차단해야 한다. 항목: ① CAN 소유권·링크, ② 카메라 연결·USB 링크 속도, ③ **`use_velocity_and_torque` = true**, ④ 캘리브레이션 유효성, ⑤ 디스크 여유(≥1시간), ⑥ 프로파일 로드. | M | CAM FR; F-4′ | [확정] |
| FR-GUI-072 | 🔴 GUI는 **`use_velocity_and_torque`의 현재 값을 전 화면 상단 배지에 상시 표시**하고, `false`이면 **경고 색상 + "토크·속도 데이터가 기록되지 않습니다"**를 표시해야 한다. 이 플래그는 **팔로워·리더를 묶는 단일 스위치**로만 노출하고 개별 설정 UI를 제공해서는 안 된다. 충돌 감지·트윈 잔차·바이래터럴 기능은 이 값이 `true`일 때만 활성화되어야 한다. | M | 🔴 `config_openarm_follower.py:71` (**기본 OFF**) → 켜지 않으면 조용히 위치-only 데이터셋. 팔로워만 True면 `build_dataset_frame`이 `values["joint_1.torque"]`에서 **KeyError 런타임 사망**(F-4′) | **[신규구현]** |
| FR-GUI-073 | 🔴 GUI는 **`--dataset.push_to_hub`의 현재 값을 상시 표시**하고, 기본값(`True`)일 때 **위험 색상 + "수집 데이터가 Hugging Face Hub로 업로드됩니다"** 경고를 띄워야 한다. `true`로 수집을 시작하려 하면 **명시적 확인**을 요구해야 한다. `private`/`tags`도 함께 표시. | M | 🔴 `configs/dataset.py` `push_to_hub: bool = True`; `lerobot_record.py:534-538`의 `finally`가 `push_to_hub` 호출(F-5′) | **[신규구현]** |
| FR-GUI-074 | GUI는 데이터셋 이름 표시 시 **`stamp_repo_id()`가 붙인 타임스탬프 포함 실제 이름**을 읽어야 한다. 사용자 입력 이름을 그대로 표시해서는 안 된다. | S | `configs/dataset.py:75-83` — `repo_id`에 `_%Y%m%d_%H%M%S` 자동 부착(`--resume`에서는 미호출) | [신규구현] |

### 3.6 모드 전환 — **`Robot` 객체 상태 전이의 GUI 노출** (프로세스 재시작 아님)

> 🔴 모드는 **백엔드 같은 프로세스·같은 `Robot` 객체 위의 상태 전이**(`LiveLinkMode`)다. AppMode(CLIENT/LOCAL/SERVER)만 백엔드 시작 시 선택이고, 그 안의 텔레옵/기록/추론/수동 전환은 상태머신이다. **"재연결"이 안전 사고**이기 때문에(F-3′) 이 절이 GUI를 쉽게 만들지 않는다.

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-080 | GUI는 **모드 목록과 각 모드의 `send_action()` 권리 보유자**를 명시적으로 표시해야 한다. 최소: `IDLE`(권리 없음) / `MANUAL` / `TELEOP_VR` / `TELEOP_KER` / `RECORD` / `INFERENCE` / `SIM`(시뮬 `Robot`) / `MOTOR_SETUP`(CLI — **CAN 미점유에서만 허용**). **전 모드가 백엔드 같은 프로세스·같은 실기 `Robot` 객체를 공유한다.** | M | §2.1 F-3′; `hw_worker.py:169-183`(LiveLinkMode) | **[신규구현]** |
| FR-GUI-081 | 🔴 GUI는 **모드 전환에 `Robot.disconnect()` / `connect()`를 호출해서는 안 된다.** 세션당 `connect()`는 **정확히 1회**이며 모드 전환은 **`send_action()` 권리의 이동**으로만 구현되어야 한다. GUI에 **"재연결" 버튼을 제공해서는 안 된다.** | M | 🔴 `openarm_follower.py:152-153` — `connect()`가 `set_zero_position()` 호출 → 조인트 리밋·가상벽·데이터셋 좌표계 동시 무효, 무에러(F-3′, `12` FR-SAF-071) | **[신규구현]** |
| FR-GUI-082 | 모드 전환은 **권리 이양 시퀀스**(현 소유자 명령 중단 → **`STOP_HOLD` 유지** → 신규 소유자 권리 획득 → 첫 명령 검증)로 표현되고, 각 단계 진행·실패 지점을 표시해야 한다. 🔴 **어느 단계에서도 CAN 명령 스트림이 끊겨서는 안 된다** — 중단 = 인에이블 이탈 = **낙하**. | M | `12` §2.3; F-8b | **[신규구현]** |
| FR-GUI-083 | 🔴 백엔드는 **LeRobot CLI(`lerobot-record`/`-teleoperate`/`-rollout`/`-calibrate`)를 모드마다 서브프로세스로 스폰해서는 안 된다.** 각 CLI가 시작 시 `robot.connect()`·종료 시 `disconnect()`를 하므로 **모드 전환마다 영점이 파괴된다.** 반드시 **Python API를 임베드**하고 `record_loop(...)`에 `events` dict를 우리가 소유해 넘긴다. | M | 🔴 LeRobot CLI는 각각 독립 프로세스; `lerobot_record.py:228-248` `record_loop(events=…)` → Python API 직접 호출 가능 | **[신규구현]** |
| FR-GUI-084 | 🔴 GUI는 **부득이한 재연결**(하드웨어 교체·CAN 복구)에 대해 ① **현재 자세가 rest인지 3D 뷰포트와 관절각으로 확인**, ② **"현재 자세가 새 영점이 된다" 경고**, ③ **이중 확인**, ④ **감사 로그**를 강제해야 한다. 확인 화면에 현재 자세와 rest 자세의 관절별 차이를 표시. | M | 🔴 `connect()` → `set_zero_position()`(F-3′) | [확정] |
| FR-GUI-085 | GUI는 **CAN 락 강제 회수(force takeover)** 를 제공할 수 있으나 **2중 확인 + 사유 입력 + 감사 로그**를 강제해야 한다. 🔴 **회수 전 "토크 해제"를 수행해서는 안 된다**(=낙하). 회수는 **`STOP_HOLD` 유지** 상태로 이루어져야 한다. | S | 교착 복구 경로 필요; `12` §2.3(브레이크 없음) | **[신규구현]** |
| FR-GUI-086 | GUI는 **`openarm-can-cli`/`cansend`/`openarm_teleop` 등 외부 CAN 클라이언트를 실행하는 경로를 세션 중에 노출해서는 안 되며**, `MOTOR_SETUP` 모드(CAN 미점유)에서만 허용해야 한다. | M | `flock`은 협조적 — 백엔드가 그런 경로를 열어주지 않는 것이 1차 방어선 | [확정] |
| FR-GUI-087 | GUI는 제어 주파수 설정에서 **1000 Hz 초과 입력을 차단**하고 값에 따른 **CAN 버스 부하(%)** 를 표시해야 한다. | M | openarm_can 공식: 8모터에서 1000 Hz 초과 시 CAN 불안정(F-9) | [확정] |
| FR-GUI-088 | 백엔드는 **`record_loop()`의 `events` dict**(`{"exit_early","rerecord_episode","stop_recording"}`)를 **직접 소유·조작**해야 한다. 🔴 **`stop_recording`을 E-Stop에 연결해서는 안 된다** — 에피소드 제어이지 안전 정지가 아니다(F-8b). dora 데몬/coordinator는 우리 경로에 없다. | M | `lerobot_record.py:228-248`; `utils/keyboard_input.py:153-170`(환경 의존 → Python API 직접 호출이 안전) | **[신규구현]** |

### 3.7 제어권 — 명령 소스 배타성

> 🔴 **명령 소스가 정확히 하나(VR / GUI 조그 / 정책)** 라는 구조적 배타성은 `LiveLinkMode` 상태머신(한 값만 활성)으로 성립한다. 웹이므로 **여러 브라우저 클라이언트가 동시에 접속할 수 있으나**, 백엔드는 **한 시점에 제어권(command authority)을 정확히 한 WS 클라이언트에만** 부여하고 나머지는 **관찰자(읽기전용)** 로 둔다. 이는 다중 사용자 세션 관리 시스템이 아니라 **단일 제어권 중재**다(오버엔지니어링 회피).

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-090 | 시스템은 **명령 소스 배타성**을 보장해야 한다 — VR·GUI 조그·정책 중 **정확히 하나만** `send_action()` 권리를 갖고, 나머지는 억제되어야 한다. `LiveLinkMode`의 구조적 mutex로 강제한다. | M | `hw_worker.py:169-183`(LiveLinkMode, 한 값만 활성) | [확정] |
| FR-GUI-091 | 제어권은 **CAN 디바이스 락(L1, `flock`)** 과 **명령 소스 락(L2, LiveLinkMode)** 으로 2단 결합되어야 한다. L1(단일 백엔드 프로세스 소유)만으로는 프로세스 내부의 두 명령 소스 충돌을 막지 못한다. | M | §2.1 F-1 · F-2 | [확정] |
| FR-GUI-092 | 백엔드는 **제어권(command authority)을 한 시점에 한 WS 클라이언트에만** 부여하고, 나머지 접속 브라우저는 **관찰자(읽기전용, 텔레메트리·카메라만 수신)** 로 둔다. 제어권 이양은 **명시적 요청 + 현 보유자 통지**로 이루어지며, 관찰자는 `send_action` 경로가 서버측에서 거부되어야 한다. | M | 웹 다중 접속 가능 → 서버측 단일 제어권 중재 필요; F-1·F-2 | **[신규구현] — 웹 다중클라이언트 대응(최소)** |
| FR-GUI-093 | 백엔드 제어 루프가 크래시하거나 제어 하트비트가 임계 시간 끊기면 시스템은 **즉시 소프트 스톱(`STOP_HOLD`)** 으로 전이해야 한다. 마지막 셋포인트가 MIT 게인으로 계속 유지되는 구조라 프로세스가 죽어도 로봇은 안 멈춘다 — 워치독이 유일한 방어선이다. **WS 클라이언트 이탈은 소프트 스톱 사유가 아니다**(제어권은 서버가 쥔다) — 단, 제어권 보유 클라이언트의 하트비트 소실은 `STOP_HOLD`로 전이한다. | M | 워치독 부재 → 크래시 후에도 마지막 명령 유지; `12` §2.3 | [확정] |
| FR-GUI-096 | **텔레옵(VR) 세션이 활성인 동안 GUI 수동 조작 컨트롤은 비활성**이어야 한다. 두 입력 소스가 동시에 명령을 발행할 수 있는 UI 상태가 존재해서는 안 된다. | M | 명령 소스 배타성(FR-GUI-090) | [확정] |
| FR-GUI-094/095 | ~~관리자 승인 기반 다중 사용자 세션 목록 / 락 요청·승인 워크플로 확장~~ → **최소화.** 제어권 중재는 FR-GUI-092의 단일 제어권 모델로 충분하며, 역할 기반 세션 관리 시스템은 만들지 않는다. 원격 추론 서버(AppMode SERVER)의 접근 제어는 `11`(INF)이 소유한다. | — | 오버엔지니어링 회피 | **미채택(최소화)** |

### 3.8 화면별 고유 요구사항

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| FR-GUI-100 | **S-01 대시보드**는 한 화면에서 표시해야 한다: 로봇 연결/모드, **CAN 락 상태 + 침입자 유무**(FR-GUI-061), **`use_velocity_and_torque`**(FR-GUI-072), **`push_to_hub`**(FR-GUI-073), **카메라 FPS/지터**(타일 수는 상수가 아니라 활성 전송 스트림 수에서 유도), 디스크 여유 + 예상 소진 시각, GPU/VRAM, **LeRobot 루프 사이클 타임 p95**(NFR-GUI-011), 최근 세션, 미ack 경고 수. | M | §2.4; `06` FR-CAM-001; F-4′·F-5′ | [확정] |
| FR-GUI-101 | **S-06 카메라**는 **활성 전송 스트림 전체**를 **타일 그리드**로 동시 표시하되, 타일 수를 **상수로 하드코딩하지 말고** LeRobot `robot.observation_features`의 카메라 키셋에서 **런타임 유도**해야 한다. 각 타일은 **WS 바이너리 JPEG 프레임을 `<canvas>`/`<img>`로 렌더**하고 **UI 라벨과 데이터셋 키(`observation.images.…`)를 함께** 표시(둘이 다르다). **뎁스 타일은 컬러맵으로 표시**한다. 백엔드 프리뷰 grab이 캡처 CPU를 잠식하지 않아야 하며(**비블로킹 `read_latest()`**), 녹화 중 프리뷰(WS 송출)를 끌 수 있어야 한다. 스테레오/뎁스 슬롯의 분할·정본은 **`06`이 소유**한다. | M | `bi_openarm_follower._cameras_ft`; `read_latest()` "UI visualization"; DECISIONS-v3(WS JPEG, 뎁스 컬러맵); `06`(슬롯·분할 정본) | [확정] |
| FR-GUI-102 | **S-07 데이터 수집**은 에피소드 루프를 **start → success/fail/cancel → reset → repeat**로 제공하고, 에피소드별 성공/실패 + 노트를 기록하며, 중단 세션을 **Resume**할 수 있어야 한다. 태스크 프롬프트를 부착. 🔴 **구현은 `record_loop()`의 `events` dict를 백엔드가 소유**한다(CLI stdin `n`/`r`/`q` 주입은 pynput/TTY 백엔드가 환경 의존적이라 신뢰 불가). 🔴 **성공/실패 라벨은 LeRobot 네이티브에 없으므로 사이드카 저장.** Resume은 **stamped `repo_id`**(FR-GUI-074)를 그대로 준다. | M | `lerobot_record.py:228-248,469-516`; `keyboard_input.py:153-170`; `constants.py:80-87`(`success` 없음); `configs/dataset.py:75-83` | **[신규구현]** |
| FR-GUI-103 | **S-07**은 녹화 중 **카메라별 드롭 프레임 수를 실시간 표시**하고 에피소드 종료 시 총 드롭을 리포트하며, 드롭률 임계 초과 에피소드를 경고 플래그 표시(~2% 허용 / ~5% 과부하)해야 한다. **WS 송출 드롭과 캡처/인코딩 드롭을 구분**해 표시한다. | M | LeRobot 스트리밍 인코딩 백프레셔 `"Encoder queue full for {camera}, dropped N frame(s)"`; FR-GUI-042(WS 백프레셔) | [확정] |
| FR-GUI-104 | **S-08 데이터셋**은 에피소드를 **타임라인 스크럽**으로 재생하며 카메라 영상과 **`observation.state` 채널 플롯**(`names`로 `.pos`/`.vel`/`.torque` 분리 — **한 벡터의 부분 인덱스**), `action`, 성공/실패 라벨을 동기 표시해야 한다. 🔴 `timestamp`는 벽시계가 아니라 `frame_index/fps`(합성값)이므로 실제 캡처 지터는 **사이드카 `capture_ts`**로 본다(`06`). 🔴 성공/실패 라벨은 사이드카에서 읽는다. | M | `feature_utils.py:68-89`; `dataset_writer.py:207-210`(`timestamp=frame_index/fps`); `constants.py:80-87` | [확정] |
| FR-GUI-105 | **S-11 추론/평가**는 태스크 스위처, 태스크별·세션별 성공률, **액션 큐 크기 실시간 시각화**, 체크포인트 패널, takeover, **InferenceMode(LOCAL/ASYNC) 선택**을 제공해야 한다. 성공률은 **Wilson 95% CI**와 함께 표시하고 **N<20 비교는 "통계적으로 무의미"로 표기**해야 한다. 🔴 **실행 엔진은 `lerobot-rollout`(실기)이며 `lerobot-eval`이 아니다**(후자는 gym 전용). **성공/실패 라벨링·성공률 집계는 LeRobot에 없으므로 전량 우리 몫.** | M | 🔴 `configs/eval.py:29-31`(`env` 필수 → gym 전용); `lerobot_rollout.py:85`; `policy_service.py`(LOCAL/ASYNC) | **[신규구현]** |
| FR-GUI-106 | **S-05 텔레옵**은 **제어채널 지연(C-Lat)** 을 실시간 표시하고 **헤드셋 내부 지연은 소프트웨어로 측정 불가함을 명시**해야 한다. VR 포즈 스무더의 `min_cutoff`/`beta`/`d_cutoff`를 **런타임 설정으로 노출**하고 이론 위상 지연 `τ = 1/(2π·f_c)`를 병기해야 한다. 🔴 **스무더는 우리 VR `Teleoperator`(백엔드) 안에 있다** — 상류 One-Euro(`smoothing.py`)는 dora 의존 0인 순수 Python이라 그대로 이식(Apache-2.0). | M | 상류 `OneEuroPoseSmoother(min_cutoff=2.0, beta=0.04, d_cutoff=1.5)` → τ≈79.6 ms(생성자 하드코딩) | [확정] |
| FR-GUI-107 | **S-05**는 텔레옵 시작 시 **리더(VR) 포즈와 팔로워 현재 자세를 정렬하는 단계**를 강제하고 정렬 완료 전 추종을 시작하지 않아야 한다. 클러치(grip) 상태를 상시 표시하고 클러치 해제 시 기준점 리셋을 표현. 🔴 **정렬 상태머신은 우리 `Teleoperator`(백엔드) 안에** 두어(LeRobot `Teleoperator` ABC에 정렬 개념 없음) `get_action()`이 정렬 전에는 현재 관절각을 그대로 반환(no-op)해야 한다. 🔴 **joint6 리밋이 ±45°로 좁아** VR 1:1 매핑 시 상시 충돌 → **회전 스케일을 위치와 분리**해야 한다. | M | 상류 `STOPPED→STARTED→ALIGNED`(`--align-threshold 0.1`) **개념만** 차용; v2 URDF joint6 ±45°(§2.3) | [확정] |
| FR-GUI-108 | **S-03 모터 설정**은 CAN ID 맵(send `0x01–0x08` / recv `0x11–0x18`), 모터 타입, **게인/리밋 프로파일 편집·전환·검증**(compliant/stiff, `kp∈[0,500]`/`kd∈[0,5]` 검증), 모터별 **온도(T_MOS/T_Rotor)** 를 표시해야 한다. 온도는 상태 프레임에 이미 실려 오므로 **별도 폴링 UI를 만들지 않아야** 한다. **그리퍼는 POS_FORCE + open/close 엔드포인트 rad 캡처**로 다룬다(파지력을 N으로 표시하지 않는다 — pu↔N 미확정, §5 Q-9). | M | `dm_motor_control.cpp::parse_motor_state_data`(온도); `12` FR-SAF-062(게인 검증); `03`(MOT)이 그리퍼 소유 | [확정] |
| FR-GUI-109 | **S-13 시스템/로그**는 프로세스·포트 매니페스트(§2.7), 각 프로세스의 **RT 클래스(`chrt -p`) · CPU 어피니티 · `mlockall` 성공 여부**, 진단 번들을 제공해야 한다. | M | RT 승격 대상은 백엔드 제어 루프(NFR-GUI-008) | [확정] |
| FR-GUI-110 | **S-09 시뮬레이션**은 실기 구동 전 **백엔드 `Robot` 객체만 시뮬(`bi_openarm_mujoco`)로 바꿔 동일 텔레옵·동일 액션 경로를 먼저 검증**하는 드라이런 모드를 제공해야 한다(`09` FR-SIM-029). 🔴 **전환에 `disconnect()`/`connect()`를 하지 않는다**(FR-GUI-081). GUI는 **MuJoCo 모델을 하드웨어 사양의 교차확인 근거로 표시해서는 안 된다.** 트윈·드라이런은 실기 stiff(230) 게인을 요구한다(`09` FR-SIM-028b). | M | `09` §2.10; MJCF 내부 불일치(joint7) — 시뮬 자산 버그가 실기 명령에도 영향(`09` §1.1) | [확정] |
| FR-GUI-111 | **S-12 충돌·안전**은 가상벽/금지영역을 3D 뷰포트에서 **직접 편집**하고 충돌 반응 정책(소프트 스톱 / 속도 스케일 하향 / 하드 E-Stop)을 선택할 수 있어야 하며, **충돌 감지의 기본 반응이 전원 차단이어서는 안 된다.** | M | 홀딩 브레이크 부재 → 전원 차단 = 낙하(F-8) | [확정] |
| FR-GUI-112 | **S-02 로봇 연결**은 CAN 인터페이스 자동 탐지·설정·진단을 수행하고 CAN-FD(공칭 1 Mbps / 데이터 5 Mbps)·socketcan을 지원해야 한다. **`side`(left/right) 선택을 강제**(미지정 시 전 축 ±5°로 잠김)하고, 브링업은 **`connect_readonly()`(torque-OFF)로 시작**해 손으로 방향·영점을 검증한 뒤 명시적 set_zero → Enable Torque 순으로 진행해야 한다(`12` FR-SAF-075). | M | `lerobot-setup-can`; `config_openarm_follower.py`(±5°); 참조 레포 브링업 플로우 | [확정] |

#### 3.8.1 S-04 수동 동작 — 화면 고유 요구사항

> 도메인 로직(조그 산식, IK 백엔드, 중력보상, 클램프 순서, 정지 카테고리)은 **`04-수동-동작.md`(영역 `MAN`)가 소유한다.** 아래는 화면 창구다.

| ID | 요구사항 | 우선 | 근거 (매핑) | 비고 |
|---|---|---|---|---|
| FR-GUI-113 | **S-04**는 **관절 선택기**(팔 left/right × J1–J7 + 그리퍼 J8), **연속(hold-to-move)/스텝 토글**, **조그 스텝 크기**(최소 `{0.1,0.5,1,5}` deg), **전역 속도 스케일(0–100%)** 을 제공해야 한다. 연속 모드는 버튼을 떼면 즉시 정지, 속도 스케일은 URDF velocity 리밋 초과 불가. | M | FR-MAN-008/009/010/011 | [확정] |
| FR-GUI-114 | **S-04**는 **카테시안 조그**(병진 ±X/±Y/±Z, 회전 ±R/±P/±Y)를 제공하고 **기준 프레임을 `base`/`tool`/`world`**에서 선택할 수 있어야 한다. 선택 프레임·TCP를 상시 표시하고 `base`/`world` 회전 동일(리프터 높이만 병진 차이)을 오인하지 않게 표기. | M | FR-MAN-018/019/022/023 | [확정] |
| FR-GUI-115 | **S-04**는 **엘보(널스페이스) 자세 슬라이더**를 제공(EE 포즈 고정한 채 스위블 각 조정, EE 이동 없음을 3D로 확인). | M | FR-MAN-024(mink `posture` task) | [확정] |
| FR-GUI-116 | **S-04**는 **Freedrive 진입/이탈 버튼과 상태 표시**를 제공해야 한다. 진입은 **데드맨(hold-to-activate)**, 데드맨 유지·잔여 하트비트 여유를 상시 표시, 버튼 해제/타임아웃 시 **즉시 위치 홀드(Cat 2)** 로 이탈했음을 표시. Freedrive 중임을 전 화면 배너로 알림. | M | FR-MAN-029/031/050/051(하트비트 200 ms) | [확정] |
| FR-GUI-117 | **S-04**는 **티칭 포인트 리스트/저장/재생**을 제공해야 한다: 1버튼 캡처, 리스트 CRUD/재정렬/복제, 파일 저장·로드, 재생 이동, 다중 포인트 시퀀스(dwell + 그리퍼). **재생 전 궤적 사전 검증(리밋·속도/가속·충돌)을 표시하고 실패 시 실행 버튼 비활성.** | M | FR-MAN-039/040/041/044/045 | [확정] |
| FR-GUI-118 | **S-04**는 **홈 복귀 버튼**을 제공하고 활성 홈 프로파일명·목표 자세를 실행 전 표시하며 궤적 사전 검증 통과 시에만 실행되어야 한다. 홈 정의가 둘 이상 실재하므로 **어느 정의가 활성인지 명시.** | M | FR-MAN-047/048; `04` §2.10 | [결정필요] — 홈 정의 정본은 `04` 소유 |
| FR-GUI-119 | **S-04**는 **리밋 근접 시각 경고**를 제공(잔여 가동각 임계 기본 5° 이내 관절 강조, 리밋 도달 방향 버튼 비활성). 카테시안 조그에서 **IK 실패(`NoSolutionFound`/리밋 도달/특이점 근접) 원인 구분** + 즉시 홀드 전이 표시. | M | FR-MAN-013/025/026 | [확정] |

#### 3.8.2 S-10 학습 — 화면 고유 요구사항

> 도메인 로직(정책 레지스트리, 설정 스키마, 사전 검증 규칙, 계보 스키마)은 **`10-학습.md`(영역 `TRN`)가 소유한다.** 아래는 화면 창구다. 학습 잡은 참조 레포와 동일하게 **subprocess(`lerobot-train`)**로 실행한다(제어 루프와 무관, `connect()` 영향 없음).

| ID | 요구사항 | 우선 | 근거 (매핑) | 비고 |
|---|---|---|---|---|
| FR-GUI-120 | **S-10**은 **학습 잡 큐/실행 목록**을 표시(각 잡 `{ID, 이름, 정책, 데이터셋+revision, 요청 GPU 수, 상태, 시각, 출력 경로}`, 필터·정렬·취소). **GPU 부재로 `QUEUED` 대기**를 상태로 구분. | M | FR-TRN-027/028/032; 참조 레포 `training/train_process.py`(subprocess) | [확정] |
| FR-GUI-121 | **S-10**은 **정책 타입 선택기 + 하이퍼파라미터 폼**을 제공(정책 목록은 설치된 LeRobot 레지스트리에서 런타임 유도, 하드코딩 금지). LeRobot 기본값 프리필 + **CLI 플래그명 병기**, optimizer/scheduler 프리셋 자동 채움(하나 덮어쓰면 둘 다 요구), `vqbet`은 사용불가 표시·차단. | M | FR-TRN-001/002/004/007/008 | [확정] |
| FR-GUI-122 | **S-10**은 **데이터셋 선택과 통계**를 제공(태스크·변형별 에피소드 분포, 총 수 50 미만 경고, 변환 커버리지·손실 리포트). **다중 데이터셋(list) 지정 금지**, 병합 경로 안내. | M | FR-TRN-014/023/026/056 | [확정] |
| FR-GUI-123 | **S-10**은 **VRAM 사전검증을 학습 시작 전 표시**(정책+`batch_size`+동결 예상 VRAM vs 가용, 초과 시 시작 비활성 + 대안 제시). 예상값에 근거 출처 병기. | M | FR-TRN-018/015 | [확정] |
| FR-GUI-124 | **S-10**은 **진행률·손실 곡선·처리량 + 로그 스트리밍**을 실시간 표시해야 한다. 차트 키는 LeRobot `MetricsTracker`가 실제 내보내는 **`loss, grad_norm, lr, samples_per_s, update_s, dataloading_s, gpu_mem_gb`**로 한정(임의 키 발명 금지). 로그는 실시간 스트리밍 + 파일 영속(잡 종료 후 조회), **W&B 없이 동작하는 로컬 손실 곡선 뷰를 반드시 제공**(폐쇄망 — FR-GUI-008 정합). | M | FR-TRN-029/030/035/036 | [확정] |
| FR-GUI-125 | **S-10**은 **체크포인트 목록 + 중단/재개**를 제공(중단 시 마지막 체크포인트 보존·계보 기록, 재개는 `train_config.json`+`resume=true`로 optimizer·scheduler·step·데이터 순서 복원 명시). **val loss 최소 체크포인트를 기본 선택으로 삼지 말고** "오프라인 지표는 온라인 성공률을 예측하지 못한다" 경고 상시 표시. | M | FR-TRN-032/033/041/045 | [확정] |
| FR-GUI-126 | **S-10**은 학습 중 **GPU 사용률·VRAM·온도**를 표시(`MetricsTracker`는 `gpu_mem_gb`만 → NVML/`nvidia-smi` 별도 계측). 온도 임계 초과·`samples_per_s` 지속 하락(스로틀링) 시 경고. | M | FR-TRN-038/039 | [확정] |
| FR-GUI-127 | **S-10**은 **데이터셋 ↔ 체크포인트 계보를 양방향 조회**(체크포인트↔에피소드 집합), 불변 스냅샷(데이터셋 revision + `stats.json` 해시, `train_config.json` 전문, git SHA, 컨테이너 다이제스트)과 원본 id ↔ `episode_index` 매핑표를 열람할 수 있어야 한다. | M | FR-TRN-053/054/055 | [확정] |

### 3.9 비기능 요구사항

| ID | 요구사항 | 우선 | 근거 | 비고 |
|---|---|---|---|---|
| NFR-GUI-001 | 3D 뷰포트는 **60 fps**(프레임 예산 16.7 ms)를 목표로 하며(브라우저 Three.js 클라이언트 렌더), 30 fps 미만 3초 지속 시 자동 품질 저하(포인트클라우드 비활성 → 그림자 비활성 → 메시 LOD)를 적용하고 표시해야 한다. | M | Three.js WebGL 렌더 예산 | [확정] |
| NFR-GUI-003 | 관절 상태의 WS 발행율은 **기본 30 Hz, 상한 60 Hz**여야 한다. 제어 루프 풀레이트를 그대로 WS로 밀어서는 안 된다(렌더/대역폭 병목). | M | §2.4 | [확정] |
| NFR-GUI-004 | 관절 상태 지연(백엔드 샘플 시각 → 브라우저 3D 뷰포트 반영)의 **p95 상한**을 정의하고 상시 계측·표시해야 한다. **WS 홉(로컬호스트 또는 LAN)을 포함**하며 수치는 자체 벤치로 확정한다. | M | 인프로세스 제어 루프 폴 주기 + WS 홉 + 렌더 프레임이 지배 | [결정필요] |
| NFR-GUI-005 | 비상정지 명령의 **왕복 지연 상한**(브라우저 입력 → WS → 백엔드 `STOP_HOLD` 적용)을 정의하고 초과 시 경고해야 한다. **수치는 자체 벤치로 확정한다.** (텔레옵 지연 근거로 인용되던 arXiv 2603.06850은 CARLA 차량 차선유지 실험이라 도메인이 다르다 — 그 수치를 상한으로 쓰지 않는다.) | M | 도메인 불일치; WS 홉 포함 | [결정필요] |
| NFR-GUI-008 | 🔴 **제어 루프가 백엔드 프로세스 안에 있다.** ① 제어 루프와 **WS 서빙·카메라 JPEG 인코딩**을 **별도 스레드/워커로 분리**, ② WS 서빙/인코딩이 제어 루프를 블로킹해서는 안 되며, ③ 제어 루프 스레드는 **RT 승격(SCHED_FIFO) + `mlockall`** 대상, ④ **제어 루프 사이클 타임을 상시 계측**해 인코딩·직렬화 부하가 지터를 만드는지 감시해야 한다. | M | 🔴 GROUND §0 — LeRobot 인프로세스 임베드; **CLI 스폰 금지**(FR-GUI-083); LeRobot 루프 사이클 타임 [미측정] | **[결정필요] — §5 Q-14** |
| NFR-GUI-011 | 🔴 GUI는 **LeRobot 제어 루프(백엔드)의 사이클 타임(p50/p95/p99)** 을 상시 계측·표시하고, 목표 fps 대비 0.95배 미만이 N사이클 연속이면 WARN + 원인 구간(CAN / 카메라 grab·인코딩 / IK / WS 직렬화) 분해 표시해야 한다. | M | 🔴 한 프로세스에 CAN(16모터)+카메라 grab·JPEG 인코딩+IK(0.345 ms)+WS 서빙이 얹힌다. **[미측정]** — `09` NFR-SIM-007 · `12` FR-SAF-001b와 **같은 측정 하나**로 해결 | **[신규구현] — 세 문서 공통 최우선 측정** |
| NFR-GUI-010 | 메시 자산은 **브라우저·백엔드 양측에서 캐시**되어야 하며 씬 재구성 시 재파싱·재다운로드하지 않아야 한다. 백엔드는 `Cache-Control`/`ETag`로 정적 자산 재요청을 억제한다. | S | 웹 자산 로드 | [확정] |
| NFR-GUI-012 | WS 링크 대역폭 예산을 정의하고 상시 계측해야 한다: 카메라 스트림 합계(JPEG bytes/s) + 텔레메트리. 링크 포화 시 **카메라 품질/fps를 우선 낮추고 제어·텔레메트리를 보호**해야 한다. LAN vs 로컬호스트 클라이언트 여부를 표시한다. | S | 웹 스트리밍의 실재 비용(§2.1, FR-GUI-042) | **[신규구현] — 웹 대역폭 예산** |

> **FR 합계: 웹 전송 복원(카메라 스트리밍) + 다중클라이언트 최소 대응 반영 후 유효 FR 약 80개** (FR-GUI 번호는 도메인 문서 참조 호환을 위해 유지, 미채택 항목은 결번). / **NFR 유효: 8개**

---

## 4. 상태 · 오류 처리

### 4.1 CAN 소유권 — GUI가 노출하는 상태 전이

GUI가 표시하는 CAN 인터페이스(`can0`/`can1`)별 상태다. 정본 상태머신은 `01-시스템-아키텍처.md`(SYS)가 소유하며, 여기서는 **화면에 무엇이 보여야 하는가**만 규정한다. CAN은 항상 **백엔드 프로세스**가 소유하며 브라우저는 그 상태를 WS로 관찰만 한다.

| 상태 | GUI 표시 | 진입 조건 | 허용 동작 |
|---|---|---|---|
| `UNOWNED` | 회색 "미점유" | 락 미보유, 바인딩 소켓 0 | 모든 모드 시작 가능 |
| `ACQUIRING` | 진행 스피너 | 락 획득 시도 중 | 취소만 |
| `READONLY` | 청색 "torque-OFF 브링업" | `connect_readonly()` — 버스 열림, enable 안 함 | 손으로 방향/영점 검증, 명시적 set_zero |
| `OWNED` | 녹색 + **소유자·PID·`connect()` 시각** | `flock` 보유 + bind + Enable Torque | 해당 모드 제어. 다른 모드 시작 차단 |
| `RELEASING` | 진행 스피너 | rest 확인 → `close(fd)` → 락 해제(**세션 종료에서만**) | 취소 불가 |
| `INTRUDED` | 🔴 적색 "외부 침입" + 침입 PID | `flock`은 우리가 쥐었으나 바인딩 소켓 > 1 | **제어 UI 차단 + `STOP_HOLD` 유지.** 🔴 `disconnect()`로 도망가지 않는다(영점 파괴) |
| `CONFLICT` | 적색 + 소켓 수 | 프리플라이트에서 소켓 > 1 | **제어 UI 차단**, 진단 화면 강제 이동 |
| `FAULT` | 적색 + 링크 상태 | `BUS-OFF` 또는 에러 카운터 임계 초과 | CAN 재기동 |

**전이 규칙**
- `UNOWNED → ACQUIRING → READONLY → OWNED` : 브링업(torque-OFF 검증 → 명시적 enable).
- `OWNED → RELEASING → UNOWNED` : 🔴 **세션 종료에서만.** 모드 전환에서는 절대 일어나지 않는다(FR-GUI-081). 해제 전 rest 자세 확인 선행.
- `OWNED → INTRUDED` / `* → CONFLICT` : 바인딩 소켓 > 1 검출. **커널이 알려주지 않으므로 능동 검사로만 발견된다.**

### 4.2 GUI 실시간 패널 상태 (브라우저↔백엔드 WS)

| 상태 | 표시 | 제어 UI | 3D 뷰포트 |
|---|---|---|---|
| `LIVE` | 정상 | 활성(제어권 보유 시) | 실시간 |
| `DEGRADED` | 사이클 타임/드롭/대역폭 경고 | 활성 + 경고 | 실시간 + age 배지 |
| `STALE` | 상태 age 임계 초과 | **차단** | 로봇 모델 회색화 + age 표시 |
| `WS_DOWN` | 주황 배너 "서버 연결 끊김" | **차단** | 마지막 자세 고정 + WS 재접속 시도 표시 |
| `WORKER_DOWN` | 적색 배너 | **차단** | 마지막 자세 고정 + "제어 루프 정지" 오버레이 |

> **원칙**: GUI는 백엔드 제어 루프가 멈췄거나 WS가 끊긴 동안 **마지막 상태를 실시간인 것처럼 계속 렌더링해서는 안 된다.** 신선하지 않으면 시각적으로 명백히 달라야 한다. 🔴 `WS_DOWN`은 **브라우저 WS 재접속만** 시도하고 백엔드 `Robot`을 건드리지 않는다. `WORKER_DOWN` 복구를 **`Robot` 재연결로 하지 않는다**(영점 파괴) — 제어 루프 상태·CAN 링크·`get_observation()` 예외를 먼저 진단한다.

### 4.3 오류 조건 · 감지 · 복구

| 오류 | 감지 | GUI 동작 | 복구 |
|---|---|---|---|
| CAN 이중 bind(조용한 실패) | `/proc/net/can/raw` ifindex별 소켓 > 1 | `CONFLICT` 배지, 제어 UI 차단, 침입 PID | 침입 프로세스 종료 후 재검사 |
| 상태 스트림 stale | 샘플 age > 임계 | 3D 회색화, 제어 차단, ERROR 알림 | 🔴 **`Robot` 재연결로 복구하지 않는다**(영점 파괴). 제어 루프·CAN 링크·`get_observation()` 예외 진단 |
| WS 링크 끊김 | WS 하트비트 타임아웃 | `WS_DOWN` 배너, 제어 차단 | 브라우저 WS 재접속(백엔드 `Robot` 불변) |
| 카메라 프레임 드롭 | 인코더/WS 큐 백프레셔 + FPS < 0.95×목표 | WARN 배지, 에피소드 플래그, 드롭 수(캡처/WS 구분) | 해상도/fps/JPEG 품질 하향, HW 인코더 |
| 제어 루프 하트비트 소실 | 백엔드 제어 루프 하트비트 타임아웃 | **즉시 소프트 스톱(`STOP_HOLD`)**, 감사 로그 | 제어 루프 진단 후 재기동(재연결 아님) |
| WS 대역폭 포화 | 송신 버퍼/전송률 임계 | 카메라 품질·fps 우선 하향, 제어·텔레메트리 보호 | LAN 품질 개선 / 로컬호스트 접속 |
| 프로파일 미로드 | 활성 프로파일 없음 | 제어 시작 차단 | 프로파일 선택 |
| 디스크 여유 부족 | 잔여 < 1시간 분량 | 녹화 시작 차단 | 아카이브/삭제 |
| `use_velocity_and_torque=false` | 기동 시 config 검사 | 충돌 감지·트윈·바이래터럴 비활성 + 경고 배지 | 단일 스위치로 True |
| CAN-FD 미설정 | `ip -details link show` | 기동 거부 | `ip link`로 CAN-FD 설정 |

---

## 5. 미해결 · 결정필요

| # | 질문 | 무엇을 확인/측정해야 하는가 | 태그 |
|---|---|---|---|
| Q-1 | **SPA 프레임워크(React/Vue/Svelte)를 무엇으로 할 것인가?** 3D는 Three.js + `urdf-loader`로 확정(§2.1.1)이나 프레임워크는 미확정. | 상태관리·라우팅·번들러·개발자 친숙도로 구현 단계에서 선택. **아키텍처 결정(단일 WS·REST·백엔드 소유)은 프레임워크와 무관하게 성립**하므로 이 미결이 나머지를 막지 않는다. | **[결정필요] — 프레임워크만** |
| Q-2 | **관절 클램프의 정본은?** → **v2 URDF `joint_limits.yaml`(rad)이 기계 상한 정본**(j2=−10/+190°), driver `openarm_cell.yaml`이 운영 상한, LeRobot deg는 v1-era 소프트 클램프. | GUI는 활성 리밋 세트를 항상 표시하고 URDF 정본으로 클램프한다. 좌/우 비대칭(j1/j2/finger)과 `side` 미지정 ±5° 잠금을 반영. | **[확정 방향]** |
| Q-3 | **활성 게인 프로파일의 정본은?** → **명명 3-프로파일**: compliant(70, 공통) / stiff(230, v2, 트윈·드라이런·평가·VR) / replay(추종 우선). "70=v2 판별자"는 오류(70 공통, v2 고유는 230). | GUI는 "무엇이 활성인지 항상 표시"(FR-GUI-068). 트윈·드라이런은 stiff 강제(`09` FR-SIM-028b). | **[확정 방향]** |
| Q-4 | **3D 뷰포트 관절 상태 지연 상한(p95)?** (NFR-GUI-004) | 자체 벤치: 백엔드 샘플 타임스탬프 → WS 홉 → 브라우저 렌더 프레임까지 p50/p95/p99. 30 Hz 발행 시 이론 하한 ≈ 폴 33 ms + WS 홉 + 렌더 16.7 ms. LAN vs 로컬호스트를 구분해 잰다. | [결정필요] |
| Q-5 | **비상정지 왕복 지연 상한?** (NFR-GUI-005) | arXiv 2603.06850(≤150 ms)은 CARLA 차량 차선유지라 도메인이 다르다. 양팔 매니퓰레이션 기준 + WS 홉 포함 자체 벤치 필요. | [결정필요] |
| Q-6 | **`openarm_description` v2.0 xacro 인자 이름과 bimanual 프리셋 존재 여부** [미확인]. | xacro 원문을 열어 인자(`arm_type`, `bimanual`, `side`, `prefix` 등)를 확정해야 백엔드 URDF 전개(FR-GUI-010)와 `package://` 리라이트(FR-GUI-011) 파라미터를 정의할 수 있다. | [미확인] |
| Q-7 | ~~**GUI 정본 모드가 `dataflow-vr.yaml`인가 `dataflow_bridge_ros2_vr.yaml`인가?**~~ → 🔴 **[확정·종결] 둘 다 아니다.** LeRobot Python API를 백엔드에 인프로세스 임베드한다. dora도 ROS 2도 쓰지 않는다. 3D 상태 소스는 항상 `Robot.get_observation()` 하나. 새 제약: `connect()` 1회(FR-GUI-081), 제어 루프가 백엔드 프로세스 안(Q-14). | 질문 소멸. | **[확정·종결]** |
| Q-8 | **공식 문서가 광범위하게 stale하다.** OpenArm VR 페이지("Isaac Lab 프로토타입/~20 FPS/coming soon")·LeRobot `openarm.mdx`(record 예제가 `--repo-id`인데 실제는 `--dataset.repo_id`, `use_velocity_and_torque` 미문서화, train/rollout/eval 0개) 모두 낡았다. **v2 실기 VR은 `tutorial/data-collection-vr.mdx`·`dora-openarm-vr`에 동작한다** — vr.mdx는 v1이 v2 트리에 복붙된 죽은 페이지다. | **원칙: 문서가 아니라 소스를 인용한다.** GUI가 생성·표시하는 모든 CLI 문자열·설정 키는 LeRobot 소스의 draccus 필드명에서 유도. 공식 문서를 근거로 만든 UI는 첫 실행에서 죽는다. | **[확정 — 원칙]** |
| Q-9 | **그리퍼 파지력의 단위·상한.** `gripper_posforce_limits: [50.0, 1.0]`은 실재하나 API는 per-unit(`torque_pu∈[0,1]`), 드라이버는 `/4.5`(driver.py:206-210, `# TODO: … convert Nm to pu?`), 실전달 0.222 pu. 50 rad/s는 DM4310 vMax=30 rad/s 초과. | GUI 그리퍼 슬라이더의 단위·범위를 정할 수 없다. 실측 캘리브레이션(파지력계 pu↔N) 선행. 그때까지 **per-unit(0–1)으로만 표시**, Nm 환산 금지. 그리퍼는 **엔드포인트 rad 캡처**로 open/close 정규화(참조 레포 패턴). | [결정필요] |
| Q-10 | ~~**데스크톱 셸(Electron/Tauri)이 필요한가?**~~ → 🔴 **[확정·종결] 웹 SPA(브라우저).** 데스크톱 셸을 쓰지 않는다. 배포는 백엔드가 정적 자산을 서빙하고 사용자는 브라우저로 접속한다(에어갭·CSP·자체 호스팅 — FR-GUI-008). | 질문 소멸. | **[확정·종결]** |
| Q-11 | ~~**WebRTC `getStats()`로 glass-to-glass 지연을 얻는가?**~~ → 🔴 **[확정·종결]** WebRTC를 쓰지 않는다(단일 WS). 카메라 지연은 **백엔드 grab 타임스탬프 → WS 수신 시각**으로 직접 계측한다(FR-GUI-048). | 질문 소멸. | **[확정·종결]** |
| Q-12 | **포인트클라우드 전송 규격** — 정본 카메라 구성의 뎁스 유무는 `06`이 소유한다. 뎁스 소스가 있는 구성에서만 FR-GUI-031이 살아나며, 그때 WS 전송 규격(다운샘플/LOD)과 렌더 예산 내 최대 포인트 수를 실측한다. | `06`의 뎁스 결정에 종속. 뎁스는 16-bit PNG/컬러맵으로 WS 전송(FR-GUI-041), 포인트클라우드 변환은 브라우저 또는 백엔드 중 실측으로 결정. | [선택] |
| Q-13 | ~~**Foxglove/Rerun을 디버깅·리플레이 도구로 병행 임베드할 것인가?**~~ → 🔴 **[확정·종결]** 3D·시계열·리플레이·카메라 타일은 자체 Three.js/차트 컴포넌트로 구현한다. 외부 뷰어 병행 임베드는 결합도·CSP 부담이라 하지 않는다. | 질문 소멸. | **[확정·종결]** |
| Q-14 | 🔴 **제어 루프가 백엔드 프로세스 안에 있다. 카메라 인코딩·WS 서빙이 제어 루프를 방해하는가?** (NFR-GUI-008 / NFR-GUI-011) LeRobot `record_loop()`가 백엔드 제어 루프에서 돌고, 같은 프로세스가 카메라를 JPEG 인코딩해 WS로 밀며 텔레메트리를 직렬화한다. **LeRobot 루프 사이클 타임 [미측정].** | **측정하라.** ① 카메라 스트림 개수·해상도·JPEG 품질별로 제어 루프 사이클 타임 p50/p95/p99 비교, ② 인코딩·WS 서빙을 별 워커/스레드로 격리한 효과 분리, ③ 클라이언트 접속 수(다중 브라우저)에 따른 부하. 대안이 없으면 카메라 인코딩·WS 서빙을 **별 프로세스로 빼고 상태를 IPC(공유메모리)로 넘기되 `connect()` 1회 원칙(F-3′)은 유지** — 제어 프로세스가 `Robot`을 독점. 🔴 **`09` Q13 · `12` Q17과 동일한 실험 하나. 먼저 재라.** | **[결정필요] — 백엔드 아키텍처 최대 미결** |
| Q-15 | **Quest 3S VR 동작 검증.** v2 실기 VR은 Quest 3(APK/UDP 5006, WebXR/HTTPS 8443)로 동작하나 **Quest 3S는 공식 어디에도 없다**(APK는 Quest 3 대상 빌드). | S-05 VR 진입점은 Quest 3S에서 자체 검증 필요(m22). APK 미동작 시 WebXR(8443) 경로로 폴백. | [미확인] — 자체 검증 |

**닫힌 결정**

- **닫힘: GUI = 웹 SPA + FastAPI 헤드리스 백엔드, 브라우저↔백엔드 = 단일 WebSocket + REST, 3D = Three.js + `urdf-loader`, gRPC = 원격 추론 전용(8080).** (근거: DECISIONS-v3 웹 단일 결정 / 참조 레포는 **백엔드 로직 템플릿**으로만 사용) → PyQt6/pyqtgraph 데스크톱 확정을 **폐기**하고 웹 전송(단일 WS·카메라 스트리밍)을 **복원**. Q-7 종결 유지, Q-10/Q-11/Q-13은 웹 근거로 종결, Q-1은 **프레임워크만** 미결로 유지.

---

## 6. 출처

**🔴 참조 레포 — 백엔드 로직 템플릿 (실측 구조, UI는 재사용 안 함)**
- `bh_indy7_LeRobot/src/bh_indy7_lerobot_gui/workers/hw_worker.py:169-239`(LiveLinkMode/상태전이), `:407-435`(enqueue/update_configs), `:588-807`(connect/observer/disconnect) — **`Robot` 소유·`connect()` 1회·상태머신 패턴을 백엔드로 이식**(Qt 시그널 전달만 WS로 대체)
- `.../app.py:26-96` — AppMode(CLIENT/LOCAL/SERVER) 개념(백엔드 기동 인자로 이식)
- `.../inference/policy_server.py`, `.../_transport/services.proto:42-54` — **gRPC = 원격 추론 전용(8080)**
- `.../inference/policy_service.py` — LOCAL(인프로세스 루프백) / ASYNC(원격) 추론
- `.../src/bh_indy7_lerobot/runtime_config.py:71-297` — 설정 pydantic + atomic + blast-radius 격리(백엔드 서버측)
- `.../src/bh_indy7_lerobot/calibration/atomic_io.py:29-94` — 캘리브레이션 영속(`save_calibration_atomic`)
- `.../src/lerobot_robot_indy7_rig/__init__.py:22-30` — umbrella dist 접두사 자동로드
- `.../src/lerobot_plugin_rebot/rebot.py:247-266` — `connect()`(auto set_zero 오버라이드) / `connect_readonly()`(torque-OFF), `capture_gripper_endpoint`(엔드포인트 rad 캡처)
- ⚠️ `.../pyproject.toml`(PyQt6/pyqtgraph/PyOpenGL) — **UI 스택으로 채택하지 않는다**(웹 SPA로 대체). 백엔드 로직만 이식.

**🔴 LeRobot — 정본 런타임 (v0.6.1 스냅샷 직접 열람). §2.2의 F-3′ ~ F-7′ 근거**
- 🔴 `src/lerobot/robots/openarm_follower/openarm_follower.py:152-153` — `connect()` → `if self.is_calibrated: self.bus.set_zero_position()` → **영점 파괴** (F-3′, FR-GUI-081/084)
- 🔴 `config_openarm_follower.py:71` — `use_velocity_and_torque: bool = **False**` (F-4′, FR-GUI-072); `:107-120` — `joint_limits`, **`side` 미지정 전 축 ±5°** (F-6′, FR-GUI-112); `max_relative_target` **기본 `None`**
- 🔴 `src/lerobot/configs/dataset.py` — **`push_to_hub: bool = True`** (F-5′, FR-GUI-073); `stamp_repo_id()`(`:75-83`)가 `_%Y%m%d_%H%M%S` 부착 (FR-GUI-074)
- 🔴 `src/lerobot/scripts/lerobot_record.py:534-538`(`finally`의 `push_to_hub`), `:228-248`(`record_loop(events)`), `:469-516`(루프)
- `src/lerobot/utils/keyboard_input.py:153-170` — `events = {"exit_early","rerecord_episode","stop_recording"}`, pynput/TTY 폴백 환경 의존
- `src/lerobot/utils/feature_utils.py:68-89` — 토크가 `observation.state`로 평탄화(양완 48). `observation.effort` 없음. `:131-132` KeyError 위험
- `src/lerobot/utils/constants.py:80-87` — `DEFAULT_FEATURES`에 **`success` 없음** → 사이드카
- `src/lerobot/robots/bi_openarm_follower/bi_openarm_follower.py:99-112` — 팔별 카메라 키 `left_`/`right_` 자동 부착 → UI 라벨 ≠ 데이터셋 키
- `src/lerobot/configs/eval.py:29-31` — `env` 필수 → 🔴 **`lerobot-eval`은 시뮬 gym 전용** (FR-GUI-105); `lerobot_rollout.py:85`(실기 rollout)
- `src/lerobot/motors/damiao/damiao.py:568` — 단위 `.pos`=deg/`.vel`=deg/s/`.torque`=Nm; `:492-502` `_mit_control_batch`가 tau를 받는다(`12` FR-SAF-069)
- ⚠️ **stale 문서**: https://huggingface.co/docs/lerobot/openarm — `--repo-id`(실제 `--dataset.*`), `use_velocity_and_torque` 미문서화, train/rollout/eval 0개 → §5 Q-8

**🔴 openarm_control — IK / FK (3D 뷰포트 EE 포즈 소스, 백엔드)**
- `kinematics.py fk_bimanual(right, left)` → `float32[7] × 2`(MJCF 월드, rad), 실측 0.037 ms → FR-GUI-025
- `kinematics.py:107` — `solve(self)`(인자 없음); `config.py:23-26` — `openarm_mujoco.v2` 하드코딩 → IK가 푸는 모델 = v2 MJCF(`09` §1.1)

**웹 3D — Three.js + urdf-loader (프런트엔드)**
- `urdf-loader`(브라우저 URDF 로드, `robot.setJointValue(name, rad)`, `package://` 리라이트) — FR-GUI-003/010/011/020
- Three.js `WebGLRenderer`/`OrbitControls`(orbit/pan/zoom, 60 fps 목표) — §2.5, NFR-GUI-001

**OpenArm v2 자산 · VR (1차)**
- `openarm_description` v2.0(프리셋 xacro, 관절 이름, `joint_limits.yaml` rad 정본): https://github.com/enactic/openarm_description
- `openarm_driver/configs/openarm_cell.yaml`(운영 리밋·게인·`gripper_posforce_limits`) / `openarm_cell_higher_pd.yaml`(stiff 230): https://github.com/enactic/openarm_driver
- `pinch_gripper/config/joint/joint_limits.yaml`·`joint_mimics.yaml`(pinch −45°–0°, 2지 mimic): openarm_description v2.0
- `dora-openarm-vr`(Meta **Quest 3**, APK/UDP 5006, `OneEuroPoseSmoother`) / `dora-openarm-webxr`(WebXR HTTPS 8443, PICO4/Quest3): https://github.com/enactic/dora-openarm-vr · https://github.com/enactic/dora-openarm-webxr
- v2 실기 VR 튜토리얼(정본): `openarm` `website/docs/tutorial/data-collection-vr.mdx`. ⚠️ **stale**: `website/docs/teleop/vr.mdx`(v1이 v2 트리에 복붙된 죽은 페이지 — "coming soon"은 v1 잔재)
- `openarm_can/src/openarm/canbus/can_socket.cpp`(`bind()` 비배타) / `dm_motor_control.cpp`(`parse_motor_state_data`: `data[6]=T_MOS`, `data[7]=T_Rotor`)

**상류 UI 선례 (기능 목록의 참고 — 런타임/스택으로 쓰지 않는다)**
- `dora-openarm-evaluation-ui`(에피소드 루프 start→success/fail/cancel→reset, 태스크 스위처, 성공률, Resume, 단축키+E-stop, 스트림 FPS/지터): https://github.com/enactic/dora-openarm-evaluation-ui
- `dora-openarm-data-collection-ui/src/.../main.py`(`jitter_ms`, 윈도 60/120, `VR_STALE_AFTER_S=1.0` — 통계 리셋용이지 안전 워치독 아님)
- ⚠️ **상류 dora dataflow**(`dataflow-vr.yaml` 등) — 🔴 **런타임으로 쓰지 않는다.** 카메라 배치·One-Euro 상수·정렬 상태머신 개념의 교차확인 참고로만 인용

**커널**
- https://docs.kernel.org/networking/can.html (SocketCAN: 다중 bind 허용, 로컬 루프백 기본 ON)
