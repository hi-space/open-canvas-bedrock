# 로그인 유지 시간 개선

## 확인한 원인과 범위

운영 ALB의 로그인 세션이 **3,600초(1시간)**로 설정되어 있었다. 긴 작업 후
새로고침하거나 다시 요청하면 이 세션이 만료되어 로그인 화면으로 이동할 수 있다.
최근 애플리케이션 배포는 Cognito 클라이언트나 인증 쿠키 설정을 바꾸지 않았다.
확인한 최근 앱 로그에서도 HTTP 401 실패가 관찰되지 않았다.

이 설정 문제는 확인했지만 사용자 브라우저의 모든 로그아웃 원인을 재현한 것은
아니다. 쿠키가 삭제되는 경우와 관리자에 의한 세션 해제 등은 별개다.

## 변경

- 로그인 세션 최대 유지 시간을 **604,800초(7일)**로 설정한다.
- Cognito 앱 클라이언트, 인증 쿠키 이름, 로그인 필수 설정과 라우팅을 보존한다.
- 액세스·ID·갱신 토큰의 기존 유효기간은 변경하지 않는다. ALB는 로그인 세션
  안에서 기존 갱신 토큰으로 액세스 토큰을 갱신한다.
- 이미지 배포 시 이미 설정된 세션 시간을 다시 쓰지 않는다.
- 릴리스에서는 인증 리스너의 세션 시간 이외 속성 변경을 거부한다.
- 최초 설정 스크립트도 같은 7일 값을 사용한다.

이미 만료된 세션은 다시 로그인해야 한다. 새로 로그인하면 새 정책이 적용된다.

## 검증

- 배포 코드 테스트 30개와 하위 테스트 23개 통과.
- 실서비스 템플릿으로 실행한 변경 미리보기는 `AlbHttpsB7CA700A`의
  `SessionTimeout`만 바꾸며 쿠키·클라이언트·라우팅을 그대로 보존한다.
- 독립 코드 검토 통과. CloudFormation 숫자 문자열 표현도 회귀 검증에 포함했다.
- [배포 전 실제 설정과 변경 미리보기](2026-10-26-login-session-before.json)
- [테스트 결과](../verification/login-session/deploy-tests.txt)
- [설계·작업 기록](../plans/login-session.md)

## 배포 상태

코드 검증 완료. 기존 GitHub Actions 경로로 배포한 뒤 실제 리스너와 Cognito
클라이언트 설정을 비교해 결과를 기록한다.

## 공식 근거

- [ALB 인증 세션과 갱신](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/listener-authenticate-users.html)
- [인증 세션 설정과 기본 7일 값](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/aws-properties-elasticloadbalancingv2-listener-authenticatecognitoconfig.html)
