# 출처 필요 시 읽기 배포

## 상태

배포 성공. GitHub Actions의 여섯 작업이 모두 성공했으며, 배포 후 실제 이미지와
서비스 상태를 별도로 확인했다.

- 배포 소스: `d3cb8d99628c883b2549a8dfa6b0c2371664cc9d`
- 실행: [40284643751](https://github.com/hi-space/open-canvas-bedrock/actions/runs/40284643751)
- 실행 시작: `2026-10-26T07:15:05Z`
- 실행 완료: `2026-10-26T07:24:23Z`
- 독립 운영 검증: `2026-10-26T07:25:28Z`

이 배포 결과를 기록하는 후속 문서 커밋은 `[skip ci]`를 사용한다. 애플리케이션
이미지를 만든 소스는 위 `d3cb8d9`이며 문서 기록 때문에 재배포하지 않는다.

## 변경

- 프로젝트 출처 보관량과 요청별 읽기 예산 분리.
- 일반 에이전트의 전체 발췌 사전 입력 제거, 목록·검색·구간 읽기 도구 추가.
- 딥리서치의 질문별 출처 조회, 후속 구간 읽기, 웹/보관 근거 동시 보존.
- 출처 패널의 발췌 필요 시 조회와 검색·나눠 보기.
- 모델 예산과 별개의 보관 상한 및 사용하지 않는 복사본 정리. 작업·수정안이
  참조하는 버전은 유지하고, 저장 한도가 차도 작업 실행은 계속 허용.
- 기존 인라인 출처는 롤백 호환용으로 유지하며, 읽기 전용 런타임의 권한 변경 없음.

구현 설명은 [필요한 출처만 읽기](../on-demand-sources.md),
테스트·브라우저 근거는 [검증 기록](../verification/on-demand-sources/README.md)에 있다.

## 배포 전 검증

- 백엔드 417개 테스트 및 101개 하위 테스트.
- 웹 225개 테스트, 타입 검사, 린트 오류 없음, 프로덕션 빌드.
- 배포 스크립트 26개 테스트 및 18개 하위 테스트.
- 실제 Chromium에서 출처 67개를 둔 상태로 기존 문서 보강·승인과 HTML/SVG
  리서치·승인·다운로드 완료. 초기 모델 입력 137자, 선택한 근거 읽기 93자.
- 운영 DynamoDB에서 존재하지 않는 임의 검증 namespace를 읽어 실제 조회
  형식을 확인했다. 읽은 사용자 기록과 쓴 기록 모두 0개.

모델과 검색 응답은 로컬 검증용으로 고정했다. 운영 계정으로 유료 모델 호출이나
사용자 문서 변경을 수행한 결과가 아니다.

## 배포 전 운영 상태

- 이전 소스: `d4bface90db6baf7248259b692ce5b74720ee5d2`
- ECS 태스크 정의: revision `21`
- AgentCore 런타임 및 DEFAULT 엔드포인트: version `8`, READY
- `HtmlCanvasStack`, `CanvasWorkspaceStack`: UPDATE_COMPLETE
- [배포 전 스냅샷](2026-10-26-on-demand-sources-before.json)

## 배포 후 운영 검증

- 두 CloudFormation 스택 모두 `UPDATE_COMPLETE`.
- ECS 태스크 정의 revision `22`, 배포 상태 `COMPLETED`, 실행 1개·대기 0개.
- 웹·API 컨테이너 모두 `RUNNING` / `HEALTHY`; ALB 대상 `healthy`.
- 실행 컨테이너의 이미지 URI와 실제 digest가 빌드 산출물과 일치.
- AgentCore 런타임 및 DEFAULT 엔드포인트 `READY`, 실제 제공 버전 `9`.
- 런타임 idle timeout 60초 / 최대 수명 900초 유지.
- `/`, `/api/workspaces`의 비로그인 접근이 Cognito 로그인으로 이동.
- 이전 태스크 revision `21`은 `ACTIVE`로 남아 있으며 롤백은 발생하지 않았다.

| 이미지 | SHA-256 digest |
| --- | --- |
| 웹 | `80faf7bf5722d2e81c3d435d40d907ec7a3000f969f55cbab81e9ab2d99b446b` |
| API | `6de5250ac83e2af462f40961aecb4002ba72d25c8f50d97ea988af601d6cf1d7` |
| AgentCore ARM64 | `2332ab9f00fb4b30d601754a244939c0dbd8164da26311417d6f3874c0b0050c` |

- [배포 후 스냅샷](2026-10-26-on-demand-sources-after.json)
- [소스·이미지 manifest](releases/2026-10-26-on-demand-sources/manifest.json)
- [워크플로 결과](releases/2026-10-26-on-demand-sources/workflow.json)
- [배포 로그](releases/2026-10-26-on-demand-sources/release-log.txt)
- [독립 검증 로그](releases/2026-10-26-on-demand-sources/live-verification.txt)
