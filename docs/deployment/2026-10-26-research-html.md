# 리서치 HTML·SVG 배포 — 2026-10-26

상태: 로컬 통합 검증 완료. `main` 푸시 후 자동 배포 결과를 확인합니다.

## 배포 범위

- 선택한 프로젝트 자료를 활용하는 딥리서치 HTML.
- 네이티브 HTML/CSS 계층도와 SVG 흐름·시퀀스, 선택적 전문 스킬.
- SVG 전체 선택·수정, 출처·도식 보존과 오프라인 다운로드.
- 원격 `main`의 HTML 넓은 보기 변경을 함께 통합.
- 설계·계획·검증 자료를 프로젝트 `docs/` 안으로 정리.

## 실행 경로

원래 프로젝트의 `main`을 원격 저장소에 푸시하고
`.github/workflows/deploy.yml`의 **Test and deploy**로 배포합니다.
대상은 `canvas.hi-yoo.com`, 리전 `ap-northeast-2`의 기존
`HtmlCanvasStack`과 `CanvasWorkspaceStack`입니다.

파이프라인은 테스트 후 frontend/backend/ARM64 agent 이미지를 만들고,
이미지 digest를 사용해 배포합니다. 완료 후 ECS 서비스, ALB 대상 상태,
AgentCore 런타임과 Cognito 로그인 보호를 확인합니다.

배포 완료 시 이 문서에 실제 커밋, 실행 번호, digest와 확인 결과를 기록합니다.

## 배포 전 확인

- 원래 프로젝트 `main`에 기능 브랜치와 원격 `main`의 HTML 넓은 보기를 통합했습니다.
- 백엔드 390개 테스트와 101개 하위 검증, 프런트엔드 221개 테스트를 통과했습니다.
- 배포 스크립트 26개 테스트와 18개 하위 검증, 타입 검사, 린트, 프로덕션 빌드를 통과했습니다.
- 네이티브 HTML/SVG, 전문 스킬의 PNG, HTML 넓은 보기 브라우저 검증을 통과했습니다.
- 모델·검색 응답은 로컬 검증에서 테스트 응답으로 대체했습니다.
- [배포 전 AWS 상태](2026-10-26-research-html-before.json): 두 스택 `UPDATE_COMPLETE`,
  ECS task definition `:19`, 실행 1개·대기 0개, ALB 대상 `healthy`,
  AgentCore 버전 `6` / `READY`.

[검증 자료](../verification/research-html/README.md)와
[넓은 보기 검사 결과](../verification/html-layout/results.json)를 프로젝트 안에 보관합니다.
