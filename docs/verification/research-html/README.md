# 리서치 HTML 검증 자료

이 폴더에는 프로젝트의 리서치 HTML·SVG 검증 결과를 보관합니다. 예시의 모델과
웹 검색 응답은 테스트 데이터이며, 실제 그래프·API·저장·승인·브라우저 렌더링을
사용합니다. 화면에 나온 수치를 실측 연구 결과로 해석하지 마세요.

## 예시

- [네이티브 HTML 보고서](native-report.html): HTML 계층도와 SVG 흐름도
- [넓은 시퀀스 HTML](wide-sequence.html): 여섯 참여자의 글자 크기와 가로 탐색
- [데스크톱 보고서](native-desktop.png)
- [모바일 보고서](native-mobile.png)
- [시퀀스 모바일](wide-sequence-mobile.png)
- [작업실 미리보기](native-preview.png)
- [네이티브 브라우저 검증 결과](native-results.json)
- [PNG 보고서](png-report.html)와 [PNG 검증 결과](png-results.json)
- [넓은 보기·모바일 레이아웃 결과](../html-layout/results.json)
- [테스트·빌드 실행 로그](logs/)

기본 검증은 생성 → 승인 전 미리보기 → SVG 전체 선택 → 승인 → 오프라인
다운로드를 포함합니다. 네이티브 경로에서 PNG 생성과 이미지 요청이 없는지,
넓은 SVG의 글자가 박스 안에 있는지, 키보드로 가로 탐색이 가능한지도 확인합니다.

전문 스킬의 PNG 경로는 별도로 검증하며, 손상된 PNG 안내·다운로드 차단·재시도·
오프라인 이미지 내장을 확인합니다.

## 재현

백엔드 테스트:

```bash
cd apps/backend
.venv/bin/python -m pytest -q
```

프런트엔드 테스트:

```bash
cd apps/web
yarn test
yarn typecheck
yarn lint
```

브라우저 검증은 `apps/web/tests/research_html_backend.py`의 로컬 전용 응답을
사용합니다. `NATIVE_HTML_DIAGRAMS_ONLY=1`은 스킬 없는 네이티브 경로입니다.
`research_html_smoke.py`와 `native_html_diagrams_smoke.py`의 기본 결과 위치는
이 폴더이며, `OPEN_CANVAS_TEST_ARTIFACTS`로 명시적으로 변경할 수 있습니다.

실제 운영 배포 결과는 [배포 기록](../../deployment/2026-10-26-research-html.md)에
배포 SHA와 이미지 digest, 서비스 상태를 구분해 기록합니다.
