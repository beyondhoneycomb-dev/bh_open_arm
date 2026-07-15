# bh_open_arm

OpenArm v2.0 양팔 로봇 기반 **피지컬 AI 토탈 플랫폼**. 하나의 웹 GUI에서 텔레오퍼레이션 → 데이터 수집 → 학습 → 추론 → 평가를 수행한다.

현재 저장소는 **기능 명세** 단계다. 코드는 아직 없다.

## 문서

- **[docs/spec/](docs/spec/)** — 기능 명세서 (18개 문서, 요구사항 ~1,159개). 시작점은 [docs/spec/README.md](docs/spec/README.md).
- **[docs/background_source/](docs/background_source/)** — 참고 자료 (대용량 바이너리는 미포함, 취득 안내만).

## 확정된 아키텍처 (요약)

| 항목 | 값 |
|---|---|
| 대상 로봇 | OpenArm v2.0 (양팔, 팔당 7-DOF + 그리퍼) |
| 런타임 | LeRobot v0.6.1 (OpenArm = 1급 로봇) |
| GUI | 웹 SPA + 헤드리스 FastAPI 백엔드 (단일 WebSocket + REST), 3D = Three.js + urdf-loader |
| 텔레옵 입력 | Meta Quest 3S VR / OpenArm KER (리더암) |
| 원격 추론 | LeRobot async PolicyServer (gRPC :8080) |

세부와 미해결 결정은 [docs/spec/16-미해결-이슈.md](docs/spec/16-미해결-이슈.md) 참조.
