# Open Canvas Agents - FastAPI with AWS Bedrock

Open Canvas 에이전트의 Python FastAPI 구현체로, AWS Bedrock을 사용한 LLM 통합을 제공합니다.

## 개요

이 프로젝트는 LangGraph를 사용하여 구현된 여러 AI 에이전트들을 FastAPI로 제공하는 서버입니다. 주요 기능은 다음과 같습니다:

- **Open Canvas Agent**: 대화 기반 아티팩트 생성 및 수정을 위한 메인 에이전트
- **Reflection Agent**: 대화와 아티팩트에 대한 반성 및 피드백 생성
- **Thread Title Agent**: 대화 스레드의 제목 자동 생성
- **Summarizer Agent**: 긴 대화 내용 요약
- **Web Search Agent**: 웹 검색 기능 통합
- **Threads Management**: LangGraph SDK 호환 스레드 관리
- **Assistants Management**: LangGraph SDK 호환 어시스턴트 관리
- **Store Management**: LangGraph SDK 호환 스토어 관리

## 기술 스택

- **FastAPI**: 웹 프레임워크
- **LangGraph**: 상태 머신 및 에이전트 오케스트레이션
- **LangChain**: LLM 통합 및 메시지 처리
- **AWS Bedrock**: LLM 제공자
- **Tavily**: 웹 검색 (선택사항)
- **Pydantic**: 데이터 검증
- **Uvicorn**: ASGI 서버

## 모델 설정

### 지원 모델

AWS Bedrock 모델만 지원됩니다. 주요 지원 모델:

- Claude Haiku 4.5, Sonnet 4, Sonnet 4.5, Opus 4.1
- Amazon Nova Premier, Pro, Micro, Lite
- Llama 3.3 70B Instruct
- DeepSeek R1, V3

전체 모델 목록은 `models.py`를 참조하세요.

### 모델 설정

모델 설정은 요청의 `config` 필드를 통해 전달됩니다. 모델 이름, 온도, 최대 토큰 수 등을 설정할 수 있습니다. 상세한 설정 구조는 `/docs`에서 확인할 수 있습니다.

## 프로젝트 구조

```
apps/agents/
├── main.py                 # FastAPI 애플리케이션 진입점
├── bedrock_client.py       # AWS Bedrock 클라이언트 래퍼
├── models.py               # 지원 모델 정의
├── utils.py                # 유틸리티 함수
├── requirements.txt        # Python 의존성
│
├── open_canvas/           # Open Canvas 메인 에이전트
│   ├── graph.py           # LangGraph 그래프 정의
│   ├── state.py           # 상태 정의
│   ├── routes.py          # FastAPI 라우트
│   ├── generate_path.py  # 경로 생성 로직
│   ├── prompts.py         # 프롬프트 정의
│   └── rewrite_artifact_utils.py  # 아티팩트 재작성 유틸리티
│
├── reflection/            # 반성 에이전트
│   ├── graph.py
│   ├── state.py
│   ├── routes.py
│   └── prompts.py
│
├── thread_title/          # 스레드 제목 생성 에이전트
│   ├── graph.py
│   ├── state.py
│   ├── routes.py
│   └── prompts.py
│
├── summarizer/            # 요약 에이전트
│   ├── graph.py
│   ├── state.py
│   └── routes.py
│
├── web_search/            # 웹 검색 에이전트
│   ├── graph.py
│   ├── state.py
│   └── routes.py
│
├── threads/               # 스레드 관리
│   ├── routes.py
│   └── store.py
│
├── assistants/            # 어시스턴트 관리
│   ├── routes.py
│   └── store.py
│
└── store/                 # 스토어 관리
    ├── routes.py
    └── store.py
```

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

환경 변수를 직접 설정하거나 `.env` 파일을 생성할 수 있습니다:

```
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
TAVILY_API_KEY=your_tavily_api_key
PORT=8000

# LangSmith 트레이싱 (선택사항)
LANGCHAIN_API_KEY=your_langsmith_api_key
LANGCHAIN_TRACING_V2=true
LANGSMITH_ENDPOINT=https://api.smith.langchain.com
LANGSMITH_PROJECT=your_project_name
```

### 3. 서버 실행

```bash
python main.py
```

또는 uvicorn을 직접 사용:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API 엔드포인트

### API 문서

서버 실행 후 다음 URL에서 자동 생성된 API 문서를 확인할 수 있습니다:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Health Check

- **GET** `/health` - 서버 상태 확인

### Open Canvas Agent

- **POST** `/api/agent/stream` - Open Canvas 에이전트 실행 (스트리밍)
  - Server-Sent Events (SSE) 형식으로 실시간 이벤트 스트리밍
  - 대화 메시지와 아티팩트를 받아 적절한 작업 수행
  - 아티팩트 생성, 수정, 재작성, 웹 검색 등 다양한 작업 지원

### Reflection Agent

- **POST** `/api/reflection/reflect` - 대화와 아티팩트에 대한 반성 실행
  - 대화 내용과 생성된 아티팩트를 분석하여 스타일 규칙과 사용자 메모리 생성
  - 생성된 반성 결과를 스토어에 저장하여 향후 대화에 활용

### Thread Title Agent

- **POST** `/api/thread-title/generate` - 대화 스레드 제목 생성
  - 대화 내용과 아티팩트를 기반으로 적절한 제목 자동 생성
  - 스레드 메타데이터 업데이트 지원

### Summarizer Agent

- **POST** `/api/summarizer/summarize` - 대화 내용 요약
  - 긴 대화 내용을 요약하여 메시지 길이 관리
  - 요약된 내용을 새로운 메시지로 변환하여 대화 히스토리 최적화

### Web Search Agent

- **POST** `/api/web-search/search` - 웹 검색 수행
  - 사용자 메시지를 분석하여 웹 검색 필요 여부 판단
  - 필요시 검색 쿼리 생성 및 Tavily API를 통한 웹 검색 수행

### Threads Management

- **POST** `/threads` - 새 스레드 생성
- **GET** `/threads/{thread_id}` - 스레드 조회
- **POST** `/threads/search` - 스레드 검색
- **DELETE** `/threads/{thread_id}` - 스레드 삭제
- **POST** `/threads/{thread_id}/state` - 스레드 상태 업데이트 (LangGraph SDK 호환)

### Assistants Management

- **POST** `/assistants` - 새 어시스턴트 생성
- **GET** `/assistants/{assistant_id}` - 어시스턴트 조회
- **PUT/PATCH** `/assistants/{assistant_id}` - 어시스턴트 업데이트
- **DELETE** `/assistants/{assistant_id}` - 어시스턴트 삭제
- **POST** `/assistants/search` - 어시스턴트 검색

### Store Management

- **POST** `/store/get` - 스토어에서 항목 조회
- **POST** `/store/put` - 스토어에 항목 저장
- **POST** `/store/delete` - 스토어에서 항목 삭제

### Runs Management (LangSmith)

- **POST** `/runs/feedback` - LangSmith run에 피드백 생성
  - `runId`: LangSmith run ID
  - `feedbackKey`: 피드백 키 (예: "correctness", "helpfulness")
  - `score`: 피드백 점수 (0.0 ~ 1.0)
  - `comment`: 선택사항, 피드백 코멘트
  
- **GET** `/runs/feedback` - LangSmith run의 피드백 조회
  - `runId`: LangSmith run ID
  - `feedbackKey`: 피드백 키
  
- **POST** `/runs/share` - LangSmith run 공유 URL 생성
  - `runId`: LangSmith run ID
  - 반환: 공개 공유 가능한 URL

## 에이전트 동작 구조

### Open Canvas Agent

Open Canvas Agent는 LangGraph를 사용하여 구현된 복잡한 상태 머신입니다. 사용자 요청을 분석하여 적절한 작업을 수행합니다.

#### 그래프 흐름

1. **경로 생성 (generatePath)**
   - 모든 요청은 `generatePath` 노드에서 시작
   - 사용자 입력과 상태를 분석하여 다음 작업 결정
   - 가능한 경로:
     - `generateArtifact`: 새 아티팩트 생성
     - `rewriteArtifact`: 전체 아티팩트 재작성
     - `updateArtifact`: 하이라이트된 코드 부분만 업데이트
     - `updateHighlightedText`: 하이라이트된 텍스트 업데이트
     - `rewriteArtifactTheme`: 아티팩트 테마(언어, 길이, 읽기 수준 등) 변경
     - `rewriteCodeArtifactTheme`: 코드 아티팩트 테마(주석, 로그, 언어 포팅, 버그 수정) 변경
     - `webSearch`: 웹 검색 수행
     - `customAction`: 커스텀 빠른 액션 처리
     - `replyToGeneralInput`: 아티팩트 없이 일반 응답

2. **웹 검색 경로**
   - `webSearch` 노드에서 웹 검색 수행
   - 검색 결과에 따라 `routePostWebSearch`에서 다음 노드 결정
   - 검색 결과를 활용하여 아티팩트 생성 또는 재작성

3. **아티팩트 처리 후 후처리**
   - 모든 아티팩트 관련 노드는 처리 후 `generateFollowup`으로 이동
   - 후속 메시지 생성 후 `reflect` 노드에서 반성 수행
   - `cleanState`에서 상태 정리

4. **조건부 종료**
   - 메시지가 2개 이하: `generateTitle`로 이동하여 제목 생성
   - 총 문자 수가 300,000 초과: `summarizer`로 이동하여 요약
   - 그 외: 바로 종료

#### 주요 기능

- **아티팩트 생성/수정**: 코드, 마크다운 등 다양한 형식의 아티팩트 생성 및 수정
- **부분 업데이트**: 하이라이트된 코드나 텍스트만 선택적으로 업데이트
- **테마 변경**: 언어, 길이, 읽기 수준, 이모지 등 아티팩트 스타일 변경
- **웹 검색 통합**: 필요시 웹 검색을 수행하여 최신 정보 활용
- **반성 및 학습**: 대화와 아티팩트를 분석하여 스타일 규칙과 메모리 생성

자세한 그래프 구조는 `open_canvas/README.md`를 참조하세요.

### Reflection Agent

Reflection Agent는 단일 노드로 구성된 간단한 그래프입니다.

#### 동작 방식

1. 대화 메시지와 아티팩트를 분석
2. 기존 반성 결과(스타일 규칙, 사용자 메모리)를 스토어에서 조회
3. LLM을 사용하여 새로운 스타일 규칙과 사용자 메모리 생성
4. 생성된 반성 결과를 스토어에 저장하여 향후 대화에 활용

#### 주요 기능

- **스타일 규칙 추출**: 대화에서 사용자의 선호 스타일과 가이드라인 추출
- **사용자 메모리 생성**: 사용자에 대한 사실과 정보 저장
- **지속적 학습**: 반성 결과를 저장하여 일관된 응답 제공

### Thread Title Agent

Thread Title Agent는 단일 노드로 구성된 그래프입니다.

#### 동작 방식

1. 대화 메시지와 아티팩트를 분석
2. LLM을 사용하여 적절한 제목 생성
3. 스레드 메타데이터 업데이트 (선택사항)

#### 주요 기능

- **자동 제목 생성**: 대화 내용을 기반으로 의미 있는 제목 생성
- **아티팩트 고려**: 생성된 아티팩트를 고려하여 더 정확한 제목 생성

### Summarizer Agent

Summarizer Agent는 단일 노드로 구성된 그래프입니다.

#### 동작 방식

1. 대화 메시지 전체를 요약
2. 요약된 내용을 새로운 메시지로 변환
3. 요약 메시지에 특별한 플래그 추가하여 원본 메시지 대체

#### 주요 기능

- **대화 압축**: 긴 대화 내용을 요약하여 토큰 사용량 최적화
- **컨텍스트 유지**: 요약 과정에서 중요한 정보 보존
- **투명한 요약**: 요약된 메시지임을 표시하여 모델이 적절히 처리

### Web Search Agent

Web Search Agent는 3단계 노드로 구성된 그래프입니다.

#### 동작 방식

1. **메시지 분류 (classifyMessage)**
   - 사용자의 최신 메시지를 분석하여 웹 검색 필요 여부 판단
   - 검색이 필요하지 않으면 바로 종료

2. **쿼리 생성 (queryGenerator)**
   - 대화 내용을 분석하여 검색 엔진 친화적인 쿼리 생성
   - 현재 날짜 등 추가 컨텍스트 포함

3. **웹 검색 (search)**
   - Tavily API를 사용하여 웹 검색 수행
   - 검색 결과를 구조화된 형식으로 반환

#### 주요 기능

- **지능형 검색 판단**: 모든 메시지에 대해 검색하지 않고 필요시에만 검색
- **컨텍스트 기반 쿼리**: 대화 맥락을 고려한 검색 쿼리 생성
- **구조화된 결과**: 검색 결과를 일관된 형식으로 제공
