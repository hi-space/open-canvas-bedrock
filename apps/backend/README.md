# Open Canvas Agents - FastAPI with AWS Bedrock

A Python FastAPI implementation of Open Canvas agents that provides LLM integration using AWS Bedrock.

## Overview

This project is a server that provides multiple AI agents implemented using LangGraph through FastAPI. The main features include:

- **Open Canvas Agent**: Main agent for conversation-based artifact generation and modification
- **Reflection Agent**: Reflection and feedback generation for conversations and artifacts
- **Thread Title Agent**: Automatic title generation for conversation threads
- **Summarizer Agent**: Summarization of long conversation content
- **Web Search Agent**: Web search functionality integration
- **Threads Management**: LangGraph SDK-compatible thread management
- **Assistants Management**: LangGraph SDK-compatible assistant management
- **Store Management**: LangGraph SDK-compatible store management

## Model Configuration

### Supported Models

Only AWS Bedrock models are supported. Main supported models:

- Claude Haiku 4.5, Sonnet 4, Sonnet 4.5, Opus 4.1
- Amazon Nova Premier, Pro, Micro, Lite
- Llama 3.3 70B Instruct
- DeepSeek R1, V3

See [core/models.py](./core/models.py) for the complete model list.

## Tech Stack

- **FastAPI**: Web framework
- **LangGraph**: State machine and agent orchestration
- **LangChain**: LLM integration and message processing
- **AWS Bedrock**: LLM provider
- **Tavily**: Web search (optional)
- **Pydantic**: Data validation
- **Uvicorn**: ASGI server

## Project Structure

The project follows a clean architecture pattern with clear separation of concerns:

```
apps/backend/
├── agents/              # Agent logic (graphs, nodes, states, prompts)
│   ├── open_canvas/    # Main Open Canvas agent
│   ├── reflection/      # Reflection agent
│   ├── thread_title/   # Thread title generation agent
│   ├── summarizer/     # Conversation summarization agent
│   └── web_search/     # Web search agent
│
├── api/                 # API endpoints (domain-based organization)
│   ├── open_canvas/    # Open Canvas API
│   │   └── routes.py
│   ├── threads/         # Thread management API
│   │   ├── models.py    # Pydantic request/response models
│   │   ├── service.py   # Business logic
│   │   ├── routes.py    # HTTP endpoints
│   │   └── store.py     # Data storage
│   ├── assistants/      # Assistant management API
│   ├── reflection/      # Reflection agent API
│   ├── thread_title/    # Thread title API
│   ├── summarizer/      # Summarizer API
│   ├── web_search/      # Web search API
│   ├── firecrawl/       # Firecrawl scraping API
│   ├── runs/            # LangSmith runs API
│   ├── store/           # Store management API
│   └── models/          # Model configuration API
│
├── core/                # Core utilities
│   ├── bedrock_client.py      # AWS Bedrock client
│   ├── utils.py              # Common utilities
│   ├── models.py             # Model configurations
│   ├── exceptions.py         # Custom exceptions
│   └── exception_handlers.py # Global exception handlers
│
└── store/               # Storage infrastructure
    ├── factory.py       # Storage factory
    ├── base.py          # Base storage classes
    └── ...
```

### Architecture Principles

1. **Domain-Driven Design**: Each API domain (threads, assistants, etc.) is self-contained with its own models, service, and routes
2. **Separation of Concerns**:
   - `models.py`: Pydantic models for request/response validation
   - `service.py`: Business logic (reusable, testable)
   - `routes.py`: HTTP endpoints (thin layer, delegates to service)
3. **Global Exception Handling**: Centralized error handling via exception handlers in `core/exception_handlers.py`
4. **Agent Logic Separation**: Agent implementations (graphs, nodes) are separate from API endpoints

## Installation and Execution

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Environment Variable Configuration

You can set environment variables directly or create a `.env` file:

### 3. Storage Configuration

You can configure storage for data such as assistant information, chat history, quick actions, and reflections.

#### Storage Type Selection

You can select the storage type through the `STORAGE_TYPE` environment variable:

- `memory` (default): Memory storage - data is lost on server restart
- `dynamodb`: AWS DynamoDB - cloud-based persistent storage

| Feature | Memory | DynamoDB |
|---------|--------|----------|
| Persistence | ❌ Lost on restart | ✅ Persistent storage |
| Setup Difficulty | Easy | Moderate (AWS setup required) |
| Cost | Free | AWS charges apply |
| Performance | Very fast | Fast |
| Scalability | Limited | Unlimited |
| Recommended Use | Development, Testing | Production |

#### DynamoDB Configuration

**Note**: When using DynamoDB, tables are automatically created. Appropriate permissions for DynamoDB are required:
- `dynamodb:CreateTable`
- `dynamodb:DescribeTable`
- `dynamodb:PutItem`
- `dynamodb:GetItem`
- `dynamodb:UpdateItem`
- `dynamodb:DeleteItem`
- `dynamodb:Query`

#### Data Storage Structure

The following data is stored in the selected storage:

- **Assistant Information** (entities table): Assistant ID, graph ID, configuration, metadata
- **Thread Information** (normalized structure):
  - `threads` table: Thread ID, metadata
  - `thread_messages` table: Conversation messages (stored independently)
  - `thread_artifacts` table: Artifact data (stored independently)
- **Store Data** (store_items table): 
  - Reflection data: `namespace=["memories", assistantId]`, `key="reflection"`
  - Quick actions: `namespace=["custom_actions", userId]`, `key="actions"`
  - Other LangGraph SDK-compatible store data

```
┌──────────────────────────────────────────────────┐
│  Entity Store (Assistant Management)             │
│  - assistants: Assistant metadata                │
│    ├─ assistant_id (PK)                          │
│    ├─ graph_id                                   │
│    ├─ config (name, icon, color)                 │
│    ├─ context_documents (attached files)        │
│    └─ metadata                                   │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Thread Store (Conversation Management)          │
│  - Normalized Structure                          │
│                                                  │
│  threads (Thread metadata)                       │
│  ├─ thread_id (PK)                               │
│  ├─ user_id                                      │
│  ├─ assistant_id                                 │
│  ├─ title                                        │
│  ├─ created_at                                   │
│  └─ metadata                                     │
│                                                  │
│  thread_messages (Messages)                      │
│  ├─ thread_id (PK)                               │
│  ├─ message_id (SK)                              │
│  ├─ role (human/assistant)                       │
│  ├─ content                                      │
│  ├─ attachments                                  │
│  └─ timestamp                                    │
│                                                  │
│  thread_artifacts (Artifacts)                     │
│  ├─ thread_id (PK)                               │
│  ├─ artifact_id (SK)                             │
│  ├─ current_index (current version)              │
│  └─ contents (versioned content array)          │
│      ├─ [0] { type, content, language, ... }    │
│      ├─ [1] { type, content, language, ... }    │
│      └─ ...                                      │
└──────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────┐
│  Key-Value Store (App Data)                      │
│                                                  │
│  Reflections (Learned Memory)                    │
│  - namespace: ["memories", assistant_id]         │
│  - key: "reflection"                             │
│  - value: {                                      │
│      style_rules: ["rule1", "rule2", ...],       │
│      user_memories: ["info1", "info2", ...]      │
│    }                                             │
│                                                  │
│  Custom Quick Actions                            │
│  - namespace: ["custom_actions", user_id]         │
│  - key: "actions"                                │
│  - value: [                                      │
│      { id, name, prompt, options, ... },         │
│      ...                                         │
│    ]                                             │
└──────────────────────────────────────────────────┘
```

### 4. Run Server

```bash
python main.py
```

Or use uvicorn directly:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## API Endpoints

### API Documentation

After starting the server, you can view the auto-generated API documentation at the following URLs:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

### Error Handling

The API uses global exception handlers for consistent error responses:

- **Custom Exceptions** (`core/exceptions.py`):
  - `NotFoundError`: 404 errors for missing resources
  - `ValidationError`: 400 errors for invalid input
  - `InternalServerError`: 500 errors for server issues

- **Exception Handlers** (`core/exception_handlers.py`):
  - All exceptions are caught and formatted consistently
  - Unhandled exceptions are logged with full traceback
  - Error responses follow a standard format:
    ```json
    {
      "error": "Error message",
      "detail": "Detailed error information",
      "status_code": 404
    }
    ```

### Code Organization

Each API domain follows a consistent structure:

- **models.py**: Pydantic models for request/response validation
- **service.py**: Business logic functions (pure, testable)
- **routes.py**: FastAPI route handlers (thin layer)
- **store.py**: Data access layer (if applicable)

This separation allows for:
- Easy unit testing of business logic
- Reusable service functions
- Clear separation of concerns
- Consistent error handling

## Agent Operation Structure

### Open Canvas Agent

The Open Canvas Agent is a complex state machine implemented using LangGraph. It analyzes user requests and performs appropriate tasks.

#### Graph Flow

```
START
  ↓
[generatePath] Path decision node
  ├─→ generateArtifact (create new artifact)
  ├─→ rewriteArtifact (full rewrite)
  ├─→ updateHighlightedText (text partial modification)
  ├─→ rewriteArtifactTheme (text theme: translation, length, emoji, etc.)
  ├─→ webSearch → [routePostWebSearch] → (artifact operations)
  ├─→ customAction (custom quick action)
  └─→ replyToGeneralInput (general conversation)
  ↓
[generateFollowup] Generate follow-up message
  ↓
[reflect] Perform Reflection (style learning)
  ↓
[cleanState] Clean state
  ↓
[shouldContinue] Condition check
  ├─→ generateTitle (messages ≤ 2)
  ├─→ summarizer (total > 300K characters)
  └─→ END
```

#### Detailed Node Descriptions

**1. generatePath (Path Decision)**
- Analyzes user input, current artifact state, and highlight information
- Uses LLM to determine the most appropriate next task
- Output: Next node name (e.g., "generateArtifact")

**2. Artifact Operation Nodes**
- `generateArtifact`: Create new artifact from user request
- `rewriteArtifact`: Fully rewrite existing artifact
- `updateHighlightedText`: Modify only highlighted text sections
- `rewriteArtifactTheme`: Translation, length adjustment, reading level changes, emoji addition
- `customAction`: Perform tasks with user-defined prompts

**3. webSearch (Web Search Path)**
- Calls Web Search Agent to perform web search
- `routePostWebSearch`: Determines next task using search results
- Search results are used as context when generating/modifying artifacts

**4. Post-Processing Nodes**
- `generateFollowup`: Generate appropriate follow-up messages after artifact operations
- `reflect`: Call Reflection Agent to learn user style
- `cleanState`: Clean temporary state for next execution

**5. Conditional Termination**
- `shouldContinue`: Checks conversation state to determine if additional tasks are needed
  - Messages ≤ 2 → `generateTitle` (title generation)
  - Total > 300,000 characters → `summarizer` (conversation summarization)
  - Otherwise → END (termination)

See [agents/open_canvas/README.md](./agents/open_canvas/README.md) for detailed graph structure and visualization.

### Reflection Agent

The Reflection Agent is a simple graph consisting of a single node.

#### Operation Method

1. Analyze conversation messages and artifacts
2. Retrieve existing reflection results (style rules, user memory) from store
3. Generate new style rules and user memory using LLM
4. Store generated reflection results in store for use in future conversations

#### Key Features

- **Style Rule Extraction**: Extract user's preferred styles and guidelines from conversations
- **User Memory Creation**: Store facts and information about the user
- **Continuous Learning**: Store reflection results to provide consistent responses

### Thread Title Agent

The Thread Title Agent is a graph consisting of a single node.

#### Operation Method

1. Analyze conversation messages and artifacts
2. Generate appropriate title using LLM
3. Update thread metadata (optional)

#### Key Features

- **Automatic Title Generation**: Generate meaningful titles based on conversation content
- **Artifact Consideration**: Generate more accurate titles by considering generated artifacts

### Summarizer Agent

The Summarizer Agent is a graph consisting of a single node.

#### Operation Method

1. Summarize all conversation messages
2. Convert summarized content to a new message
3. Add special flag to summarized message to replace original messages

#### Key Features

- **Conversation Compression**: Summarize long conversation content to optimize token usage
- **Context Preservation**: Preserve important information during summarization
- **Transparent Summarization**: Indicate summarized messages so models can process appropriately

### Web Search Agent

The Web Search Agent is a graph consisting of 3-stage nodes.

#### Operation Method

1. **Message Classification (classifyMessage)**
   - Analyzes user's latest message to determine if web search is needed
   - Terminates immediately if search is not needed

2. **Query Generation (queryGenerator)**
   - Analyzes conversation content to generate search engine-friendly queries
   - Includes additional context such as current date

3. **Web Search (search)**
   - Performs web search using Tavily API
   - Returns search results in structured format

#### Key Features

- **Intelligent Search Decision**: Search only when needed, not for every message
- **Context-Based Query**: Generate search queries considering conversation context
- **Structured Results**: Provide search results in consistent format
