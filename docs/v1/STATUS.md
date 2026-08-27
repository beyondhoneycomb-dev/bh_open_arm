# STATUS — 지금 무엇이 도는가

작성 2026-08-24 · 갱신 2026-08-27(§3.2·§3.5) · 기준 커밋 `31c59f8` + 미커밋 작업트리

---

## 0. 이 문서가 무엇인가

`docs/v1/` 아래 네 묶음은 서로 다른 질문에 답한다.

| 묶음 | 답하는 질문 |
|---|---|
| `spec/` 18문서 (19,302줄) | 시스템이 **무엇을 할 수 있어야 하는가** |
| `plan/` 10문서 | **어떤 순서로** 지을 것인가 (177 WP · 게이트 15 · 계약 13) |
| `work_log/` 43편 (6,676줄) | **각 회차에 무엇을 했는가** |
| **이 문서** | **지금 무엇이 도는가** |

🔴 **명세와 계획은 고치지 않는다.** 그것은 "하려던 것"의 기록이고 그대로 값이 있다. 이 문서가 **"된 것"의 정본**이며, 둘이 어긋나면 여기가 이긴다.

🔴 **"지어졌다"와 "돈다"는 다르다.** 이 저장소는 파일이 존재하고 테스트가 초록인데 **아무 실행 경로에도 안 걸린** 코드가 많다. 그 구분을 안 하면 다음 사람이 없는 기능을 있다고 읽는다 — 실제로 그런 오독이 이미 여러 번 있었다.

---

## 1. 한눈에

```
1급 파이썬 모듈 1,080개 · 164,544줄
  진입점에서 도달   249개 ·  47,441줄  (29%)
  도달 안 됨        831개 · 117,103줄  (71%)
```

**도달 안 되는 71% 는 버리는 코드가 아니다.** 사용자 확정(2026-08-24): 전부 남긴다 — 곧 다 지을 것이므로. 이 문서는 그것을 **지우기 위해서가 아니라 헷갈리지 않기 위해** 표시한다.

프런트엔드는 13화면이 전부 렌더되지만 **값은 전량 픽스처**다. 실시간 데이터를 구독하는 화면은 0개다.

---

## 2. 측정 방법 (재현 가능)

진입점에서 `import` 를 이행적으로 따라가 도달 집합을 구한다. 재현:

```python
# 저장소 루트에서. tests/ 와 */_tests/ 는 제외.
# 진입점 = pyproject [project.scripts] 3개 + scripts/*.py 5개
#   backend.config.serve  backend.camera.cli  registry.env.cli
#   scripts.torque_session scripts.jog_joint scripts.can_node_watch
#   scripts.canbind_session scripts.rig_session
```

🔴 **§1 의 도달 29% / 미도달 71% 는 2026-08-24 측정치다.** 2026-08-26 에 조율 기계 14,272줄이
삭제되면서 분모가 줄었고(258,728 → 244,456), 삭제분은 **거의 전부 도달하던 코드**였다 — 즉 도달
비율은 실제로 **내려갔다**. 다시 재기 전까지 §1 숫자를 인용하지 말 것.

한계 둘, 그대로 적는다: ① 동적 import·plugin 등록은 못 본다 ② 도달 못 해도 **곧 이을 코드**일 수 있다 — §5 가 그 목록이다.

---

## 3. 지금 돌릴 수 있는 것 — 진입점 전수

### 3.1 로봇을 만지는 것

| 명령 | 무엇 | 실기 검증 |
|---|---|---|
| `scripts/torque_session.sh` | 가드된 토크-ON/OFF 세션. 5단계 admission(전부 fail-closed) | ✅ 2026-08-04 왼팔 can0 24V, 유지 틱 6,877회 |
| `scripts/jog_joint.sh` | 관절 하나를 램프로 움직이고 되돌린다. 리밋을 읽는다 | ✅ 2026-08-11 양팔 14관절 |
| `scripts/can_node_watch.sh` | **통전 없이** 노드 감시 — `0xFD` 만 보낸다 | ✅ 2026-08-06 |
| `scripts/canbind_session.sh` | 어느 팔이 어느 CAN 채널인가 판정 | ✅ 2026-08-05 |
| `scripts/rig_session.py` | 토크 브링업용 버스 조립 | 위 세션들의 부속 |
| `oa-camcap` | 카메라 캡처 — `PG-CAM-001` 재현 | ✅ 2026-08-17 3대 10분 연속 |

### 3.2 GUI

| 명령 | 무엇 | 한계 |
|---|---|---|
| `oa-serve` | FastAPI + SPA + WebSocket 1개 | `--arm` 은 `none`·`dummy`·**`real`**. `real` 은 **읽기 전용** — 보드에 실기 값이 오르고, 명령은 여전히 안 나간다(§6) |
| — REST | `GET /api/tools` · `GET /api/config` · `PUT /api/config/{서브객체}` | 서브객체 4개(`layout`·`presets`·`endEffector`·`control`) |
| — WS `/ws/realtime` | 리스 갱신·재무장 핸드셰이크·`stop_hold` 수용 · 거절은 닫힘 코드 4400–4408 로 답한다(§8.1) | **서버가 먼저 보내는 프레임 0종.** §6 참조 |
| — SPA | 13화면 + `/viewport` | **S-06 장치 지정 패널만 실기에 붙었다**(프리뷰·지정·저장). 나머지 12화면은 값 전량 픽스처, 실시간 구독 0 |
| — REST 카메라 | `GET /api/cameras/devices` · `PUT`·`DELETE /api/cameras/slots/{슬롯}` · `GET .../{포트}/preview` | **S-06 이 실제로 부른다.** 프런트에서 백엔드로 가는 첫 `fetch` |

### 3.3 저장소 도구

`oa-env` · `./scripts/gates.sh` — 검사 **13종**(파이썬 레인 9 + 프런트 `tsc`·`eslint`·`vitest`·`vite build`), 약 100초.

`oa-check`·`oa-registry`·`oa-index`·`oa-contracts`·`oa-state` 는 2026-08-26 에 삭제됐다(§6b). 남은 진입점은 `oa-serve`·`oa-camcap`·`oa-env` 셋이다.

---

### 3.4 `--arm real` — 2026-08-26 신설, 아직 안 켜봤다

`oa-serve --arm real` 이 하는 일, 순서대로 (`backend/config/arm.py`):

1. `~/.config/openarm/can_binding.json` 을 읽고 지금 있는 채널에 맞춘다 (`resolve_arm_channels`).
   못 맞추면 **거절하고** `canbind_session.sh` 를 지목한다 — 두 팔은 같은 CAN id 로 답하므로
   "첫 번째 인터페이스" 폴백은 팔이 움직이기 전까지 정답과 구분되지 않는다.
2. 양쪽 인터페이스 락을 쥔다 (`LockManager.acquire_all`, `01` FR-SYS-005). 남이 쥐고 있으면 거절.
3. `BiOaOpenArmFollower` 를 채널별 `port` 로 짓고 `connect_readonly(lock_manager)`.
4. `ArmSession` 에 `RealSideReader` 둘. 각 호출이 `OaOpenArmFollower.read_frame()` — 한 번의
   `sync_read_all_states` 로 pose·torque·`GuardSample` 이 같이 나온다.

🔴 **뜨는 순간 모터 14개가 통전된다.** `DamiaoMotorsBus.connect()` 의 핸드셰이크가
`CAN_CMD_ENABLE`(0xFC)를 보내고 응답을 요구한다(`openarm_follower_oa.py:471-475`). kp·kd·tau 가
0 이라 잡는 힘은 없지만 **한 프레임이면 움직인다.** 브레이크가 없다 — 사람이 받쳐야 한다.
시동 시 stderr 로 그 문장을 낸다.

**읽기만 한다.** `ArmSession` 에는 송신 경로가 없고 `STOP_HOLD_SENDER` 는 여전히 null 이다
(§6). 종료 시 `ArmBackend.close()` 가 틱을 세운 **뒤에** 토크를 끄고 버스를 닫고 락을 푼다.

**아직 두 번째 writer 는 없다.** `ArmSessionRunner` 스레드가 버스를 만지는 유일한 쪽이므로
버스 뮤텍스를 안 지었다(`CLAUDE.md` §4b). **정지 루프가 붙는 회차에 이게 바뀐다** — 그때
명령은 이 루프를 통해서 가야 한다.

---

### 3.5 카메라 슬롯 지정 — 2026-08-27, GUI 에 붙었다

**`S-06` 장치 지정 패널이 이 저장소에서 백엔드에 닿는 첫 화면이다.** 그전까지 프런트에 `fetch`
는 0건이었다.

어느 카메라가 어느 슬롯인가는 소스가 모른다. 손목 두 대가 시리얼 `Arducam_202500915_0001` 을
같이 쓰므로 스캔이 읽는 어느 필드로도 안 갈린다 — 사람이 **그림을 보고** 정한다.

| | |
|---|---|
| 화면 | `S-06` `DeviceAssignmentPanel` — 포트별 프리뷰 + card·포트·노드 + 슬롯 선택 + 해제 |
| 프리뷰 | `GET /api/cameras/devices/{포트}/preview` — JPEG **한 장**, 500 ms 마다 다시 요청 |
| 지정·저장 | `PUT`/`DELETE /api/cameras/slots/{슬롯}` → `~/.config/openarm/camera_binding.json` 원자적 기록 |
| 실행 시 해소 | `oa-camcap` 이 매번 그 파일을 지금 붙은 노드에 맞춘다(`backend/camera/rig.py`) |

**프리뷰가 스트림이 아니라 스틸인 이유:** 슬롯의 진짜 스트림은 캡처 런과 실시간 채널의 것이다.
같은 노드에 두 번째 리더를 열면 런이 세고 있는 프레임을 가져가고, 런은 그걸 카메라가 드롭하기
시작한 것과 구분하지 못한다. 한 장씩 열고 닫으면 캡처에 끼어들 수가 없고, 이미 잡혀 있으면
`503` 으로 "캡처가 쥐고 있다"고 답한다.

**갈릴 수 있는 두 슬롯 목록.** 패널이 offer 하는 슬롯은 백엔드가 답한 `RIG_SLOTS` 이고, 타일은
`observationFeatures` 에서 파생된다(`CG-G-S06a`). 둘이 어긋나면 패널이 제안한 슬롯을 `PUT` 이
404 로 거절한다 — 조용히 맞추지 않는다.

---

## 4. 실기로 증명된 것

| 날짜 | 무엇 | 증거 |
|---|---|---|
| 2026-07-29 | 영점 확립 절차 (`02` FR-CON-063 순서) | 잔차 검증 + 원자적 영속 |
| 2026-08-04 | **토크 ON 성립** — 왼팔 can0 24V, `0x01`–`0x07` | `engage.json`, 00:53:57 |
| 2026-08-05 | CAN 채널 ↔ 좌우 판정 | `canbind_session` |
| 2026-08-06 | 무통전 노드 감시 | `0xFD` 전용 경로 |
| 2026-08-11 | **양팔 14관절 조그** | 커밋 `6da2823`·`d21081b` |
| 2026-08-11 | 제어 주기를 커널 타이머가 쥔다 | 369 Hz 달성, 100 Hz 채택 |
| 2026-08-11 | Q-10 영점 프레임 닫힘 | 잔차 0.0109° |
| 2026-08-17 | **`PG-CAM-001` 실측** 3대 10분 | `~/openarm_captures/pgcam001_20260817/` |

`PG-CAM-001` 숫자: 링크 포맷 YUYV 확정(**MJPEG 은 커널 목록에 없다**) · 대역폭 3096.6 / 3200 Mbps · 동기 q99 wrist 3.993 / ZED 16.669·16.689 ms · 드롭 1.37~1.56%.

🔴 **판정은 레지스트리에 등록되지 않았다.** `PG-*` 게이트 15종 중 봉인된 것 0건. 이유는 §6.

---

## 5. 지었지만 아직 안 이어진 것

**전부 남긴다**(사용자 확정 2026-08-24). 각 상자는 명세대로 지어졌고 자기 테스트를 통과한다. 없는 것은 **들어가는 전선과 나가는 전선**이다.

### 5.1 사슬 — 명세가 정한 본 목적

```
텔레오퍼레이션 → 데이터 수집 → 데이터셋 → 학습 → 추론 → 평가
```

| 고리 | 트리 | 줄수 | 상태 |
|---|---|---|---|
| 텔레오퍼레이션 | `backend/teleop/` | 5,889 | 진입점 없음 |
| 데이터 수집 | `backend/recorder/` `capture_interlock/` `crash_recovery/` | 5,611 | 진입점 없음 |
| 데이터셋 | `backend/dataset/` (edit·import_export·integrity·lineage·merge·stats·viewer) | 8,678 | 진입점 없음 |
| 학습 | `backend/training/` `learning/` | 7,471 | 진입점 없음 |
| 추론 | `backend/inference/` `policy_matrix/` `compat/` | 8,639 | 진입점 없음 |
| 평가 | `backend/eval/` (autojudge·protocol·selection·stats·taxonomy) | 4,674 | 진입점 없음 |

### 5.2 사슬 밖

| 무엇 | 트리 | 줄수 | 비고 |
|---|---|---|---|
| **카메라 두 번째 스택** | `backend/sensing/` | 7,772 | 🔴 `backend/camera/`(2,806줄, `oa-camcap` 이 씀)와 **중복**. 둘은 주석으로만 서로를 안다 — `sensing/bandwidth/spec.py:7` 이 산식 정본을 `camera` 라 적는다 |
| 수동 동작 | `cartesian_jog` `freedrive` `freedrive_walls` `teaching` `replay` `home` `moveto` `mirror` | 8,318 | S-04 화면은 있고 백엔드 연결이 없다 |
| 충돌·안전 감지 | `gmo` `threshold_calib` `reaction` `collision_preflight` `detection_gate` `event_ring` | 약 7,400 | S-12 화면 동일 |
| 물리 모델 | `gravity` `gravity_verify` `friction` `friction_log` `payload` `excitation` | 6,579 | 마찰 동정 등. `PG-FRIC-001` 미실행 |
| 시뮬레이션 | `sim/dryrun` `sim/harness` `sim/fkik` `sim/walls` `sim/mjcf` `sim/mujoco` | 약 7,200 | MuJoCo 1단계. `sim/ik` 는 161줄만 도달 |
| 벤치·부하 | `rtbench` `loadtest` `stopbench` `reaction_bench` | 약 5,500 | 🔴 `loadtest/constants.py:30-31` 이 WS 발행율 정본(30/60 Hz)을 쥐고 있는데 `backend/ws/` 에는 0건 |
| 운영 | `ops/acl` `ops/systemd` `ops/telemetry` `ops/versionpin` `ops/hubguard` | 약 5,400 | `ops/hw` 는 1,026줄 도달(canbind 가 씀) |
| 계약 픽스처 | `contracts/fixtures` `contracts/capture` `contracts/recorder` `contracts/camera_registry` | 약 3,600 | 소비자 착지 대기 |

### 5.3 프런트엔드 — 만들어졌고 호출자가 0인 것

| 컴포넌트 | 왜 안 붙었나 |
|---|---|
| `mode/ModeBadge` | `global/StatusBadgeBar.tsx:67-71` 이 이미 모드 배지를 그린다 (중복) |
| `mode/HandoffProgress` · `ForceTakeoverDialog` | 데이터원 없음. `CTR-WS@v2` 프레임 10종에 handoff·takeover 가 없다. `ForceTakeoverDialog` 는 `role="admin"` 을 요구하는데 `leaseView.ts:49-51` 은 `operator`/`observer` 만 낸다 |
| `global/NotificationCenter`(패널) | 🔴 **원천은 이미 도착한다** — §8 참조 |
| `global/PreflightBanner` | 생산자 없음 (`global/preflight.ts` 는 순수 모델) |
| `global/shortcuts.ts` | 레지스트리만 있고 **어떤 키에도 안 묶여 있다** (`keydown` 리스너 전 트리 0건) |

붙은 것: `ControlLeaseView`(리스 표면, 2026-08-18) · `ModeAuthorityTable`(모드 권한표, 2026-08-24) · `NotificationBadge`(배지만, 빈 배열 고정).

---

## 6. 아예 없는 것

| 무엇 | 막힌 이유 |
|---|---|
| **텔레메트리 흐름** | `ArmStateBoard` 가 100 Hz 로 쓰는데 `board.view()` 프로덕션 소비자 0. `CTR-WS@v2` 의 `telemetry` 프레임은 **필드가 0개**다. 잠금은 사라졌으므로 막는 것은 이제 기계가 아니라 **형상 결정** — 프런트에 이미 갈라진 형상 둘 중 무엇을 정본으로 하느냐다(§6 아래) |
| **정지 명령 루프** | `STOP_HOLD_SENDER = null` (`frontend/src/app/backendLink.ts`). `ArmSession` 은 읽고 게시할 뿐 **보내지 않는다** — 버스 핸들도 engage 시퀀스도 없다. 채우면 GUI 가 `{sent:true}` 를 받고 팔은 그대로다 (NORM-007) |
| **`/api/system/report`** | S-13 이 부르는데 백엔드 0건 |
| **`PG-*` 게이트 판정 봉인** | 봉인할 기계가 없다. `registry/state/store/state.json` 은 **존재한 적이 없고**, 그것을 쓰던 `oa-state` 는 2026-08-26 에 삭제됐다(§6b). 게이트 통과 여부는 실기 캡처와 작업로그가 들고 있다 |
| **Isaac Tier-2** | `WP-5-09`~`14`. 코드 0줄. `Isaac` 문자열은 `ops/versionpin` 승급 차단기에만 있다 |
| **전원상실 복구 상태머신** | 사용자 확정 — 안 짓는다 (§7) |

### 계약 13종 — 이름이지, 잠금이 아니다

`CTR-ACT@v1` `CTR-CAL@v2` `CTR-CAM@v1` `CTR-CAP@v1` `CTR-ERR@v2` `CTR-GW@v1` `CTR-OWN@v1`
`CTR-PLUG@v1` `CTR-PRIM@v1` `CTR-REC@v1` `CTR-TEL@v1` `CTR-UNIT@v1` `CTR-WS@v2`

**2026-08-26: 동결 기계를 삭제했다.** 없어진 것 — 동결 장부(`registry/contracts/freeze_ledger.yaml`),
계약 인덱스, `CI-09`(내용 해시 대조), `oa-contracts` CLI, `CONTRACT_FROZEN` 집행.
`@vN` 은 **이름의 일부로 남는다.** 계약을 바꾸는 것은 이제 파일을 고치는 일이고, git 이 그 기록이다.

왜 지웠나 — `plan/01` §6.2 는 계약을 *"두 병렬 워크플로우 사이의 뮤텍스"* 라고 정의한다. 뮤텍스는
동시에 쓰는 쪽이 둘 이상일 때만 뜻이 있다. 병렬 fan-out 은 끝났고 지금은 순차로 짓는다.
한 명이 쓰는 뮤텍스가 하는 일은 `git diff` 가 이미 한다.

**대신 남은 것 — 이게 실제로 드리프트를 잡던 절반이다.**

| 무엇 | 어디 |
|---|---|
| 프런트 미러 ↔ 백엔드 원본 대조 | `ws/errors.contract.test.ts` · `global/contracts/errorCodes.test.ts` · `ws/closeCodes.contract.test.ts` · `ws/envelope.contract.test.ts` |
| 계약별 `reverify` — 실린 JSON ↔ 타입 표면 | `contracts/*/reverify.py` |
| 형상 검사(차원·단위·시계 도메인 등) | `contracts/recorder/reverify.py:59-65` 외 |

지운 것은 **세대 번호를 내용 해시에 묶는 층** 하나다. 그 층이 한 일은 오늘까지 0건이었고,
그것이 만든 것은 고칠 수 없는 라벨과 종료하지 않는 카스케이드였다.

### 어제까지 여기 적혀 있던 카스케이드·순환

`CTR-ERR@v2` 아티팩트가 자기를 `@v1` 이라 부르던 문제, 그것을 고치면 `CTR-PRIM` → 3A 계약 5종으로
번지고 `prim ↔ ws` 순환에서 멈추지 않던 문제 — **전부 사라졌다.** 원인이 잠금이었기 때문이다.
라벨은 편집 한 줄로 맞췄고 미러 27파일이 따라왔다. 경위는
`work_log/2026-08-25_거절은-…md` §7 이 들고 있다.

### `telemetry` 본문 형상이 프런트에 둘이다 — 🔴 아직 유효하다

- `screens/S-03/motorDomain.ts:269-289` — `body["motor_states"]` = `{joint_name, temp_mos_c, temp_rotor_c, err_nibble}[]`
- `ws/synthetic.ts:52` — `{sequence, observation:{"observation.state":[]}}`

둘 다 `CTR-WS@v2` 의 `telemetry` 프레임에 없다 — 그 프레임은 **필드가 0개**다. 잠금을 지운 것이
이 문제를 고치지는 않는다. 형상이 둘이면 소비자가 둘로 갈리고, 그건 잠금이 있든 없든 결함이다.
텔레메트리를 실제로 흘릴 때 **하나로 정해야 한다**.

---

### 6b. 2026-08-26 — 조율 기계를 지웠다

사용자 판정: *"계약이니 게이트니 뭐니 하는거 다 좇같은데, 꼭 필요한것만 있으면 되잖아."*

**전제가 사라졌기 때문이다.** `plan/01` §6.2 는 계약을 *"두 병렬 워크플로우 사이의 뮤텍스"* 라고
정의한다. 뮤텍스는 동시에 쓰는 쪽이 둘 이상일 때만 뜻이 있다. 병렬 fan-out 은 끝났고 지금은
순차로 짓는다. 한 명이 쓰는 뮤텍스가 하는 일은 `git diff` 가 이미 한다.

저장소가 스스로 말한 증거 — `registry/state/store/state.json` 은 **존재한 적이 없고**, 177 WP 전부
형식상 `not_started` 이며, `CI-18` 은 `sites=0` 이었다. **WP 상태머신은 한 번도 안 돌았다.**

#### 지운 것

| | 규모 |
|---|---|
| `registry/traceability.yaml` | **57,489줄** |
| `registry/checks/**` — CI 규칙 28종 + 픽스처 | 5,089줄 |
| `registry/ingest/**` — 계획문서 → 레지스트리 파서 | 2,361줄 |
| `registry/contracts/**` — 동결 장부·계약 인덱스 | 1,942줄 |
| `registry/generate/**` — 인덱스 185파일 생성 | 898줄 |
| `registry/normalization/{validator,gate_map,cli,seed}.py` | 792줄 |
| `ops/launch/**` — WP 스포너 | 753줄 |
| `ops/cancel/{executor,policy,staticcheck}.py` | 413줄 |
| `ownership/**` · `dashboard/**` · `registry/schema/**` · `registry/state/**` | — |
| `contracts/fixtures/contract_regression.py` · `contracts/plugin_api/freeze.py` | 호출자 0이었다 |
| 테스트 (`boot01`~`boot05`, `n1`, 기계 시험분) | ~270건 |

**파일 162개 삭제. `registry` 11,125 → 2,003줄. 게이트 14 → 9. 진입점 6 → 3.**
파이썬 258,728 → 244,456줄. **로봇을 시험하는 테스트는 0건 삭제** — 5,324건 그대로 초록이다.

#### 안 지운 것과 그 이유

- **`contracts/**` 전체** — 이건 부기가 아니라 **공유 타입**이다. `units` 49곳, `action` 47곳,
  `ws` 28곳, `prim` 20곳이 import 한다. 지우면 로봇이 멈춘다.
- **`ops/cancel/scheduler.py` 의 `LatchReason`** — 39곳이 쓰고 **그중에 정지 경로가 있다**(WS
  디스패처·충돌 가드·데드맨·감사 링).
- **`registry/env` + `normalization/content_hash`** — 학습 산출물의 provenance 스탬프
  (`backend/learning`, `backend/policy_matrix`, `sim/harness` 가 "어느 환경/어느 정규화에서
  나왔나"를 찍는다).
- **미러 대조 테스트 전량** — 두 표현이 한 사실을 말하는지 보는 것. 드리프트를 잡던 진짜 절반이다.

#### 지우면서 실제로 고친 것

1. **라벨.** 잠금이 사라지자 `CTR-ERR@v2`·`CTR-CAL@v2` 가 **편집 한 줄**로 맞았다(미러 27파일).
   전날 회차를 막았던 카스케이드와 `prim ↔ ws` 순환은 개념 자체가 없어졌다.
2. **안전 래치의 두 번째 문.** 워크플로우 취소기를 지우니 `ActuationScheduler.latch_to_hold` 가
   고아가 됐다 — 아무도 안 여는 문인데 남아 있으면 다음 사람은 둘 다 살아있다고 읽는다.
   `engage_safety_latch` 하나만 남았다.
3. **`CI-03b`**(삭제 전 마지막 수리). 죽은 게 아니라 **없는 파일**을 읽고 있었고 매 실행마다
   *"이 파일이 없어서 아무것도 안 봤다"* 고 출력했다. 실재 파일로 돌리자 정규식이 16진수 코드를
   형식 위반으로 잡는 것과, 감시하던 불변식(「한 도메인에 발행처 하나」)이 데이터에 의해 반증된다는
   것이 드러났다.

#### 규율은 `CLAUDE.md` §4b 로 옮겼다

> 이 기계가 막는 충돌을 대라. 그 충돌을 일으킬 수 있는 쓰는 쪽 둘을 대라.
> 둘 중 하나라도 미래형이면 아직 짓지 마라.

그리고 검사의 판정 기준 — **모든 검사는 오늘의 데이터에서 실패할 수 있어야 한다.** 없는 파일이나
빈 축을 가리키는 검사는 통과하는 검사와 구분되지 않고, 세어지고 신뢰받고 조용하기 때문에 검사가
없는 것보다 나쁘다.

---

## 7. 사용자 확정 — 되풀이 금지

| 확정 | 날짜 | 내용 |
|---|---|---|
| 안전 상수 우리 기준 유지 | 08-06 | 토크 40/27/7 N⋅m · 온도 115/95℃ · 속도캡 722/90. 옆 레포 실측이 2~8배 작지만 채택 안 함. **재론 금지** |
| 전원차단 경계 없음 | 08-04 | 릴레이 계획 없음. 하드 E-Stop = 전원라인 물리 버튼(사람 손)뿐 (NORM-007) |
| 래치 디스크 지속성 불필요 | 08-14 재확인 08-17 | 연구개발 리그. `WP-3B-15` ⑦ 재시작 항목 **미충족 확정**. 그 빨간불은 원인 재추적 대상 아님 |
| 복구 상태머신 안 짓는다 | 08-17 | 위험 경로는 이미 닫혀 있다 — `connect()` 자동영점 제거(`openarm_follower_oa.py:519-530`), 미검증 영점 토크-ON 거부(`torque_session.py:1264`) |
| GitHub Actions 삭제 | 07-28 | 게이트는 `./scripts/gates.sh` 뿐. **다시 만들지 말 것** |
| 다크 모드 없음 | 08-24 | `theme` runtime_config 서브객체째 삭제. 명세에 테마 FR 0건이었다 |
| 도달 안 되는 코드 전부 유지 | 08-24 | 곧 다 짓는다. 지우지 말고 이 문서로 표시만 |
| 조율 기계는 최소로 | 08-26 | 계약·레지스트리·게이트는 **동시에 쓰는 쪽이 둘 이상일 때만** 짓는다. 규율은 `~/.claude/CLAUDE.md` §4b. 위 08-24 확정은 **제품 코드**에 적용되고 그것을 관리하는 기계에는 적용되지 않는다 |

---

## 8. 다음에 이을 것

막힘 없는 순서로.

| | 무엇 | 크기 | 비고 |
|---|---|---|---|
| 1 | ~~**`onError` 배선**~~ | — | **전제가 틀렸다. 2026-08-25 폐기.** error 프레임은 존재하지 않으므로 도착하지도, 버려지지도 않는다 — `CTR-WS@v2` 프레임 열 종에 error 가 없고(`contracts/ws/schema.py:223-338`), 백엔드 송신 경로는 `sink.py:121`·`app.py:198` 둘뿐이다. `onError` 는 생산자 0인 소비자이며 `CG-G-03g` 는 `CTR-WS@v3` 없이는 열리지 않는다. 그 자리에 있던 실제 결함은 §8.1 로 옮겼고 고쳤다 |
| 2 | ~~**`oa-serve` 실기 백엔드**~~ | — | **됐다(2026-08-26). §3.4 참조.** `--arm real` 이 `can_binding.json` 으로 채널을 풀고, 양팔 락을 쥐고, `BiOaOpenArmFollower` 를 열어 보드에 실기 값을 올린다. 첫 실행은 아직 — 뜨는 순간 모터 14개가 통전된다 |
| 3 | **`telemetry` 프레임에 본문을 준다** | 중간 + 결정 | 2번 뒤. 세대 범프가 아니라 **형상 결정**이다 — 파이썬 표·`envelope.schema.json`·프런트 표 셋이 같은 것을 말하게 하고, 위의 갈라진 형상 둘 중 하나를 고른다 |
| 4 | 정지 명령 루프 | 중간 | 3번 뒤. 선행은 토크-ON 이고 **사람이 팔 옆에 있어야 한다** |
| 5 | `/api/system/report` | 중간 | 포트 정본이 `spec/01`:456-462 마크다운 표뿐이라 상수로 박으면 세 번째 정본이 된다 — 읽는 방법 결정 필요 |

### 8.1 이미 이었다 — 서버 거절은 닫힘 코드로 온다 (2026-08-25)

`CTR-WS@v2` 에 error 프레임이 없으므로 백엔드는 거절을 **WebSocket 닫힘**으로 답한다. 코드
아홉 종(4400–4408)을 `backend/ws/constants.py:44-56` 이 소유하고, `app.py:171-176` 은 브라우저가
읽을 수 있도록 **`accept()` 뒤에** 닫으며, `app.py:46-64` 는 사유를 RFC 6455 한계인 123 바이트로
자른다 — 넘기면 사유가 아예 도착하지 않기 때문이다.

브라우저는 그 코드와 사유를 `wsClient.ts` 의 `socket.onclose = () => handlers.onClose()` 에서
버리고 있었고, 그 뒤 **조건 없이 1초마다 재접속**했다. 영구 거절(예: 4407 origin, 4408 이 프로세스는
팔을 명령하지 않는다)이 끝나지 않는 재접속 루프가 되고 운영자에게는 아무것도 안 보였다.

지금은 이렇다.

| | 지금 |
|---|---|
| 분류 | `ws/closeCodes.ts` — 4400–4499 는 거절(범위), 그중 **4400·4401·4407 만 재접속 무의미**(열거). `closeCodes.contract.test.ts` 가 `backend/ws/constants.py` 의 `__all__` 과 `app.py` 의 `handshake_session` 본문을 읽어 대조한다 |
| 재시도 | **핸드셰이크 거절만** 안 한다(role·session·Origin 은 클라이언트 생성 시 고정이라 다음 소켓도 같은 판정을 받는다). 프레임 거절 6종과 transport 닫힘은 재시도 — **이 소켓이 소프트 스톱을 나르므로**(`FR-GUI-065`, `backend/ws/arm_channel.py:13-15`) 명령 하나가 거절됐다고 채널을 끊으면 정지가 리로드까지 사라진다 |
| 표면 | 핸드셰이크 거절이면 `RealtimeProvider` 가 `status="unavailable"` + `reason="4407: <서버 사유>"`. `ControlLeaseHost`(`Layout.tsx:50`, 전 화면)가 이미 그린다. 프레임 거절은 `stats().refusalCount` 로만 센다 — 화면 표면은 아직 없다 |

알림 센터에는 붙이지 않았다 — `Notification` 은 `OA-*` 코드를 요구하는데 4404 는 `OA-*` 가 아니고,
닫힘 코드로 `OA-*` 를 지어내는 것은 `wsClient.ts:327-330`·`decoder.ts:4-6` 가 명시적으로 금한다.
`CG-G-03g` 는 여전히 `CTR-WS@v3` 대기다.

### 착수 전 알아야 할 함정

1. `tests/wp3b15/conftest.py:236-273` `expect_close()` 는 서버 메시지를 **정확히 하나** 읽고 프레임이면 실패시킨다. 요청 없이 telemetry 를 밀면 거절·리스 테스트가 전부 깨진다 — 결함이 아니라 순서 문제다
2. `tests/wp3b15/test_single_channel.py:76-88` 이 `backend/ws/` 의 모든 `.py` 를 소문자로 읽어 `webrtc`·`foxglove`·`rosbridge`·`grpc-web` 이 있으면 실패시킨다 — **주석에 써도 걸린다**
3. 스레드 경계는 건널 것이 없다. 보드는 락 없는 속성 읽기(`board.py:155-162`)라 루프가 당겨오면 되고, `app.py:192` 의 `asyncio.create_task(sink.drain_forever())` 가 이미 동시 송신 태스크의 선례다
4. `uv sync` 는 `pyzed` 를 지운다(락에 없는 벤더 휠). 복구: `.venv/bin/python /usr/local/zed/get_python_api.py` 로 휠만 받고 → `uv pip install <휠>`. 사본 `~/.local/share/openarm/`

---

## 9. 이 문서를 갱신하는 법

**회차가 끝날 때마다 §3·§5·§6 을 다시 본다.** 진입점이 하나 생기면 §5 에서 §3 으로 줄이 옮겨가고, 도달 줄수가 바뀐다. §2 의 측정을 다시 돌려 숫자를 갱신한다.

작업로그(`work_log/`)는 계속 회차별로 쓴다 — 그건 **왜 그렇게 했는가**의 기록이고, 이 문서는 **지금 무엇이 참인가**다. 둘은 대체 관계가 아니다.
