# STATUS — 지금 무엇이 도는가

작성 2026-08-24 · 기준 커밋 `649123e` + 미커밋 작업트리

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

진입점 14개에서 `import` 를 이행적으로 따라가 도달 집합을 구한다. 재현:

```python
# 저장소 루트에서. tests/ 와 */_tests/ 는 제외.
# 진입점 = pyproject [project.scripts] 8개 + scripts/*.py 5개 (+ ops.launch.cli)
#   backend.config.serve  backend.camera.cli  registry.check  registry.ingest.cli
#   registry.generate.cli registry.contracts.cli registry.env.cli
#   registry.normalization.cli ops.launch.cli
#   scripts.torque_session scripts.jog_joint scripts.can_node_watch
#   scripts.canbind_session scripts.rig_session
```

한계 둘, 그대로 적는다: ① 동적 import·plugin 등록은 못 본다(`registry.checks` 가 처음 오탐이었고 `from registry.checks import (...)` 를 잡아 해소했다) ② 도달 못 해도 **곧 이을 코드**일 수 있다 — §5 가 그 목록이다.

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
| `oa-serve` | FastAPI + SPA + WebSocket 1개 | `--arm` 이 `none`·`dummy` **뿐**. 실기 백엔드 없음 |
| — REST | `GET /api/tools` · `GET /api/config` · `PUT /api/config/{서브객체}` | 서브객체 4개(`layout`·`presets`·`endEffector`·`control`) |
| — WS `/ws/realtime` | 리스 갱신·재무장 핸드셰이크·`stop_hold` 수용 | **서버가 먼저 보내는 프레임 0종.** §6 참조 |
| — SPA | 13화면 + `/viewport` | 값 전량 픽스처. 실시간 구독 0 |

### 3.3 저장소 도구

`oa-check`(CI 규칙 35종) · `oa-registry` · `oa-index` · `oa-contracts` · `oa-env` · `oa-state` · `./scripts/gates.sh` — 검사 18종(파이썬 레인 14 + 프런트 `tsc`·`eslint`·`vitest`·`vite build`), 약 110초.

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
| **`oa-serve` 실기 백엔드** | `ARM_BACKENDS = ("none", "dummy")`. 실기를 서버 프로세스에 붙이는 작업이 통째로 남았다 |
| **텔레메트리 흐름** | `ArmStateBoard` 가 100 Hz 로 쓰는데 `board.view()` 프로덕션 소비자 0. `CTR-WS@v2` 의 `telemetry` 프레임 **필드가 0개**로 동결돼 있어 본문을 못 싣는다 → `CTR-WS@v3` 결정 대기 |
| **정지 명령 루프** | `STOP_HOLD_SENDER = null` (`frontend/src/app/backendLink.ts`). `ArmSession` 은 읽고 게시할 뿐 **보내지 않는다** — 버스 핸들도 engage 시퀀스도 없다. 채우면 GUI 가 `{sent:true}` 를 받고 팔은 그대로다 (NORM-007) |
| **`/api/system/report`** | S-13 이 부르는데 백엔드 0건 |
| **`PG-*` 게이트 판정 봉인** | `registry/state/store/state.json` 이 **존재한 적 없다.** 177 WP 전부 형식상 `not_started`, 게이트 판정 레코드 0건. `oa-state` CLI 는 구현돼 있으나 호출된 적 없다 |
| **Isaac Tier-2** | `WP-5-09`~`14`. 코드 0줄. `Isaac` 문자열은 `ops/versionpin` 승급 차단기에만 있다 |
| **전원상실 복구 상태머신** | 사용자 확정 — 안 짓는다 (§7) |

### 동결된 계약 13종 (`registry/build/contract_index.json`)

`CTR-ACT@v1` `CTR-CAL@v2` `CTR-CAM@v1` `CTR-CAP@v1` `CTR-ERR@v2` `CTR-GW@v1` `CTR-OWN@v1`
`CTR-PLUG@v1` `CTR-PRIM@v1` `CTR-REC@v1` `CTR-TEL@v1` `CTR-UNIT@v1` `CTR-WS@v2`

동결 규칙(`plan/06` §4.3): **동결 후 어떤 필드 추가도 `@v(n+1)` 발행이다.** 선택 필드도 예외 없다.
집행은 `CI-09`(내용 해시 대조) + `CR-2`(미동결 계약 소비 금지) + `CR-3`(발행 절차).

### 계약이 비어 있는 동안 자란 것 — 🔴 `@v3` 때 정리할 것

`telemetry` 본문 형상이 프런트에 **둘** 생겼고 서로 다르다:

- `screens/S-03/motorDomain.ts:269-289` — `body["motor_states"]` = `{joint_name, temp_mos_c, temp_rotor_c, err_nibble}[]`
- `ws/synthetic.ts:52` — `{sequence, observation:{"observation.state":[]}}`

둘 다 `CTR-WS@v2` 에 없다. **필드를 비워둔 동결은 동결이 아니었다.**

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

---

## 8. 다음에 이을 것

막힘 없는 순서로.

| | 무엇 | 크기 | 비고 |
|---|---|---|---|
| 1 | **`onError` 배선** | 작음 | `wsClient.ts:362-364` 가 `onError` 를 부르는데 `ws/defaults.ts` 가 안 넘긴다. 백엔드 결함 프레임이 도착해서 **버려지고 있다.** 계약 변경 불필요. 이걸 이으면 `CG-G-03g`(ERROR 이상 ack 전까지 배지 유지)가 처음으로 성립 가능해진다 |
| 2 | **`oa-serve` 실기 백엔드** | 큼 | `--arm real`. 이게 되기 전에는 텔레메트리를 열어도 합성값만 흐른다 |
| 3 | **`CTR-WS@v3`** | 중간 + 결정 | 2번 뒤. 파이썬 표 + `envelope.schema.json`(CONTRACT_FROZEN, `CI-09` 대조) + 프런트 표 셋이 함께 움직인다 |
| 4 | 정지 명령 루프 | 중간 | 3번 뒤. 선행은 토크-ON 이고 **사람이 팔 옆에 있어야 한다** |
| 5 | `/api/system/report` | 중간 | 포트 정본이 `spec/01`:456-462 마크다운 표뿐이라 상수로 박으면 세 번째 정본이 된다 — 읽는 방법 결정 필요 |

### 착수 전 알아야 할 함정

1. `tests/wp3b15/conftest.py:236-273` `expect_close()` 는 서버 메시지를 **정확히 하나** 읽고 프레임이면 실패시킨다. 요청 없이 telemetry 를 밀면 거절·리스 테스트가 전부 깨진다 — 결함이 아니라 순서 문제다
2. `tests/wp3b15/test_single_channel.py:76-88` 이 `backend/ws/` 의 모든 `.py` 를 소문자로 읽어 `webrtc`·`foxglove`·`rosbridge`·`grpc-web` 이 있으면 실패시킨다 — **주석에 써도 걸린다**
3. 스레드 경계는 건널 것이 없다. 보드는 락 없는 속성 읽기(`board.py:155-162`)라 루프가 당겨오면 되고, `app.py:192` 의 `asyncio.create_task(sink.drain_forever())` 가 이미 동시 송신 태스크의 선례다
4. `uv sync` 는 `pyzed` 를 지운다(락에 없는 벤더 휠). 복구: `.venv/bin/python /usr/local/zed/get_python_api.py` 로 휠만 받고 → `uv pip install <휠>`. 사본 `~/.local/share/openarm/`

---

## 9. 이 문서를 갱신하는 법

**회차가 끝날 때마다 §3·§5·§6 을 다시 본다.** 진입점이 하나 생기면 §5 에서 §3 으로 줄이 옮겨가고, 도달 줄수가 바뀐다. §2 의 측정을 다시 돌려 숫자를 갱신한다.

작업로그(`work_log/`)는 계속 회차별로 쓴다 — 그건 **왜 그렇게 했는가**의 기록이고, 이 문서는 **지금 무엇이 참인가**다. 둘은 대체 관계가 아니다.
