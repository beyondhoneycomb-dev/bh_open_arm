# bh_open_arm

OpenArm v2.0 양팔 로봇 기반 **피지컬 AI 토탈 플랫폼**. 하나의 웹 GUI에서 텔레오퍼레이션 → 데이터 수집 → 학습 → 추론 → 평가를 수행한다.

저장소는 명세·계획과 구현을 함께 담는다. 명세는 `docs/v1/spec/`, 실행 계획은 `docs/v1/plan/`, 코드는 `backend/`(런타임) · `contracts/`(경계 계약) · `sim/` · `ops/` · `frontend/`(웹 GUI) · `registry/`(계획 기계)에 있다. 세션별 구현 기록은 `docs/v1/work_log/`.

## 개발 환경 세팅

`uv` 하나로 끝난다. `uv.lock`이 모든 패키지의 버전을 못 박아두므로, 어느 기계에서 받아도 같은 환경이 만들어진다.

```bash
uv sync --extra dev --extra robot     # 파이썬 의존성 전부
cd frontend && npm ci && cd ..        # 웹 GUI 의존성
```

`--extra robot`이 없으면 `registry/`(계획 기계)만 도는 가벼운 환경이 된다 — `backend/`·`sim/`은 안 돌아간다.

### 런타임 버전

잠금 파일은 **패키지**를 못 박지만 그것을 실행하는 **런타임**은 못 박지 못한다. 그래서 따로 선언한다.

| 런타임 | 요구 | 어디에 선언돼 있나 |
|---|---|---|
| Python | `>=3.12` | `pyproject.toml:7` (`requires-python`) |
| Node.js | `^22.13.0 \|\| >=24` | `frontend/package.json` (`engines.node`) · `frontend/.nvmrc`(=24) |

Node 하한이 이 모양인 이유는 두 조건의 교집합이기 때문이다. 발명한 숫자가 아니다.

1. `frontend/package-lock.json`에서 가장 엄격한 `engines.node`가 `^20.19.0 || ^22.13.0 || >=24`다
   (`@eslint-community/eslint-utils`, `eslint-visitor-keys@5` 2건 — eslint·typescript-eslint의 전이 의존).
2. 그중 20 라인은 **2026-04-30에 지원이 끝났다**(`nodejs/Release` `schedule.json`). 끝난 라인은
   하한에 넣지 않는다. 22 Jod는 2027-04-30까지, 24 Krypton은 2028-04-30까지다.

`engines`는 `npm ci`를 **실패시키지 않는다** — 맞지 않으면 `EBADENGINE` 경고만 낸다
(`engine-strict`가 기본 `false`). 즉 이건 차단이 아니라 **선언**이다. 경고가 보이면 그 기계의
Node가 오래됐다는 뜻이고, 지금 당장 뭔가 깨졌다는 뜻은 아니다.

의존성 그룹은 세 개다.

| 그룹 | 무엇 | 왜 나눠져 있나 |
|---|---|---|
| (기본) | `pyyaml`, `jsonschema` | 계획 기계(`registry/`·`ops/`·`dashboard/`)가 쓰는 전부. 이 셋은 `numpy`조차 import하지 않는다 |
| `dev` | `pytest`, `ruff`, `mypy` | 검사 도구 |
| `robot` | `lerobot`, `openarm_control`, `numpy`, `mujoco`, `mink`, `pyarrow`, `opencv`, … | `backend/`·`sim/`·`packages/`가 쓰는 실행 스택 |

**의존성을 추가할 때**: `pyproject.toml`에 적고 `uv lock`을 돌린다. 적지 않고 import하면
`python -m registry.env.declared_imports`가 잡는다 — 선언 없는 import는 그것을 우연히 가진 기계에서만
돌아가고 다른 곳에서는 import 오류가 된다.

## 검사 돌리기

```bash
./scripts/gates.sh        # 게이트 전부 (13종). 판정은 종료 코드로 한다
```

호스팅 CI는 없다 — 연구개발 단계라 유지 비용이 값어치를 넘어서 제거했다(`docs/v1/plan/02a` WP-ENV-03).
그래서 `scripts/gates.sh`의 목록이 곧 계약이다: **거기 없는 검사는 아무도 돌리지 않는다.**

## 문서

- **[docs/v1/spec/](docs/v1/spec/)** — 기능 명세서 (18개 문서, 요구사항 ~1,159개). *무엇을 할 수 있어야 하는가.* 시작점은 [docs/v1/spec/README.md](docs/v1/spec/README.md).
- **[docs/v1/plan/](docs/v1/plan/)** — 실행 계획 (10개 문서, WP 177 · 게이트 `PG-*` 14 · 계약 `CTR-*` 13). *어떤 순서로·무엇을 먼저.* 시작점은 [docs/v1/plan/00-실행계획-개요.md](docs/v1/plan/00-실행계획-개요.md) (§9.1에 읽는 순서).
- **[docs/v1/reviews/](docs/v1/reviews/)** — 명세·계획 심층 검토 기록.
- **[docs/background_source/](docs/background_source/)** — 참고 자료 (대용량 바이너리는 미포함, 취득 안내만).

## 확정된 아키텍처 (요약)

| 항목 | 값 |
|---|---|
| 대상 로봇 | OpenArm v2.0 (양팔, 팔당 7-DOF + 그리퍼) |
| 런타임 | LeRobot **v0.6.0** (OpenArm = 1급 로봇). commit SHA로 핀 — `pyproject.toml:28`이 자칭하는 `0.6.1`은 PyPI·git 태그가 없는 **유령 버전**이므로 인용 금지 |
| GUI | 웹 SPA + 헤드리스 FastAPI 백엔드 (단일 WebSocket + REST), 3D = Three.js + urdf-loader |
| 텔레옵 입력 | Meta Quest 3S VR / OpenArm KER (리더암) |
| 원격 추론 | LeRobot async PolicyServer (gRPC :8080) |

세부와 미해결 결정은 [docs/v1/spec/16-미해결-이슈.md](docs/v1/spec/16-미해결-이슈.md) 참조.
