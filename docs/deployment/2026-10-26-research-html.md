# 리서치 HTML·SVG 배포 — 2026-10-26

상태: **운영 배포 성공**. 2026-10-26 00:10:41 UTC에 파이프라인이 완료됐고,
00:11:04 UTC에 운영 상태를 별도로 확인했습니다.

## 배포 범위

- 선택한 프로젝트 자료를 활용하는 딥리서치 HTML.
- 네이티브 HTML/CSS 계층도와 SVG 흐름·시퀀스, 선택적 전문 스킬.
- SVG 전체 선택·수정, 출처·도식 보존과 오프라인 다운로드.
- 원격 `main`의 HTML 넓은 보기 변경을 함께 통합.
- 설계·계획·검증 자료를 프로젝트 `docs/` 안으로 정리.

## 실행 경로

원래 프로젝트의 `main`을 원격 저장소에 푸시하고
`.github/workflows/deploy.yml`의 **Test and deploy**로 배포했습니다.
대상은 `canvas.hi-yoo.com`, 리전 `ap-northeast-2`의 기존
`HtmlCanvasStack`과 `CanvasWorkspaceStack`입니다.

- 배포 소스: `53c3ac82965cd34dc4f7addf550dc38c859bca8a`.
- GitHub Actions 실행: [40247301060](https://github.com/hi-space/open-canvas-bedrock/actions/runs/40247301060).
- 실행 결과: 백엔드·프런트엔드 테스트, 세 이미지 빌드·업로드, 배포 모두 `success`.
- 실행 시간: `2026-10-26T00:00:55Z` → `2026-10-26T00:10:41Z`.
- [워크플로 결과](releases/2026-10-26-research-html/workflow.json)와
  [배포 로그](releases/2026-10-26-research-html/release-log.txt).

이 결과 기록은 배포 후 문서 전용 커밋으로 추가합니다. 그 커밋의 `[skip ci]`는
동일한 애플리케이션을 다시 배포하지 않기 위한 것이며, 운영 소스 SHA는 위와 같습니다.

## 운영 확인 결과

- 두 CloudFormation 스택 모두 `UPDATE_COMPLETE`.
- ECS task definition `HtmlCanvasStackTaskDef2E995DD4:20`, rollout `COMPLETED`.
- 실행 1개·대기 0개. frontend(`app`)와 backend 컨테이너 모두 `HEALTHY`.
- ALB 대상 `healthy`.
- AgentCore 런타임 `canvas_writing_workspace-GKTOJW3k5H`: 버전 `7`, `READY`.
  `DEFAULT` 엔드포인트도 `READY`이며 실제 서비스 버전은 `7`.
- 최대 세션 수명 900초, 유휴 세션 제한 60초.
- 운영 이미지 세 개가 파이프라인에서 생성한 digest와 일치.
- 비로그인 HTTPS 요청 `/`, `/api/workspaces`가 Cognito 로그인으로 리다이렉트됨.

[배포 후 AWS 상태](2026-10-26-research-html-after.json)와
[독립 실행한 운영 검증 로그](releases/2026-10-26-research-html/live-verification.txt)를
보관합니다. 실제 모델·검색을 호출하는 로그인 사용자 시나리오는 이번 배포에서
다시 실행하지 않았습니다. 기능 검증 범위는 아래 로컬 브라우저 검증을 따릅니다.

## 배포 이미지

ECR 저장소:
`913524902871.dkr.ecr.ap-northeast-2.amazonaws.com/cdk-hnb659fds-container-assets-913524902871-ap-northeast-2`.

| 이미지 | Digest |
| --- | --- |
| frontend | `sha256:6ec1abbb8d3dc5fa65b2d1d279a7a9681eae125ef6a397fdc8d0b72543ef1523` |
| backend | `sha256:f7d0cbb6324f54a219d91d4a7618d069a8253f942a670f4715372cc08370319a` |
| ARM64 agent | `sha256:1061686fe67d798c6cf1d9db57b038881d4acbf411a65edeba0bdcbd97794724` |

전체 이미지 URI와 소스 커밋은
[이미지 명세](releases/2026-10-26-research-html/manifest.json)에 있습니다.

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

## 롤백 기준

직전 ECS task definition `:19`는 `ACTIVE` 상태로 남아 있습니다.
직전 frontend/backend/agent 이미지와 AgentCore 버전 `6`은
[배포 전 상태](2026-10-26-research-html-before.json)에 기록했습니다.
파이프라인은 배포 검증 실패 시 이전 이미지로 되돌리도록 구성되어 있으며,
이번 실행에서는 롤백이 발생하지 않았습니다.
