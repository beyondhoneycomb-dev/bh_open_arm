# 2026-07-27 — 코퍼스 이름변경 여파, 포매터 분열, 그리고 감사에서 나온 것들

> 기능 개발이 아니라 **검토 세션**이다. 요청: 문서와 코드를 읽고 전 범위에서 버그·개선점을 찾아
> 고칠 것. 세션은 CI 게이트 4개를 로컬에서 재현하는 것으로 시작했고, **그중 3개가 빨간불**이었다.
> 그래서 순서가 뒤집혔다 — 빨간 baseline 위에서는 어떤 감사 결과도 묻히므로 baseline부터 수리했다.
>
> 세션 중 사용자 승인이 필요한 지점이 3개 나왔고, 모두 승인받아 이번 세션에서 처리했다(§7).

## 0. 시작 시점의 진짜 상태

| 게이트 | 시작 상태 | 원인 |
|---|---|---|
| `pytest -q` | **exit 2** — 수집 단계에서 중단, 전 스위트 미실행 | 코퍼스 이름변경 |
| `registry.ingest.cli --check` | **exit 1** — FileNotFoundError | 코퍼스 이름변경 |
| `registry.check --all` | **exit 1** — 3,665건 / 8개 규칙 FAIL | 코퍼스 이름변경 |
| `registry.normalization.cli --check` | **exit 1** (ENV `ledger-verify`) | 코퍼스 이름변경 |
| `ruff format --check` | **exit 1** (CI `quality`) | 포매터 버전 분열 |
| `registry.env.cli --check` | **exit 1** (ENV `contract-regress`) | 미선언 의존성 |
| `registry.generate.cli --check` | exit 0 | — |

GitHub 상으로도 **2026-07-25 이후 모든 push에서 CI가 실패**하고 있었다. CI 잡은 14~33초 만에
죽었는데, 이는 테스트에 도달하지도 못했다는 뜻이다. 저장소 어디에도 이 사실이 기록돼 있지 않았고,
그 사이 커밋 메시지는 모두 *감사 무결점*이라고 적혀 있다 — 그 감사들은 실재했지만 **게이트를 끝까지
돌려본 적이 없고, GitHub을 본 적이 없다.**

## 1. 원인 하나: 디렉터리 이름 하나, 서로 연결되지 않은 주장 네 종류

`f0cbaa1 "revised"` 가 `docs/plan/` → `docs/v1/plan/`, `docs/spec/` → `docs/v1/spec/` 를 순수
이름변경(`R100`, 내용 동일)으로 옮겼다. 그 경로를 **읽는** 쪽은 하나도 바뀌지 않았다.

코퍼스 위치는 **성격이 다른 네 곳**에 주장돼 있었고, 어느 둘도 함께 실패할 수 없었다:

1. **파이썬 상수 12개** — `registry/checks/corpus.py`, `registry/ingest/cli.py`,
   `registry/normalization/{loader,content_hash,gate_map,validator}.py`,
   `registry/contracts/catalog.py`, `registry/checks/fixtures/{__init__,cases}.py`,
   `registry/checks/ci_11b_self.py`, 그리고 테스트 모듈 8개.
2. **JSON Schema 의 `pattern`** — `traceability.schema.json` 이 `spine_ref` 에
   `^docs/plan/[^@]+@[0-9a-f]{7,40}$` 를 요구. 파이썬만 고쳤다면 **자기 스키마가 거부하는 문서로
   레지스트리를 재파종**했을 것이다.
3. **검사기 안의 정규식** — `CI-17` 의 `PLAN_DOC_PATH`. 이건 계획 문서 *본문*에도 적용되므로
   코퍼스 내부 상호참조까지 하중을 받는다.
4. **코퍼스 문서 자신의 상호참조 56곳.**

디렉터리 2개 이름변경이 3,665건이 된 이유가 이것이다 — CI-01b가 요구사항 선언 1,207건, CI-04c가
수용 참조 1,035건, CI-17이 인용 1,218건, CI-14b가 WP 177개 전량을 잃었다. **틀린 믿음 하나,
서로 호환되지 않는 인코딩 네 벌.**

### 수리는 상수 하나이지, 리터럴 16개 정정이 아니다

`registry/__init__.py` 가 이제 `CORPUS_VERSION = "v1"` 를 들고 나머지를 전부 파생한다 —
`PLAN_SUBPATH`/`SPEC_SUBPATH`(상대, 루트를 인자로 받는 검사기·검증기용. 이들은 진짜 저장소일 수도
테스트가 만든 조작 트리일 수도 있어서 이 패키지의 루트를 절대 쳐다보면 안 된다),
`PLAN_DIR`/`SPEC_DIR`/`NORMALIZATION_DIR`(절대), `PLAN_DIR_REL`/`SPEC_DIR_REL`/`SPINE_DOC_REL`/
`DAG_DOC_REL`(레지스트리 필드값·리포트 텍스트용 POSIX 문자열).

`registry/paths.py` 가 아니라 패키지 루트에 둔 이유는 기록해둘 값어치가 있다. 새 모듈은
**어떤 `owns[]` 글롭도 주장하지 않는 파일**이고, 첫 시도에서 `registry/paths.py` 를 만들자
**CI-02b가 정확히 그것을 잡았다**. 소유를 주장하려면 `06` §3.2 와 `02a` 의 소유 표를 열어야 하는데,
경로 상수 하나 두자고 거버넌스 표를 다시 여는 건 맞지 않다. `registry/__init__.py` 는 이미
`WP-BOOT-01` 소유로 선언돼 있었고 비어 있었다.

파이썬이 닿을 수 없는 사본 두 개는 **테스트로 못박았다** — 함께 실패하게 만드는 유일한 수단이다:

- `tests/boot01/test_registry.py::test_schema_spine_pattern_agrees_with_the_corpus_constant`
- `tests/env03/test_premerge_lint.py::test_ruff_is_pinned_identically_for_the_hook_and_the_gate` (§2)

**의도적으로 건드리지 않은 것.** `docs/v1/plan/normalization/{ledger.yaml,gate_spec_map.yaml}` 는
Wave −1 정규화 해시의 두 입력이다 — 다만 §7.1에서 결국 `ledger.yaml` 을 한 줄 고쳐야 했고, 그때는
해시 재발행까지 정식 절차로 처리했다. `docs/v1/work_log/*` 도 그대로 뒀다: 당시의 경로를 서술한
기록이다.

### 이 세션이 실제로 밟은 함정 — 재발할 것이므로 남긴다

1차 sweep은 `docs/(plan|spec)/` 를 — **뒤에 슬래시를 붙여** — grep하고 완료를 선언했다.
`root / "docs/plan"` 과 `REPO_ROOT / "docs" / "spec"` 형태를 전부 놓쳤고, 그게 테스트 모듈 9개였다.
스위트는 정확히 1차 sweep이 보지 않은 자리에서 깨졌다. **grep은 어디를 볼지 알려주지, 고른 패턴이
무엇을 찾을 수 있는지까지 알려주지 않는다.**

## 2. 원인 둘: 포매터 두 벌, 게이트 하나

- `pyproject.toml [dev]` → `ruff>=0.6` → CI가 최신(0.15.22)을 설치
- `.pre-commit-config.yaml` → `rev: v0.6.9`

즉 트리를 **포맷하는** 훅과 그 포맷을 **판정하는** 게이트가 같은 포매터의 다른 버전이었고, 둘은 줄
나눔 방식이 다르다. 훅이 올바로 포맷한 파일을 CI가 거부했고, **어느 파일도 이 불일치를 기록하지
않으므로** 실패는 "포맷 실수"처럼 읽힌다. 그 상태로 5개 파일이 앉아 있었다.

둘 다 `0.15.22` 로 정확히 고정하고, `tests/env03` 가 일치를 단언한다. 범위가 아니라 정확한 핀인
이유: **머지 게이트로 쓰이는 포매터는 스타일 신탁(oracle)이고, 커밋 없이 바뀌는 신탁은 게이트를
비결정적으로 만든다.**

## 3. 원인 셋: 사실 하나를 평가 못 하면 아무것도 보고하지 않는 게이트

ENV `contract-regress` 는 `registry.env.cli --check`(상류 계약 사실 11개)를 돌린다.
`kinematics_unconstrained_fallback` 이 `openarm_control` 을 import하는데,
`registry/env/upstream.py:348` 이 모든 predicate를 **무방비로** 호출하고 있었다:

```python
result = predicate()          # 하나만 raise해도 11개 전부 판정 없음
```

`ImportError` 하나가 전체 실행을 트레이스백으로 끌어내렸다. 통과했을 사실 10개도 **아무 판정을
내지 못했고**, 출력은 "이 사실 하나를 평가할 수 없었다"가 아니라 "검사기가 고장났다"로 읽힌다.

predicate마다 격리했다. raise는 이제 예외 이름을 담은 `FAIL_BLOCKING` 행 하나가 되고 나머지 10개는
정상 보고된다. 선언된 severity와 무관하게 `FAIL_BLOCKING` 인 이유는 기존 unknown-predicate 행과
같다 — **검사되지 않은 인용은 이 검사기가 닫으려는 바로 그 구멍이므로, 절대 pass로 보고될 수 없다.**

**이것으로 잡이 초록이 되지는 않으며, 되어서도 안 된다.** `openarm_control` 은 **어디에도 선언되어
있지 않다** — `pyproject.toml`(`dependencies`·`[robot]` 둘 다), `targets/`, `deps/` 어디에도 없다.
개발 venv에 손으로 설치돼 있을 뿐이고, 그래서 로컬은 GREEN을 찍고 CI는 한 번도 통과한 적이 없다.
→ §8 D-2.

## 4. 원인 넷: 아무 게이트도 보고 있지 않던 10만 줄과 787개 테스트

CI는 `registry ops dashboard tests` 만 검사하고 있었다.

| 트리 | py 파일 | LOC | ruff(CI) | mypy | 테스트 |
|---|---|---|---|---|---|
| `backend/` | 737 | 100,178 | ✗ → **이제 ✓** | ✗ | pytest 경유 |
| `contracts/` | 59 | 10,221 | ✗ → **이제 ✓** | ✗ | pytest 경유 |
| `sim/` | 57 | 8,623 | ✗ → **이제 ✓** | ✗ | pytest 경유 |
| `registry/` | 81 | 13,323 | ✓ | ✓ | ✓ |
| `ops/` | 74 | 9,222 | ✓ | ✓ | ✓ |
| `frontend/` | — | TS | ✗ → **이제 ✓** | — | ✗ → **이제 ✓** |

`ruff check` 와 `ruff format --check` 가 이제 파이썬 트리 전량을 덮는다(워크플로 두 파일 모두).
공짜였다 — 11개 트리가 이미 전부 통과하므로, 새 작업을 요구하는 게 아니라 **참인데 보호되지 않던
상태를 고정**하는 것이다.

`frontend` 잡을 신설해 `tsc --noEmit`·`eslint .`·`vitest run` 을 돌린다 — 157파일 787테스트 전량
초록인데 어떤 게이트도 보지 않고 있었다. 그중 일부는 저장소 루트에서 `contracts/` 와
`docs/v1/spec/` 를 읽으므로, `S-13/testSupport.ts` 는 이름변경된 코퍼스를 읽고 있었고 같은 sweep에서
수리했다.

**mypy는 의도적으로 넓히지 않았다** — 이유가 곧 발견 내용이다(§8 D-1).

## 5. 병렬 감사 — 방법과 결과

12개 하위 시스템 영역에 finder를 하나씩 붙이고, 각 finder의 결과를 **반증 전담 검증자**에게
넘기는 파이프라인(24 에이전트)을 돌렸다. 검증자 지시는 명시적으로 "반증하라, 확증하지 못하면
기본값은 REFUTED" 였다.

| | 건수 |
|---|---|
| 제기됨 | **39** |
| CONFIRMED | 11 |
| UNCERTAIN | 3 |
| **REFUTED** | **25 (64%)** |

**반증 비율이 이 감사의 값어치다.** 예를 들어 "`LoadPreflight` 가 그리퍼 미러 검증 불가일 때
`allowed=True` 를 반환한다"(conf 15), "`RunawayDetector` 의 `joint_limits=None` 이 조건 ①을 영구
비활성화한다"(conf 20) 는 그럴듯했지만 호출자를 열어보면 전부 무너졌다.

세션 한도로 finder 3개(`sim`·`safety-physics`·`crosscut-sentinels`)가 죽어 별도 워크플로로
재실행했다(결과는 §9).

검증자가 놓친 것도 있다. MCAP writer 건은 검증자가 UNCERTAIN(conf 45)을 줬지만, **직접 재현
스크립트를 돌려 확정**했다(§6.3). 코드를 실행해보는 것이 읽는 것을 이긴다.

## 6. 감사에서 확인되어 고친 결함

### 6.1 held 상태의 IK 설정 표류 — 5 mm 요청이 92 mm 명령이 된다

`backend/cartesian_jog/jog.py:669` `_hold` 는 독스트링이 "움직이지 않고 latch한다"고 말한다.
committed pose는 실제로 그대로다. **IK 설정은 아니다** — 솔버는 대상이 부적합하다고 결론내기 전에
매 반복마다 설정을 제자리에서 적분하므로, 포기된 solve는 어댑터를 도달한 지점에 남겨둔다.

`commit=False` 탐침 분기(`jog.py:456`)는 정확히 이 불변식을 `self._adapter.sync(self._committed)`
로 복원한다. `_hold` 는 하지 않았다.

결과는 낡은 표시값이 아니다. 다음에 수락된 jog는 **표류한 설정에서** 작은 delta를 풀고 **그것을**
commit한다. `test_hold_no_skip` 이 hold 이후를 `seed()` 로 이어가서(재동기화되어 버그를 가림)
아무도 못 봤고, 운영자 경로인 `resume()` 는 그렇지 않다.

**실측**: 수정 없이 `+Z` 5 mm jog가 TCP를 **92 mm** 움직였다 — 18배. 회귀 테스트
`tests/wp2d01/test_hold_leaves_no_drift.py` 가 이를 못박는다(수정 전 실패, 수정 후 통과 확인).

> 이 테스트를 쓰면서 처음 만든 단언 하나는 **공허**했다 — `current_pose` 는 `_committed` 에서
> 파생되므로 hold가 건드리지 않는 값을 보고 있었고, 수정 유무와 무관하게 통과했다. 삭제했다.
> 실패할 수 없는 테스트는 없는 것보다 나쁘다(이 저장소의 `VACUOUS` 판정이 존재하는 이유와 같다).

### 6.2 빈 체크섬이 무결성 검사를 끄고 "검증됨" 도장을 찍는다 — 두 곳

`backend/calibration/schema.py:252` 와 `backend/gripper_endpoint/schema.py:353` 이 **같은 모양**이다:

```python
if stored_checksum and stored_checksum != 계산값:   # 비어 있으면 비교를 건너뜀
    raise ...
return replace(..., checksum=stored_checksum or 계산값)  # 그리고 새 지문을 찍음
```

관절 부호나 영점 오프셋을 손으로 고치고 안 맞는 체크섬을 지우는 것(가장 자연스러운 행동)이
**검증을 통과시키는 게 아니라 검증을 끄고** 위조된 본문에 새 지문을 발급한다. 그 값을
`compute_residual`(영점 잔차)과 `ZeroIdentity.from_calibration`(교시 자세 인증)이 신뢰하며,
다음 저장이 유일한 증거를 덮어쓴다.

둘 다 **빈 체크섬 = 실패**로 바꾸고 저장된 값만 반환하도록 했다. 새 거부는
`tests/wp102/test_schema.py` 와 `tests/wp2a08/test_persistence.py` 가 못박는다.

한 가지 확인이 필요했다: `wp2a08` 의 두 테스트가 체크섬을 `pop` 한다. 읽어보니 `__post_init__` 이
sign-mirror 를 **생성 시점에** 강제하므로 체크섬 분기에 도달조차 하지 않는다 — 그 `pop` 은 무효
장식이고, 엄격화는 두 테스트를 깨지 않는다(실행으로 확인).

### 6.3 MCAP writer — 죽은 자식, 무한 큐, 멈추는 close()

`ops/telemetry/mcap_writer.py`. NFR-PRF-038이 writer를 제어 루프 프로세스 밖으로 뺀 그 경계가,
**파트너가 말없이 죽을 수 있는 자리**다. 자식이 파일을 소유하고, `open()` 이 실패하면(디렉터리 없음,
권한, 디스크 가득) 자식은 종료하는데 제어 루프는 계속 샘플을 건넨다.

세 결함이 겹쳐 있었다:

1. `Queue()` 에 **상한이 없다** — 죽었거나 밀린 writer가 디스크 문제를 **팔을 명령하는 프로세스의
   무한 메모리 증가**로 바꾼다. 거기서의 OOM은 안전 사건이다.
2. `write()` 가 자식의 죽음을 **확인하지 않는다** — 영원히 큐에 넣는다.
3. `close()` 가 `join_thread()` 에서 **영원히 멈춘다** — 부모의 feeder 스레드가 아무도 비우지 않는
   파이프로 flush를 시도하며 블록된다. `exitcode` 는 읽히지도 않는다.

**재현**: 자식을 `open()` 에서 죽인 뒤 2,000샘플을 넣고 `close()` → 25초 예산에서 **SIGTERM으로
강제 종료**(멈춤 확정). 멈추는 지점을 `queue.close()` 이후 `join_thread()` 로 특정했다.

수정은 연산별로 실패 방향을 따로 도출했다:

- **`write()`** 는 실시간 경로다. 블록하거나 raise하는 것이 샘플을 잃는 것보다 나쁘다 →
  **degrade + 계수**. 상한 큐 + `put_nowait` + 드롭 카운터, 그리고 매 호출 `exitcode`(논블로킹
  waitpid, 바로 다음 줄의 `json.dumps` 보다 훨씬 싸다) 확인.
- **`close()`** 는 세션 경계다. 손실은 이미 비가역이고 이 기록은 사고를 재구성할 근거다 →
  **거부 + 알림**. timeout join, 죽었거나 시간초과면 `cancel_join_thread()`, 그리고 자식의
  exit code와 드롭 수를 담아 `McapWriterError` 를 raise.

이 배치로 드롭 카운터가 **제어흐름 독자를 갖는다** — 장식이 되지 않는 것은 그 때문이다.
재현은 이제 즉시 반환하며 스스로를 설명한다:
`"exited with code 1 before the file was finished; 2000 sample(s) were dropped"`.
실패 경로 테스트 4개 추가(`tests/wpops05/test_mcap_writer_failure.py`).

### 6.4 양팔 관측에서 CAN 드롭 카운터가 사라진다

`packages/lerobot_robot_openarm/openarm_follower_oa.py:736` 이 per-arm 키에 전부 접두사를 붙이는데,
`can_packet_drop_count` 는 ABC가 **접두사 없이** 선언하는 관측 메타다(`robot_abc.py:53`).
결과: 선언된 특징 집합에 없는 `left_`/`right_` 키 2개가 나가고, **선언된 키는 한 번도 생산되지
않는다.**

LeRobot은 `observation_features` 로 데이터셋 특징을 만든다. 즉 FR-SYS-018이 보존하려는
**CAN 패킷 드롭 집계가 모든 양팔 에피소드에서 빠진다** — 손실 많은 버스에서 녹화한 에피소드가
깨끗한 것과 구별되지 않는다.

메타 키를 접두사 루프에서 제외하고 양팔 합으로 한 번 기록한다. 테스트 2개 추가, 그중 하나는
`set(get_observation()) == set(observation_features)` — **ABC 선언과 손으로 만든 dict를 함께
실패하게 만드는** 단언이다(수정 전 둘 다 실패 확인).

> 이 테스트를 쓰다 두 번째 불일치를 봤다: `use_velocity_and_torque=False` 면 선언 48채널 중
> 32개가 생산되지 않는다. 추적해보니 **결함이 아니다** — F24 세션 시작 검사
> (`ops/telemetry/velocity_torque.py`, `TorqueDataLossError`)가 그 설정으로 녹화를 시작하는 것 자체를
> 거부한다. 그래서 테스트를 `True`(녹화가 가능한 유일한 설정)로 한정하고 이유를 적어뒀다.

### 6.0 확인된 11건 전체와 처분

감사가 CONFIRMED로 확정한 11건 전량이다. **고치지 않은 것도 전부 여기 남긴다** — 검토의 산출물은
고친 것 목록이 아니라 알게 된 것 목록이다.

| # | 파일:줄 | 심각도 | 처분 |
|---|---|---|---|
| 1 | `backend/cartesian_jog/jog.py:669` | HIGH | **수정** §6.1 |
| 2 | `backend/calibration/schema.py:252` (+`gripper_endpoint/schema.py:353`) | MEDIUM | **수정** §6.2 |
| 3 | `ops/telemetry/mcap_writer.py:119` | — (감사는 UNCERTAIN, **재현으로 확정**) | **수정** §6.3 |
| 4 | `packages/…/openarm_follower_oa.py:736` | MEDIUM | **수정** §6.4 |
| 5 | `registry/checks/ci_09.py:175` | LOW | **수정** §6.5 |
| 6 | `ops/acl/units/openarm-can-writer.service:24` | MEDIUM | **수정** §6.6 |
| 7 | `backend/actuation/enforcement.py:191` | **HIGH** | **미수정 — §8 D-5** |
| 8 | `packages/…/openarm_follower_oa.py:337` | **HIGH** | **미수정 — §8 D-6** |
| 9 | `backend/teleop/vr_udp/source.py:175` | MEDIUM | **미수정 — §8 D-7** |
| 10 | `contracts/unit_tags.yaml:62` | MEDIUM | **미수정 — §8 D-8** |
| 11 | `contracts/action/version.py:84` | MEDIUM | **미수정 — §8 D-9** |
| 12 | `registry/checks/ci_16.py:116` | HIGH | **미수정 — §8 D-10** |

### 6.5 파일이 사라지면 스스로 해제되는 동결 잠금

`registry/checks/ci_09.py:175` 가 글롭이 아무 파일도 매치하지 않으면 `continue` 했다. 동결 계약
파일이 **이름변경·이동·삭제되면 자기 잠금을 조용히 해제**하고 규칙은 초록을 보고한다. 이 저장소에서
가설이 아니다 — `f0cbaa1` 이 디렉터리 두 개를 옮겼고, 같은 이동이 계약 글롭에 일어났다면 빨간불이
아니라 침묵이 나왔을 것이다.

빈 확장을 두 상황으로 갈랐다: 기록된 해시가 없으면 동결된 적 없으므로 무해한 skip, **기록된 해시가
있으면 잠금이 아무것도 지키지 않는다는 finding.** 오늘은 9개 글롭이 모두 매치하므로 실사용 finding은
0이지만, **새 분기가 죽은 코드가 아님을 확인했다** — 수정 없이는
`tests/wpops06/test_freeze_lock.py::test_a_moved_frozen_file_does_not_silently_disarm_its_lock` 이
실패하고("the frozen glob matched nothing and CI-09 stayed green") 수정 후 통과한다.

### 6.6 실재하지 않는 유닛에 걸린 부트 게이트

`ops/acl/units/openarm-can-writer.service` — 저장소에 실재하는 **유일한 systemd 유닛**이자
FR-SYS-007(iii)의 커널 강제 절반이다. 그 `[Unit]` 절이:

```ini
Wants=openarm-can-setup.service
After=openarm-can-setup.service network-online.target
```

**`openarm-can-setup.service` 는 저장소 어디에도 없다.** 실재하는 브링업 유닛은
`openarm-can-link.service`(`ops/systemd/constants.py:34`)뿐이다. systemd는 `Wants=`/`After=` 의
모르는 유닛을 **오류 없이 버리므로**, 소원과 순서 둘 다 무효다. CAN 링크 설정이 실패해도 무엇도
전파하지 않고, **버스에 송신할 권한을 가진 유일한 프로세스가 미설정 링크를 상대로 임의 순서에 뜬다.**

두 번째 층: `ops/systemd/boot_order.py` 가 `01` FR-SYS-006 ③을 인코딩하고
(`Requires=`+`After=` 여야 하며 `Wants=` 만으로는 불충분),
`tests/wpops02/test_boot_order.py:30` 이 **`Wants=` 만인 정의는 게이트를 통과하지 못함을 명시적으로
단언한다** — 합성 본문에 대해서만. **아무도 그 술어를 실물 유닛에 겨누지 않았다.** 옳고, 테스트되고,
심판할 대상에 적용되지 않는 술어는 술어가 없는 것과 구별되지 않는다 — `WP-0A-04` 의 mypy와 정확히
같은 모양이다.

`Requires=openarm-can-link.service` + `After=…` 로 고치고, `tests/wpops01/test_boot_gating.py` 를
추가해 **실물 유닛**이 WP-OPS-02의 술어를 통과함을 단언한다. 두 번째 테스트는 유닛이 참조하는 모든
유닛이 이 저장소가 렌더링할 수 있는 것이거나 systemd 내장 target임을 요구한다 — 이름 오타가
`backend_gated_on_link` 를 통과하면서 순서만 조용히 해제하는 경로를 막는다. 원래 유닛에 대해 두
테스트 모두 실패, 수정 후 통과 확인.

> 같은 파일에서 두 번째 결함을 봤다: `ExecStart=… -m backend.can.writer_service` 가 **존재하지 않는
> 모듈**을 가리킨다(`backend/can/` = `bind`·`intruder`·`link`·`lock`·`rid`). 어떤 WP도 그 경로를
> 산출물로 선언하지 않는다. 즉 이 유닛은 설치되면 기동에 실패한다. **고치지 않았다** — writer 서비스가
> 무엇인지 정하는 것은 검토가 아니라 설계다. → §8 D-11.

## 7. 사용자 승인 후 이번 세션에서 처리한 거버넌스 3건

### 7.1 `CTR-CAL@v1` → `@v2` (승인 A)

§6.2의 캘리브레이션 수정이 `CI-09` 를 건드렸다 — `backend/calibration/schema.py` 가
`CTR-CAL@v1` 의 `CONTRACT_FROZEN` 글롭 안이고, `06` §4.3은 단호하다: *"기존 `@v<n>` 의 해시를 다시
찍는 것은 어떤 이유로도 허용되지 않는다."* 이 계약의 동결 범위가 **스키마뿐 아니라 구현 파일 자체**
라서, 이 모듈은 **버그 수정조차 봉인을 깬다.**

절차를 밟다가 **더 큰 결함**을 만났다.

> **`registry/ingest/build.py:194` 의 `read_contract_producers` 가 `@v1` 을 하드코딩하고 있었다.**
> ID 칸에서 이름만 뽑고 `f"{name}@v1"` 을 붙인다. 즉 **produces 축은 v1 이외의 세대를 구조적으로
> 표현할 수 없다** — `06` §4.3이 동결 내용 변경의 유일한 합법 대응으로 지정한 bump를, 계획 기계가
> 표현하지 못한다. 독스트링은 "(with `@v1`)"이라고 태연히 적고 있었다.

ID 칸에서 세대를 읽도록 고쳤다. `01` §6.2만 세대를 명시하고(발급 권한자) `06` §4.1은 맨 이름을
싣는 설계이므로, 명시가 없으면 첫 세대로 해소하고 그 이유를 주석에 남겼다. 나머지 12개 계약은
동작이 그대로다.

그다음 정식 절차:

| 단계 | 결과 |
|---|---|
| 코퍼스 선언 16곳 `@v1`→`@v2` (normalization 원장 제외) | — |
| 재파종 | `produces=['CTR-CAL@v2']`, `WP-G-S02 consumes=['CTR-CAL@v2']` |
| `oa-contracts freeze CTR-CAL@v2 --from-frozen-glob` | seq 10 `SUPERSEDE CTR-CAL@v1`, seq 11 `FREEZE CTR-CAL@v2` |
| 재검증 범위 | 소비자 **1개**(`WP-G-S02`) |

이때 `registry.normalization.cli --check` 가 `NORM-001 [contract] CTR-CAL@v1 has no declared producer`
를 냈다. 원장의 `contract` 필드는 그 판정의 집행을 소유하는 계약을 가리키고, 그 계약은 이제 `@v2`다.
원장은 정규화 해시의 입력이므로 **한 줄 수정 → `--issue` 재발행 → 재파종 → 매니페스트 177개 재생성**
을 정식 절차로 밟았다(`c1b53ff7…` → `4340a0ce…`).

### 7.2 `CTR-ERR@v1` → `@v2` — 죽은 문서 링크 55개

`contracts/errors/error_registry.yaml` 의 `doc_url` 55개가 없어진 `docs/spec/14-…` 를 가리키고
있었고 GUI가 이를 링크로 렌더링한다. 이 파일도 동결 글롭 안이라 §7.1과 같은 벽이었다.

55개를 `docs/v1/spec/` 로 고치고 **전량이 실재 파일로 해소됨을 확인**(unresolvable 0)한 뒤,
코퍼스 선언 24곳을 `@v2` 로 옮기고 `freeze CTR-ERR@v2 --from-frozen-glob` 을 기록했다
(seq 12 `SUPERSEDE`, seq 13 `FREEZE`). 재검증 범위는 소비자 3개
(`WP-3A-00`, `WP-G-01`, `WP-G-03`).

### 7.3 `CI-07` 판정 제외 해제 — **빌드는 이제 의도적으로 빨갛다**

`registry/checks/__init__.py` 의 `JUDGE_EXCLUDED` 가 `CI-07` 을 판정에서 빼고 있었다. 그 코드의
자기 주석: *"한시적. Wave −1 이후 해제할 것 — 그때는 저절로 초록이 된다."* **Wave −1은 끝났다.
저절로 초록이 되지 않았다.**

해제 전에 13건이 진짜 미결인지 확인했다:

- `ledger.yaml` 의 `NORM-003` 은 **구조화된 winners가 게이트 id**(`PG-RT-001a/b`)이고, `NFR-PRF-004/054/055`
  는 산문 칸에 맥락으로 등장할 뿐이다.
- `NFR-SAF-001` 은 `ledger.yaml` 에 아예 없다. `CI-07` 이 읽는 집합은 **`02a` 의 `NORM-*` 표**이고,
  파종기가 읽는 집합은 **`ledger.yaml` 의 구조화된 winners**다.
- 원장 스키마에는 **"미결(open)" 상태가 없다** — 행 하나가 곧 판정이다.

두 출처의 간극이 곧 **판정되지 않은 논쟁 요구사항**이고, `CI-07` 은 정확히 그것을 보고하려고 있다.
파종기가 보수적인 것도 의도적이다(같은 산문 칸에서 도장을 찍으면 규칙이 초록이면서 아무것도 잡지
못한다). **13건을 초록으로 만들려면 13개의 판정이 필요하고, 그중 3건은 안전 요구사항이다 — 나는
안전 판정을 발명하지 않는다.**

해제했다. 결과: `registry.check --all` 이 **13건 판정, BUILD FAILED**.

| 요구사항 | WP | tag | 왜 논쟁 중 |
|---|---|---|---|
| `NFR-SAF-001` | WP-2C-02 | 결정필요 | `02a` `NORM-*` 논쟁 칸 |
| `NFR-PRF-004` | WP-N1-03 | 확정 | `02a` `NORM-*` 논쟁 칸 |
| `NFR-PRF-054` | WP-1-04 | 미확인 | `02a` `NORM-*` 논쟁 칸 |
| `NFR-PRF-055` | WP-0C-06 | 신규구현 | `02a` `NORM-*` 논쟁 칸 |
| `FR-SAF-020` | WP-1-06 | 결정필요 | tag |
| `FR-SAF-031` | WP-2B-10 | 결정필요 | tag |
| `NFR-SAF-002` | WP-2C-06 | 결정필요 | tag |
| `FR-MAN-035` | WP-2B-06 | 결정필요 | tag |
| `FR-MAN-047` | WP-2D-07 | 결정필요 | tag |
| `FR-GUI-118` | WP-2D-07 | 결정필요 | tag |
| `NFR-GUI-004` | WP-5-05 | 결정필요 | tag |
| `NFR-GUI-008` | WP-G-S13 | 결정필요 | tag |
| `NFR-REC-001` | WP-3B-12 | 결정필요 | tag |

**해제를 유지할 것.** 조건이 지난 제외를 남겨두면 *코드에 존재하고 설정에서 꺼진 규칙* — 참이 아닌
채로 신뢰받는 모양 — 이 된다. 각 건은 `ledger.yaml` 에 구조화된 판정 행을 추가하고 해시를 재발행하면
해소된다. 1,216개 레코드 중 해시 보유는 현재 14개다.

### 7.4 세 조치가 깨뜨린 테스트 4개 — 리터럴을 살아있는 값으로 교체

거버넌스 변경 뒤 스위트가 4건 실패했다. 전부 **승인된 변경의 정직한 귀결**이지 새 결함이 아니다.
다만 고치는 방식이 중요했다 — 두 경우 모두 테스트가 **리터럴을 박아둔 것**이 실패의 원인이었고,
리터럴만 갱신하면 다음 bump에서 똑같이 깨진다.

- `tests/wpops06/test_freeze_lock.py` 3건 — `CONTRACT_ID = "CTR-ERR@v1"` 하드코딩. 이제 committed
  authority에서 **FROZEN 상태인 세대를 찾아** 쓰고, 동시에 FROZEN 세대가 정확히 하나임을 단언한다.
  잠금의 본래 단언(잠긴 해시 = 파일 내용 해시, 1바이트 변경 시 발화)은 그대로다. `06` §4.3이 bump를
  규정 대응으로 정한 이상, 리터럴 `@v1` 은 **모든 정당한 bump를 깨진 테스트처럼 보이게** 만들고 그
  수리법이 "리터럴을 고친다"가 되는데, 이는 변화를 감지하는 것이 임무인 잠금에 대해 정확히 반대의
  반사를 가르친다.
- `tests/boot03/test_contract.py::test_judge_range_excludes_the_two_uncheckable_at_landing` —
  `JUDGE_EXCLUDED` 가 2개라고 단언. 이름의 *at landing* 이 말해주듯 BOOT 착지 시점의 사실이었다.
  `test_judge_range_excludes_only_the_self_referencing_rule` 로 바꿔 **CI-18은 제외, CI-07은 판정**을
  단언한다 — 제외가 슬그머니 되돌아오는 것을 막는 것이 이 테스트의 새 임무다.

## 8. 여전히 사용자 결정인 것

**D-1 — 12만 줄에 mypy가 돌지 않고, 그것이 중요함을 증명하는 WP가 `WP-0A-04` 다.** 그 WP는 mypy가
단위 혼동(rad를 deg에 대입, 혼합 산술, 토크 패킷 스케일 오류)을 잡는다는 것을 증명하려고 존재하고,
픽스처는 통과한다. **그 오류들이 실제로 살 10만 줄은 검사되지 않는다.** 실측: `backend/contracts/sim/
packages/ownership/targets/deps` 에 **79파일 266오류**. 164개는 `[type-arg]`(엄격도), 약 38개는
읽어볼 값어치가 있다 — `[attr-defined]` 9, `[call-overload]` 9, `[arg-type]` 8, `[union-attr]` 4,
`[unreachable]` 3. `backend/` 는 `--explicit-package-bases` 없이는 해석조차 안 된다
(`backend/dataset/stats/` 와 `backend/eval/stats/` 가 둘 다 `stats` 모듈을 제공).

고신호 오류 중 6건은 손으로 추적해 **반증**했다 — 다시 제기하지 않도록 기록한다:

- `backend/dataset/integrity/checks/frames.py:28`, `backend/capture_interlock/converted.py:235`
  "Missing return statement" — mypy가 PyAV의 `__exit__` 가 예외를 삼킬 수 있다고 가정해 `with` 밖으로
  제어가 떨어질 수 있다고 본다. 실제로는 `None` 을 반환하며 삼키지 않는다. 설령 삼켜도 호출자가
  `!= expected` 로 비교하므로 **fail-closed** 다.
- `backend/replay/preverify.py:191,232,245,246` `Item "None" … has no attribute` —
  `ok=False ⟹ first_violation is not None` 불변식이 `run_preflight` 의 생성 지점 **두 곳 모두**에서
  성립한다(`backend/collision_preflight/preflight.py:248,257`). 상관관계를 표현하는 타입이 더 낫겠지만
  검토 중에 새 구조를 제안하는 것은 범위 밖이다.

**D-2 — `openarm_control` 은 CI 게이트의 판정이 의존하는 미선언 의존성이다.** `upstream.py:197` 이
introspect하는데 `pyproject.toml`·`targets/`·`deps/` 어디에도 없다. 두 가지 합법적 해소가 있고 정책
판단이다: 무거운 레인의 설치 그룹에 선언하거나, `openarm_control` 의존 사실을 그 패키지가 실제로
공급되는 per-target 레인으로 옮기거나. 그대로 두면 그 잡은 영구히 빨갛다.

**D-3 — lint 범위가 두 번 선언된다.** `ci.yml` 의 `quality` 와 `env.yml` 의 `lint` 가 이제 동일한
ruff 명령을 돌린다. 무엇도 둘을 비교하지 않으므로 한쪽에 추가된 트리는 다른 쪽에서 검사되지 않는다
— 이번엔 손으로 둘 다 고쳤다. 하나를 지우는 건 한 줄이지만 `WP-ENV-03` 의 선언된 산출물에서 잡을
빼는 일이라 소유자 판단으로 남긴다.

### D-0 — 🔴 **최우선**: IK 어댑터와 액션 계약의 좌우 순서가 반대다 (CRITICAL)

세션 한도로 죽었던 감사 3영역(`sim`·`safety-physics`·전역 sentinel)을 재실행해서 나온 건이며,
**내가 직접 재현해 확인했다.**

`sim/ik/adapter.py:244-249` 는 `right[8] + left[8]` 로 16-벡터를 만든다(우선). 상류
`openarm_control.Kinematics.sync` 의 독스트링도 `"float32[16] driver state (right[8]+left[8])"` 로,
**IK 라이브러리는 양방향 모두 우선(right-major)** 이다.

반면 `contracts/unit_tags.yaml:90` 은 `arms: [left, right]` 로 동결돼 있고,
`sim/mujoco/sim_sync.py:46 action_channel_order` 는 그 순서를 그대로 쓴다 — **계약은 좌선
(left-major)**. 팔로워의 `get_observation` 도 left→right 순이다.

그 사이에 있는 `_to_accepted_action`(`sim/ik/adapter.py:358-360`)은 **폭 검사만 하고 치환하지
않는다.** 직접 대조한 결과:

```
slot | dry-run 라벨            | 그 슬롯의 실제 어댑터 관절
   0 | left_joint_1.pos       | openarm_right_joint1     <== 좌우 불일치
   ...
  15 | right_gripper.pos      | openarm_left_finger_joint1  <== 좌우 불일치
좌우가 어긋나는 슬롯: 16/16
```

**16슬롯 전부**가 반대편 팔의 이름으로 라벨링된다. 그래서 `sim/dryrun/runner.py:93` 이 좌선 채널명을
우선 값에 zip하면, **드라이런 게이트가 각 팔을 반대편 팔의 리밋으로 검증한다.** 대부분의 관절은
리밋이 좌우 대칭이라 보이지 않지만 `joint_2` 는 유일하게 미러다(LEFT −90..9° / RIGHT −9..90°) —
즉 **정확히 그 관절에서만 판정이 뒤집힌다.**

더 나쁜 층이 하나 더 있다. `jog.seed()` 는 독스트링상 *"로봇의 실제 관절 상태"* — 즉
`get_observation()` 의 **좌선** 벡터 — 를 받아 `_committed` 에 저장하고 그대로
`adapter.sync()`(우선 API)에 넘긴다. 그런데 `_commit()` 은 어댑터가 뽑은 **우선** 벡터를 같은
`_committed` 에 쓴다. **같은 변수가 마지막에 어느 경로가 썼는지에 따라 의미가 바뀐다.**
`arm_joints("right")` 는 `_committed[0:7]` 을 슬라이스하므로 우선 색인을 가정한다.

두 경계가 모두 미변환이라 **왕복(seed→step→읽기)에서는 서로 상쇄된다.** 값이 다른 소비자
(드라이런 게이트, 팔로워의 `send_action` 접두사 분리, 데이터셋 `action` 채널)로 건너갈 때만 드러난다.
그리고 기존 테스트는 전부 좌우 대칭 값으로 seed한다(`_out_of_limit_config()` = 전 관절 `upper+1.0`,
`np.full(16, 0.5)`, `Deg(0.0)`) — **그래서 900+ 테스트가 초록인 채로 살아남았다.**

**고치지 않았다.** 올바른 수정은 두 경계 모두에서 치환하고(`seed()` 좌선→우선, `_to_accepted_action`
우선→좌선), `arm_joints`·`current_pose`·`sim/fkik/roundtrip.py`·`backend/moveto/gate.py`·
`backend/singularity/nullspace.py`·`backend/teleop/safety_gate/gate.py` 의 가정을 함께 맞춰야 한다.
안전 게이트 경로의 좌우 교환을 긴 세션 끝에 반쯤 고치는 것은 **정확히 위치가 특정된 결함보다
나쁘다.** 비대칭 리밋(`joint_2`)이 오프라인 판별 수단을 주므로 테스트로 증명 가능한 수정이며,
별도 WP로 착수할 것.

### 그 밖의 재실행 감사 결과

| 파일:줄 | 심각도 | 내용 | 내 확인 |
|---|---|---|---|
| `sim/ik/adapter.py:360` | **CRITICAL** | 위 D-0 | **직접 재현 확인** |
| `backend/safety_bringup/collision.py:225` | MEDIUM | 음수 충돌 마진이 0.0 확인 게이트를 우회한다 — `if requested_m == 0.0:` 만 막으므로 `-0.01` 은 경고 문자열만 남기고 통과하고, 실제 관통이 `ok=True` 가 된다 | 검증자가 실행 재현. **다만 심각도 정정 근거도 기록**: 저장소 내 모든 호출자가 `None` 또는 리터럴을 넘기고 CLI·YAML·HTTP·프론트 어디에도 이 값에 닿는 입력면이 없다 → 잠재 결함 |
| `sim/ik/adapter.py:375` | HIGH | IK 잔차 게이트(비수렴 solve의 유일한 탐지기)가 threshold `None` = 비활성이 기본이고, **저장소의 어떤 호출자도 무장시키지 않는다** | 미확인 — 후속 |
| `sim/dryrun/runner.py:170` | MEDIUM | 웨이포인트 0개에 대해 `run_trajectory` 가 통과 판정을 반환 → 인터록이 **검사한 적 없는 궤적**에 실송신을 무장 | 미확인 — 후속 |
| `sim/ik/limits.py:118` | HIGH(주장) | LeRobot 그리퍼 리밋이 양팔 `finger_joint1` 에 동일 적용되는데 자산은 좌우 반대 부호라는 주장 | **불확정** — 커밋된 MJCF는 양쪽 모두 `range=-10 10` 로 **대칭**이다. 이 근거로는 성립하지 않으며, 다른 자산(URDF·LeRobot 설정)을 봐야 한다 |
| `backend/actuation/enforcement.py:267` | LOW | `ActuationGateway._frames` 가 제어 경로에서 무한 증가하고 아무도 읽지 않는다 | 미확인 — 후속 |

재실행 감사는 12건을 제기해 **6 CONFIRMED / 1 UNCERTAIN / 5 REFUTED** 였다. 반증된 5건에는
"`permits_torque_on` 이 모터 타임아웃 부재와 루프 우위를 같은 True로 반환한다"(conf 88),
"`_read_joint_deg` 가 무응답 모터를 0.0°로 대체한다"(conf 88) 처럼 그럴듯한 것들이 포함된다.

### 확인되었으나 이번 세션에서 고치지 않은 것 (D-5 ~ D-11)

전부 감사가 CONFIRMED로 확정했고 검증자가 파일을 열어 재확인한 건이다. 고치지 않은 이유는 각각
다르며, **"작아 보여서"는 하나도 없다.**

**D-5 — `CollisionGuard.poll` 이 프로덕션에서 한 번도 호출되지 않아, 충돌 래치가 상수 False다. (HIGH)**
`backend/actuation/enforcement.py:191` 이 `collision_latched=self._guard.is_latched` 를 넘기고,
`is_latched` 는 `_latched` 를 반환하며, `_latched` 는 `guard.py:192` `_latch` 에서만 True가 되고
`_latch` 는 `guard.py:156-178` `poll` 에서만 도달 가능하다. 저장소 전체에서 `CollisionGuard.poll`
호출은 `tests/wp103`·`tests/wp2a05`·`tests/wp2d03` **뿐**이다. 프로덕션 생성 지점 두 곳
(`openarm_follower_oa.py:556`, `backend/freedrive/session.py:209`)은 guard를 게이트웨이에 넘기고
poll할 참조를 보관하지 않는다.

결과: `SafetyFilter._check_workspace_collision`(`safety.py:473`)이 항상 통과 분기를 타고,
`SafetyReason.COLLISION_LATCH` 는 도달 불가, `GuardCause` 의 네 fail-closed 사유
(`OBSERVATION_MISSING`/`BUS_READ_FAILED`/`LOCK_TIMEOUT`/`COLLISION_RESIDUAL`)는 **평가되지
않는다.** `12` FR-SAF-074 ②는 이들 각각이 즉시 래치할 것을 요구한다 — *"볼 수 없는 가드는 최악을
가정해야 하는 가드다."* 프리드라이브 중 CAN 읽기가 멎으면 게이트웨이는 명령을 통과시키고
`FreedriveSession.tick` 은 자기 독스트링이 약속한 `HoldCause.GATEWAY_HOLD` 에 도달하지 못한다.
예외도, 로그도, 트레이스도 없다.

**고치지 않은 이유**: 수정이 두 프로덕션 루프에 매 틱 `GuardSample` 을 만들어 `poll` 을 결선하는
일이고, `_latched` 를 되돌릴 `clear()` 도 없어 운영자 ack 경로와 함께 설계해야 한다. 실기 없이
검증할 수 없는 안전 결선이라 **정직하게 보류**한다(이 저장소의 기존 실기 보류 원칙과 같다).

**D-6 — `Robot.connect()` 가 CAN 락 없이 실제 소켓을 연다. (HIGH)**
`packages/lerobot_robot_openarm/openarm_follower_oa.py:326-341` 이
`if lock_manager is not None: guarded_connect(...)` / `else: self.bus.connect()` 이고,
`connect()`(:354)와 `BiOaOpenArmFollower.connect()`(:717) 모두 인자 없이 호출한다. 독스트링은
생략을 *"픽스처 경로(FakeDamiaoBus, 실제 소켓 없음)"* 로만 정당화하므로, **클래스 자신의 계약을
`else` 분기가 위반한다.** 기본 생성 시 `self.bus` 는 진짜 `DamiaoMotorsBus` 다. 프로덕션에서
매니저를 넘기는 곳은 `backend/rtbench/rig.py:50` 하나뿐이고 나머지는 전부 테스트다.
`docs/v1/spec/01-시스템-아키텍처.md:496` (FR-SYS-005)은 **모든 채널 락을 `Robot.connect()` 전에
획득하고, 못 하면 기동을 거부**하라고 명시한다.

검증자가 심각도를 critical→high로 정정한 근거도 기록해둔다: 서사에 나온 이중 writer 토크 간섭은
토크-ON을 필요로 하고, 토크-ON은 `backend/preflight/checks.py:156-192` `check_writer_lock` 이
따로 막는다. 확정된 결함은 **ABC 경로에서 락 없이 실소켓이 열린다**는 것이지 즉각적 이중 writer가
아니다.

**고치지 않은 이유**: 수정이 stock LeRobot 흐름 전체의 `connect()` 동작을 "연결"에서 "거부"로 바꾼다.
정상 경로를 하드웨어 없이 검증할 수 없고, 잘못 조이면 실기 브링업이 통째로 막힌다.

**D-7 — VR 소스 바인딩 게이트가 수신 경로에 없고, 있을 수도 없다. (MEDIUM)**
`backend/teleop/vr_udp/source.py:175` 는 `data, _ = sock.recvfrom(...)` 로 **송신자 주소를 버리고**,
`ingest(self, data, receive_mono_ns)`(:111)에는 host/port 파라미터가 없다. `constants.py:21` 은
`UDP_HOST_DEFAULT = "0.0.0.0"`. WP-5-08이 만든 `backend/security/vr_source_binding.py` 는
`backend/security/__init__.py` 재수출과 `tests/wp5_08` 외에 **참조가 없다**. 즉 UDP :5006에 도달
가능한 임의 호스트가 포즈를 주입하면 클러치 조정기가 그것을 운영자 포즈로 받고, 아무것도 거부하지
않으며 아무 카운터도 남지 않는다. `docs/v1/spec/14-시스템-운영.md:729` (FR-OPS-092)가 이 시나리오를
글자 그대로 적어두고 HMAC/DTLS 또는 페어링된 소스 바인딩을 요구한다.

**고치지 않은 이유**: `ingest` 시그니처를 바꿔 소스 주소를 관통시키고 `make_vr_pose_source` 가
레지스트리를 받도록 해야 하는데, 텔레옵 실기 경로의 동작 변경이라 실물 검증 없이 넣지 않는다.

**D-8 — 동결된 단위 경계표가 존재하지 않는 함수 3개를 가리킨다. (MEDIUM)**
`contracts/unit_tags.yaml:62,73,78` 이 rad/deg 교차의 유일한 합법 지점으로 선언한 네 곳 중 **세
개가 실존하지 않는 qualname** 이다(`to_openarm`/`ik_to_lerobot`/`can_to_gateway` — 저장소 전체
grep 결과 실재하는 것은 `sim/mujoco/sim_sync.py:66 lerobot_to_mjcf` 하나). 그리고
`contracts/units/checker.py` 의 `check_source` 는 **프로덕션 소스에 겨눠진 적이 없다** — 유일한
호출자가 `tests/wp0a04/test_checker.py:26` 이고 인라인 문자열에 하드코딩 allowlist를 쓴다. 실제
변환 지점은 약 16곳이다. 즉 **단일 교차점 불변식이 아무것에도 강제되지 않으면서, 동결 계약이
강제된다고 주장한다** — 리뷰어가 표를 읽고 "가드된다"고 결론내고 넘어가는 모양.

**고치지 않은 이유**: `CTR-UNIT@v1` 은 FROZEN이므로 표 수정은 `CTR-UNIT@v2` 이고, 그 전에 실제
16개 지점을 표와 대조해 **표를 넓힐지 교차점을 옮길지**를 정해야 한다. 이번 세션의 두 bump와 달리
내용 결정이 선행한다.

**D-9 — `CTR-ACT@v1` 은 동결 권위에 잠금이 없다. (MEDIUM)**
`ci_09.frozen_globs` 를 실제 코퍼스에 돌리면 CONTRACT_FROZEN 글롭을 가진 계약은 9개이고
**`CTR-ACT@v1` 은 그중에 없다** — 레지스트리가 `contracts/action_observation.yaml` 등을 EXCLUSIVE
로만 선언한다. `contract_index.json` 은 `CTR-ACT@v1` 을 `status: DRAFT`, `canonical_hash: null` 로
싣고, freeze ledger에도 없다. 그런데 `contracts/action/version.py:5-8` 과
`contracts/action_observation.yaml:21-25` 는 **"CI가 거부한다"고 주장한다.** 누군가
`channels[1].dim` 을 16→24로 바꾸고 같은 커밋에서 `frozen_digest` 를 재계산하면 전부 통과한다.

**고치지 않은 이유**: 해소는 레지스트리 레코드에 `CONTRACT_FROZEN` 글롭을 선언하고 FREEZE 이벤트를
기록하는 것 — 즉 §7과 같은 거버넌스 행위이고, 승인받은 범위(CAL·ERR) 밖이다.

**D-10 — `CI-16` 이 `06` §5.6이 요구하는 두 방향 중 한쪽만 구현한다. (HIGH)**
`registry/checks/ci_16.py:116` 의 `run()` 은 `for target in sorted(declared)` 로 **선언된 간선이
뒷받침되는지만** 묻는다. `06` §5.6 표의 1행(`downstream 누락` — 정적 그래프에서 실참조를 추출해
`downstream` 과 대조, 없으면 FAIL)에 해당하는 코드 경로가 **아예 없다.** 모듈 자신의 계약문
(:5)은 "두 방향이 실패한다"고 적고 있어 코드와 문서가 어긋난다. 검사기 자체 프리미티브로 재현하니
**모듈 수준 교차 패키지 import 간선 550개 중 439개가 소스 패키지의 `downstream[]` 에 없다.**
결과적으로 `WP-0A-01` 의 게이트가 뒤집혀도 `ops.cancel.executor.cancel_stage` 의 클로저가
`WP-2C-06`(detection_gate)을 stale로 표시하지 않는다 — 무효화된 근거 위에 안전 검출 패키지가 초록
판정을 유지한다.

**고치지 않은 이유**: 누락 방향을 켜면 **439건이 즉시 올라온다.** CI-07의 13건과 성격이 다르다 —
이쪽은 레지스트리 `downstream` 축을 대량 보정하는 작업이고, 어느 간선이 진짜 의존이고 어느 것이
우연한 import인지 판단이 필요하다. 별도 WP다.

**D-11 — 실재하지 않는 모듈을 기동하는 서비스 유닛.** §6.6 말미 참조.
`ops/acl/units/openarm-can-writer.service` 의 `ExecStart` 가 `backend.can.writer_service` 를
가리키는데 그 모듈은 없고 어떤 WP도 산출물로 선언하지 않는다. 설치되면 기동 실패한다.

**D-4 — `pip install .` 은 제품이 빠진 패키지를 만든다.** `[tool.setuptools.packages.find]` 가
`registry*`·`ops*` 만 포함하므로 `backend`·`contracts`·`sim`·`dashboard`·`packages` 는 어떤 배포본에도
없다. 테스트가 `backend` 를 import할 수 있는 건 `tests/__init__.py` 덕에 pytest가 저장소 루트를
prepend하기 때문이다. 아직 휠로 배포하지 않으므로 활성 결함이 아니라 **첫 배포에 장전된 함정**이다.

## 9. 검증

| 게이트 | 범위 | 결과 |
|---|---|---|
| `ruff check` | 파이썬 트리 11개 전량 | **통과** |
| `ruff format --check` | 파이썬 트리 11개 전량 | **통과** |
| `mypy` | `registry ops dashboard` | **157파일, 이슈 없음** |
| `registry.ingest.cli --check` | 코퍼스 → 레지스트리 | **1,216 레코드 · 177/177 · 스키마오류 0** |
| `registry.generate.cli --check` | 파생 182파일 | **전량 일치** |
| `registry.normalization.cli --check` | 원장 + 게이트맵 + 해시 | **스키마오류 0 · 위반 0 — GREEN** |
| `oa-contracts verify` | 동결 원장 해시 체인 | **검증됨** |
| `registry.check --all` | CI-01..CI-18, 35규칙 | **13 판정 finding — 의도적 FAILED**(§7.3). 시작 시점 3,665건 |
| `tsc --noEmit` | `frontend/` | 클린 |
| `eslint .` | `frontend/` | 오류 0, 기존 경고 1 |
| `vitest run` | `frontend/` | **157파일 787테스트 통과** |
| `pytest -q` | 전 스위트 | **exit 0** (시작 시점 exit 2 — 수집 단계 중단) |

## 10. 변경 파일

**새 동작** — `registry/__init__.py`(코퍼스 상수), `registry/env/upstream.py`(predicate 격리),
`registry/ingest/build.py`(계약 세대 파싱), `registry/checks/ci_09.py`(빈 글롭 = finding),
`registry/checks/__init__.py`(CI-07 해제), `backend/cartesian_jog/jog.py`(hold 시 sync),
`backend/calibration/schema.py`·`backend/gripper_endpoint/schema.py`(빈 체크섬 거부),
`ops/telemetry/mcap_writer.py`+`constants.py`(상한·죽음감지·close 계약),
`packages/lerobot_robot_openarm/openarm_follower_oa.py`(드롭 카운터 메타),
`.github/workflows/{ci,env}.yml`, `pyproject.toml`+`.pre-commit-config.yaml`(ruff 핀).

**새 테스트** — `tests/wp2d01/test_hold_leaves_no_drift.py`,
`tests/wpops05/test_mcap_writer_failure.py`, 그리고
`tests/{boot01/test_registry,env03/test_premerge_lint,wp102/test_schema,wp2a08/test_persistence,wp103/test_drop_counter}.py` 에 추가분.

**상수로 재배선(동작 무변화)** — `registry/checks/{corpus,ci_17,ci_11b_self,ci_01b}.py`,
`registry/checks/fixtures/{__init__,cases}.py`, `registry/ingest/cli.py`,
`registry/contracts/{catalog,cli}.py`, `registry/normalization/{loader,content_hash,gate_map,validator}.py`,
`registry/schema/traceability.schema.json`, 테스트 8개 모듈.

**거버넌스 기록** — `registry/contracts/freeze_ledger.yaml`(seq 10–13),
`docs/v1/plan/normalization/{ledger.yaml,normalization_hash}`, 코퍼스 선언 40곳.

**재생성(수기 편집 아님)** — `registry/traceability.yaml`, `registry/build/**`(182),
`registry/contracts/contract_index.json`.

## 11. 다음

0. 🔴 **D-0 (IK 어댑터 좌우 순서)가 최우선이다.** 안전 게이트가 각 팔을 반대편 리밋으로 검증하고
   있고, 왕복 상쇄 때문에 테스트가 전부 초록이다. 별도 WP로 착수하고, `joint_2` 의 비대칭 리밋을
   판별 수단으로 쓰는 테스트를 먼저 쓸 것.
1. **`CI-07` 의 13건이 게이트의 유일한 빨간불이다.** 각 건은 `ledger.yaml` 의 구조화된 판정 행 + 해시 재발행으로
   해소된다. 안전 3건(`NFR-SAF-001/002`, `FR-SAF-020/031`)이 먼저다 — 지금 이 코드들은 논쟁 중인
   요구사항의 한쪽 해석 위에 서 있고, 어느 쪽인지 아무 데도 적혀 있지 않다.
2. D-2(`openarm_control` 선언) — 해소 전까지 ENV `contract-regress` 는 초록이 될 수 없다.
3. D-1을 WP로 범위 설정: `--explicit-package-bases`, `stats` 모듈 충돌 해소, `type-arg` 아닌 38건 분류
   후 CI 단계 확장.
4. 중복 lint 잡 하나 삭제(D-3).
5. 첫 휠 빌드 전에 D-4.
