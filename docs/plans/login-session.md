# 로그인 세션 유지 개선

## 확인한 상태

- 사용자는 배포 후 또는 새로고침할 때 로그인이 풀리는 현상을 보고했다.
- 운영 HTTPS ALB 인증 설정의 `SessionTimeout`은 3,600초였다.
- Cognito 앱 클라이언트는 2026-10-25 이후 변경되지 않았으며 refresh token
  유효기간은 30일이다. 최근 애플리케이션 배포는 인증 리소스를 변경하지 않았다.
- 확인한 최근 3시간 앱 로그에는 실제 HTTP 401 실패가 없었다.
- AWS 문서상 ALB는 세션 만료 시 재인증을 요구한다. 세션이 액세스 토큰보다
  오래 유지되고 IdP가 갱신 토큰을 지원하면 액세스 토큰을 자동 갱신한다.

이 설정은 장시간 사용한 뒤 새로고침하면서 로그인 화면으로 이동하는 현상을
설명한다. 브라우저의 쿠키 삭제 등 다른 원인을 모두 재현해 배제한 것은 아니다.

## 변경

- [x] 로그인 세션을 604,800초(7일)로 설정한다.
- [x] 앱 클라이언트, 쿠키 이름, 로그인 필수 설정, OAuth scope와 라우팅을 보존한다.
- [x] 최초 배포 템플릿과 일반 릴리스가 같은 세션 설정을 사용한다.
- [x] 릴리스 검증은 리스너 변경 중 세션 시간만 허용한다.
- [x] 후속 이미지 배포가 이미 설정된 인증 리스너를 다시 변경하지 않는지 검사한다.
- [x] 운영 템플릿을 읽은 변경 미리보기에서 리스너의 세션 시간만 달라짐을 확인한다.
- [x] 독립 코드 검토. 인증 보존·라우팅 제한·롤백에 중요한 문제 없음.
- [x] CloudFormation의 숫자 문자열도 처리하고 이미 올바른 설정은 다시 쓰지 않음.
- [ ] GitHub Actions 배포 및 실제 리스너 설정 확인.

확인된 1시간 제한을 수정하는 작은 설정 변경이다. 토큰 유효기간 연장,
클라이언트 재생성, 사용자 데이터 변경, 로그인 우회는 포함하지 않는다.
이미 만료된 세션은 복구되지 않으며 새로 로그인할 때 새 정책이 적용된다.

## 검증

`cd deploy && ../apps/backend/.venv/bin/python -m pytest -q test_release.py agentcore`

30개 테스트 및 23개 하위 테스트 통과. 자세한 결과는
[검증 로그](../verification/login-session/deploy-tests.txt)와
[배포 전 설정](../deployment/2026-10-26-login-session-before.json)에 보관한다.

## 공식 근거

- [ALB 인증 세션 만료와 갱신 동작](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html)
- [CloudFormation 인증 세션 설정](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-elasticloadbalancingv2-listener-authenticatecognitoconfig.html)
