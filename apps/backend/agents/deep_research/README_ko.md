# Deep Research Graph

주제를 여러 라운드에 걸쳐 조사한 뒤, 선택한 장르(논문, 블로그, LinkedIn)에 맞춰 근거와 그림을 갖춘 문서를 작성하는 서브그래프입니다.

## 그래프 구조

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	planResearch(planResearch)
	searchSources(searchSources)
	extractFindings(extractFindings)
	prepareFollowups(prepareFollowups)
	buildOutline(buildOutline)
	createDiagrams(createDiagrams)
	draftSections(draftSections)
	reviewDraft(reviewDraft)
	generateArtifact(generateArtifact)
	__end__([<p>__end__</p>]):::last
	__start__ --> planResearch;
	buildOutline --> createDiagrams;
	createDiagrams --> draftSections;
	draftSections --> reviewDraft;
	extractFindings -.-> buildOutline;
	extractFindings -.-> prepareFollowups;
	planResearch --> searchSources;
	prepareFollowups --> searchSources;
	reviewDraft --> generateArtifact;
	searchSources --> extractFindings;
	generateArtifact --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## 노드 설명

- **planResearch**: 장르에 맞는 수의 하위 질문과 검색 쿼리로 리서치 브리프(독자, 주장, 언어)를 만듭니다.
- **searchSources**: Tavily `advanced` 검색으로 페이지 원문(markdown)까지 가져오고, URL 기준으로 중복을 제거해 출처를 `S1..Sn`으로 등록합니다.
- **extractFindings**: 하위 질문마다 병렬로 출처를 읽어 근거(주장, 수치, 인용, 출처 id, 신뢰도)와 남은 공백, 후속 쿼리를 뽑습니다. 읽지 않은 출처를 가리키는 근거는 버립니다.
- **prepareFollowups**: 공백이 남아 있고 장르의 라운드 한도가 남았으면 후속 쿼리를 정리해 다음 라운드로 보냅니다(`should_continue_research`).
- **buildOutline**: 장르 가이드에 맞춰 섹션별 목표, 핵심 포인트, 사용할 근거, 분량, 그림 요청을 계획합니다.
- **createDiagrams**: AWS 아키텍처는 aws-drawio-diagram 스킬의 스크립트(brief, 자동 배치, 검증, drawio PNG 내보내기)로, 개념도는 aws-diagram-design의 `awsdiag.Canvas`와 헤드리스 Chrome으로 렌더링합니다. 검증을 통과하지 못한 그림은 건너뜁니다.
- **draftSections**: 섹션 초안을 병렬로 씁니다. 배정된 근거의 `[S#]`만 인용할 수 있습니다.
- **reviewDraft**: 깊이, 논증, 근거, 중복, 장르 적합성을 기준으로 섹션별 수정 지시를 만듭니다.
- **generateArtifact**: 섹션을 순서대로 최종 수정해 캔버스로 스트리밍하고, 인용을 번호 링크로 바꾸고 그림과 참고문헌을 붙여 최종 문서를 반환합니다.

## 장르 프로필 (`genres.py`)

| 장르 | 하위 질문 | 최대 라운드 | 최대 출처 | 분량 | 그림 | 인용 |
|---|---|---|---|---|---|---|
| paper | 6-8 | 3 | 60 | 5,000-8,000 단어 | 최대 3 | 번호 + 참고문헌 |
| blog | 4-6 | 2 | 40 | 2,200-3,800 단어 | 최대 2 | 번호 + 참고 자료 |
| linkedin | 2-3 | 1 | 16 | 짧은 포스트 | 최대 1 | 본문 링크 1-3개 |

LinkedIn은 `~/.claude/skills/linkedin-writer/references/style-guide.md`(또는 `LINKEDIN_STYLE_GUIDE_PATH`)가 있으면 그 문체를 따릅니다.

## 필요 조건

- `TAVILY_API_KEY` (없으면 명시적인 오류로 중단합니다)
- 그림: `drawio` CLI(+ `xvfb-run`), Google Chrome, Claude Code 플러그인 aws-drawio-diagram, aws-diagram-design. 없으면 그림 없이 작성합니다.
- 그림 파일은 `data/research_assets/<runId>/`에 저장되고 `GET /api/research/assets/<runId>/<file>.png`로 제공됩니다.

## 사용 위치

`open_canvas` 메인 그래프의 `deepResearch` 노드에서 호출됩니다. 요청에 `researchGenre`가 있으면 `generatePath`가 이 경로로 보냅니다(컴포저의 딥 리서치 버튼).
