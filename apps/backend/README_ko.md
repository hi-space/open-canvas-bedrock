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

## 모델 설정

### 지원 모델

AWS Bedrock 모델만 지원됩니다. 주요 지원 모델:

- Claude Haiku 4.5, Sonnet 4, Sonnet 4.5, Opus 4.1
- Amazon Nova Premier, Pro, Micro, Lite
- Llama 3.3 70B Instruct
- DeepSeek R1, V3

전체 모델 목록은 [core/models.py](./core/models.py)를 참조하세요.


## 기술 스택

- **FastAPI**: 웹 프레임워크
- **LangGraph**: 상태 머신 및 에이전트 오케스트레이션
- **LangChain**: LLM 통합 및 메시지 처리
- **AWS Bedrock**: LLM 제공자
- **Tavily**: 웹 검색 (선택사항)
- **Pydantic**: 데이터 검증
- **Uvicorn**: ASGI 서버

## 프로젝트 구조

프로젝트는 관심사 분리 원칙에 따라 깔끔한 아키텍처 패턴을 따릅니다:

```
apps/backend/
├── agents/              # 에이전트 로직 (그래프, 노드, 상태, 프롬프트)
│   ├── open_canvas/    # 메인 Open Canvas 에이전트
│   ├── reflection/     # Reflection 에이전트
│   ├── thread_title/   # 스레드 제목 생성 에이전트
│   ├── summarizer/     # 대화 요약 에이전트
│   └── web_search/     # 웹 검색 에이전트
│
├── api/                 # API 엔드포인트 (도메인별 구성)
│   ├── open_canvas/    # Open Canvas API
│   │   └── routes.py
│   ├── threads/         # 스레드 관리 API
│   │   ├── models.py    # Pydantic 요청/응답 모델
│   │   ├── service.py   # 비즈니스 로직
│   │   ├── routes.py    # HTTP 엔드포인트
│   │   └── store.py     # 데이터 저장소
│   ├── assistants/      # 어시스턴트 관리 API
│   ├── reflection/      # Reflection 에이전트 API
│   ├── thread_title/    # 스레드 제목 API
│   ├── summarizer/      # 요약 API
│   ├── web_search/      # 웹 검색 API
│   ├── firecrawl/       # Firecrawl 스크래핑 API
│   ├── runs/            # LangSmith runs API
│   ├── store/           # 스토어 관리 API
│   └── models/          # 모델 설정 API
│
├── core/                # 공통 유틸리티
│   ├── bedrock_client.py      # AWS Bedrock 클라이언트
│   ├── utils.py              # 공통 유틸리티
│   ├── models.py             # 모델 설정
│   ├── exceptions.py         # 커스텀 예외
│   └── exception_handlers.py # 전역 예외 핸들러
│
└── store/               # 저장소 인프라
    ├── factory.py       # 저장소 팩토리
    ├── base.py          # 기본 저장소 클래스
    └── ...
```

### 아키텍처 원칙

1. **도메인 주도 설계**: 각 API 도메인(threads, assistants 등)은 자체 모델, 서비스, 라우트를 포함하는 독립적인 구조
2. **관심사 분리**:
   - `models.py`: 요청/응답 검증을 위한 Pydantic 모델
   - `service.py`: 비즈니스 로직 (재사용 가능, 테스트 가능)
   - `routes.py`: HTTP 엔드포인트 (얇은 레이어, 서비스에 위임)
3. **전역 예외 처리**: `core/exception_handlers.py`의 예외 핸들러를 통한 중앙화된 에러 처리
4. **에이전트 로직 분리**: 에이전트 구현(그래프, 노드)은 API 엔드포인트와 분리

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정

환경 변수를 직접 설정하거나 `.env` 파일을 생성할 수 있습니다:

### 3. 저장소 설정

어시스턴트 정보, 채팅 히스토리, 빠른 액션, 반성(reflection) 등의 데이터를 저장하는 저장소를 설정할 수 있습니다.

#### 저장소 타입 선택

환경 변수 `STORAGE_TYPE`을 통해 저장소 타입을 선택할 수 있습니다:

- `memory` (기본값): 메모리 저장소 - 서버 재시작 시 데이터가 사라집니다
- `dynamodb`: AWS DynamoDB - 클라우드 기반 영구 저장소

| 특징 | Memory | DynamoDB |
|------|--------|----------|
| 영속성 | ❌ 재시작 시 소실 | ✅ 영구 저장 |
| 설정 난이도 | 쉬움 | 보통 (AWS 설정 필요) |
| 비용 | 무료 | AWS 요금 발생 |
| 성능 | 매우 빠름 | 빠름 |
| 확장성 | 제한적 | 무제한 |
| 권장 용도 | 개발, 테스트 | 프로덕션 |

#### DynamoDB 설정

**참고**: DynamoDB를 사용하는 경우, 테이블이 자동으로 생성됩니다. DynamoDB에 대한 적절한 권한이 필요합니다:
- `dynamodb:CreateTable`
- `dynamodb:DescribeTable`
- `dynamodb:PutItem`
- `dynamodb:GetItem`
- `dynamodb:UpdateItem`
- `dynamodb:DeleteItem`
- `dynamodb:Query`

#### 데이터 저장 구조
다음 데이터들이 선택한 저장소에 저장됩니다:

- **어시스턴트 정보** (entities 테이블): 어시스턴트 ID, 그래프 ID, 설정, 메타데이터
- **스레드 정보** (정규화된 구조):
  - `threads` 테이블: 스레드 ID, 메타데이터
  - `thread_messages` 테이블: 대화 메시지들 (독립적으로 저장)
  - `thread_artifacts` 테이블: 아티팩트 데이터 (독립적으로 저장)
- **스토어 데이터** (store_items 테이블): 
  - 반성(reflection) 데이터: `namespace=["memories", assistantId]`, `key="reflection"`
  - 빠른 액션(quick actions): `namespace=["custom_actions", userId]`, `key="actions"`
  - 기타 LangGraph SDK 호환 스토어 데이터

```
┌──────────────────────────────────────────────────┐
│  Entity Store (어시스턴트 관리)                    │
│  - assistants: 어시스턴트 메타데이터               │
│    ├─ assistant_id (PK)                          │
│    ├─ graph_id                                   │
│    ├─ config (이름, 아이콘, 색상)                 │
│    ├─ context_documents (첨부 파일)              │
│    └─ metadata                                   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Thread Store (대화 관리) - 정규화된 구조          │
│                                                  │
│  threads (스레드 메타데이터)                       │
│  ├─ thread_id (PK)                               │
│  ├─ user_id                                      │
│  ├─ assistant_id                                 │
│  ├─ title                                        │
│  ├─ created_at                                   │
│  └─ metadata                                     │
│                                                  │
│  thread_messages (메시지)                         │
│  ├─ thread_id (PK)                               │
│  ├─ message_id (SK)                              │
│  ├─ role (human/assistant)                       │
│  ├─ content                                      │
│  ├─ attachments                                  │
│  └─ timestamp                                    │
│                                                  │
│  thread_artifacts (아티팩트)                      │
│  ├─ thread_id (PK)                               │
│  ├─ artifact_id (SK)                             │
│  ├─ current_index (현재 버전)                     │
│  └─ contents (버전별 내용 배열)                    │
│      ├─ [0] { type, content, language, ... }    │
│      ├─ [1] { type, content, language, ... }    │
│      └─ ...                                      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Key-Value Store (앱 데이터)                      │
│                                                  │
│  Reflections (학습된 메모리)                       │
│  - namespace: ["memories", assistant_id]         │
│  - key: "reflection"                             │
│  - value: {                                      │
│      style_rules: ["규칙1", "규칙2", ...],        │
│      user_memories: ["정보1", "정보2", ...]       │
│    }                                             │
│                                                  │
│  Custom Quick Actions (커스텀 퀵 액션)             │
│  - namespace: ["custom_actions", user_id]        │
│  - key: "actions"                                │
│  - value: [                                      │
│      { id, name, prompt, options, ... },         │
│      ...                                         │
│    ]                                             │
└──────────────────────────────────────────────────┘
```

### 4. 서버 실행

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

### 에러 처리

API는 일관된 에러 응답을 위해 전역 예외 핸들러를 사용합니다:

- **커스텀 예외** (`core/exceptions.py`):
  - `NotFoundError`: 리소스를 찾을 수 없을 때 404 에러
  - `ValidationError`: 잘못된 입력일 때 400 에러
  - `InternalServerError`: 서버 문제일 때 500 에러

- **예외 핸들러** (`core/exception_handlers.py`):
  - 모든 예외가 일관된 형식으로 포착되고 포맷팅됨
  - 처리되지 않은 예외는 전체 트레이스백과 함께 로깅됨
  - 에러 응답은 표준 형식을 따름:
    ```json
    {
      "error": "에러 메시지",
      "detail": "상세 에러 정보",
      "status_code": 404
    }
    ```

### 코드 구조

각 API 도메인은 일관된 구조를 따릅니다:

- **models.py**: 요청/응답 검증을 위한 Pydantic 모델
- **service.py**: 비즈니스 로직 함수 (순수 함수, 테스트 가능)
- **routes.py**: FastAPI 라우트 핸들러 (얇은 레이어)
- **store.py**: 데이터 접근 레이어 (해당되는 경우)

이러한 분리를 통해:
- 비즈니스 로직의 쉬운 단위 테스트
- 재사용 가능한 서비스 함수
- 명확한 관심사 분리
- 일관된 에러 처리

## 에이전트 동작 구조

### Open Canvas Agent

Open Canvas Agent는 LangGraph를 사용하여 구현된 복잡한 상태 머신입니다. 사용자 요청을 분석하여 적절한 작업을 수행합니다.

#### 그래프 흐름

```
START
  ↓
[generatePath] 경로 결정 노드
  ├─→ generateArtifact (새 아티팩트 생성)
  ├─→ rewriteArtifact (전체 재작성)
  ├─→ updateHighlightedText (텍스트 부분 수정)
  ├─→ rewriteArtifactTheme (텍스트 테마: 번역, 길이, 이모지 등)
  ├─→ webSearch → [routePostWebSearch] → (아티팩트 작업)
  ├─→ customAction (커스텀 퀵 액션)
  └─→ replyToGeneralInput (일반 대화)
  ↓
[generateFollowup] 후속 메시지 생성
  ↓
[reflect] Reflection 수행 (스타일 학습)
  ↓
[cleanState] 상태 정리
  ↓
[shouldContinue] 조건 확인
  ├─→ generateTitle (메시지 ≤ 2개)
  ├─→ summarizer (총 300K자 초과)
  └─→ END
```

#### 노드별 상세 설명

**1. generatePath (경로 결정)**
- 사용자 입력, 현재 아티팩트 상태, 하이라이트 정보를 분석
- LLM을 사용하여 가장 적절한 다음 작업 결정
- 출력: 다음 노드 이름 (예: "generateArtifact")

**2. 아티팩트 작업 노드들**
- `generateArtifact`: 사용자 요청으로부터 새 아티팩트 생성
- `rewriteArtifact`: 기존 아티팩트를 전면 재작성
- `updateHighlightedText`: 하이라이트된 텍스트 부분만 수정
- `rewriteArtifactTheme`: 번역, 길이 조정, 읽기 수준 변경, 이모지 추가
- `customAction`: 사용자 정의 프롬프트로 작업 수행

**3. webSearch (웹 검색 경로)**
- Web Search Agent를 호출하여 웹 검색 수행
- `routePostWebSearch`: 검색 결과를 활용하여 다음 작업 결정
- 검색 결과는 아티팩트 생성/수정 시 컨텍스트로 활용

**4. 후처리 노드들**
- `generateFollowup`: 아티팩트 작업 후 적절한 후속 메시지 생성
- `reflect`: Reflection Agent 호출하여 사용자 스타일 학습
- `cleanState`: 다음 실행을 위해 임시 상태 정리

**5. 조건부 종료**
- `shouldContinue`: 대화 상태를 확인하여 추가 작업 필요 여부 판단
  - 메시지 2개 이하 → `generateTitle` (제목 생성)
  - 총 300,000자 초과 → `summarizer` (대화 요약)
  - 그 외 → END (종료)

자세한 그래프 구조와 시각화는 [agents/open_canvas/README.md](./agents/open_canvas/README.md)를 참조하세요.

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
