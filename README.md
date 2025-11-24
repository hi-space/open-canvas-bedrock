# Open Canvas - Apps

> **Note**: This project is based on modified code from [langchain-ai/open-canvas](https://github.com/langchain-ai/open-canvas).

Open Canvas is a platform for generating and improving documents and code through collaboration with AI agents. The backend (Agents) and frontend (Web) are tightly integrated to provide the following core features.

[![Demo](./static/screenshot.png)](https://www.youtube.com/watch?v=vJb0TTRrEvU)

(_Click on the image to watch the demo video on YouTube_)

## 🔄 System Architecture and Data Flow

### Overall Flow

```
┌─────────────────────────────────────────────────────────────┐
│  User (Browser)                                             │
│  - Conversation input, file attachments, artifact editing    │
└─────────────────────┬───────────────────────────────────────┘
                      ↓ HTTP / SSE
┌─────────────────────────────────────────────────────────────┐
│  Web App (Next.js)                                          │
│  - UI rendering, user interaction handling                   │
│  - Authentication (Supabase), state management (Zustand)     │
└─────────────────────┬───────────────────────────────────────┘
                      ↓ HTTP / SSE
┌─────────────────────────────────────────────────────────────┐
│  Agents API (FastAPI)                                       │
│  - Routing, request validation                              │
│  - File processing (Whisper, Firecrawl, PDF-parse)           │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  LangGraph Agents                                           │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐ │
│  │ Open Canvas     │  │ Reflection   │  │ Web Search     │ │
│  │ Agent           │  │ Agent        │  │ Agent          │ │
│  └─────────────────┘  └──────────────┘  └────────────────┘ │
│  ┌─────────────────┐  ┌──────────────┐                     │
│  │ Thread Title    │  │ Summarizer   │                     │
│  │ Agent           │  │ Agent        │                     │
│  └─────────────────┘  └──────────────┘                     │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  AWS Bedrock (LLM)                                          │
│  - Claude, Nova, Llama, DeepSeek                            │
└─────────────────────┬───────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────────────┐
│  Storage                                                    │
│  - Memory (for development) or DynamoDB (for production)    │
│  - Threads, Messages, Artifacts, Assistants, Store          │
└─────────────────────────────────────────────────────────────┘
```

## 🎯 Core Features

### 1. 🤖 AI Agent System

![agent-graph](./static/agent_graph.png)

#### Open Canvas Agent (Main Agent)
The core agent that generates and modifies artifacts (documents/code) through conversation.

**Key Features:**
- **Artifact Generation**: Create new code or markdown documents based on user requests
- **Full Rewrite**: Completely rewrite existing artifacts
- **Partial Modification**: 
  - Selectively update only highlighted code sections
  - Selectively modify only highlighted text sections
- **Theme Changes**:
  - Text: Language translation, length adjustment, reading level changes, emoji addition
  - Code: Comment addition, log addition, language porting, bug fixes
- **Web Search Integration**: Automatically perform web searches when latest information is needed
- **Custom Actions**: Customized tasks through user-defined prompts

**How It Works:**
1. Analyze user input → Determine appropriate task path
2. Perform web search if needed → Utilize search results
3. Execute artifact generation/modification
4. Generate follow-up messages
5. Perform Reflection (learn user style)

#### Reflection Agent (Memory Agent)
Analyzes conversation content and artifacts to learn user preferences and styles.

**Key Features:**
- **Style Rule Extraction**: Understand user's writing style, tone, and format preferences
- **User Memory Creation**: Store facts and information about the user
- **Continuous Learning**: Provide consistent responses across sessions
- **Context Utilization**: Automatically apply learned content to future conversations

**Stored Information:**
- Preferred writing styles (concise, detailed, etc.)
- Frequently used programming patterns
- Preferences for specific terms or expressions
- User background information (occupation, interests, etc.)

#### Web Search Agent (Search Agent)
Analyzes conversation context to determine if web search is needed and executes it.

**Key Features:**
- **Intelligent Search Decision**: Search only when needed, not for every message
- **Context-Based Query Generation**: Optimized search queries considering conversation context
- **Structured Results**: Provide search results in a consistent format
- **Real-Time Information**: Provide latest web information through Tavily API

#### Thread Title Agent (Title Generation Agent)
Analyzes conversation content to automatically generate appropriate titles.

**Key Features:**
- **Automatic Title Generation**: Automatically executed after initial 2-3 messages
- **Meaningful Titles**: Accurate titles considering both conversation and artifacts
- **Multi-Language Support**: Generate titles matching the conversation language

#### Summarizer Agent (Summarization Agent)
Summarizes long conversation content to optimize token usage.

**Key Features:**
- **Conversation Compression**: Automatically executed when conversation exceeds 300,000 characters
- **Context Preservation**: Preserve important information during summarization
- **Transparent Summarization**: Clearly indicate summarized messages for appropriate processing

### 2. 📝 Artifact Management

#### Supported Formats
- **Code**: Python, JavaScript, Java, C++, Rust, SQL, HTML, PHP, C#, Clojure, etc.
- **Documents**: Markdown, plain text

#### Editing Features
- **Real-Time Editing**: Edit code and markdown in real-time
- **Live Markdown Rendering**: View rendered results while editing
- **Syntax Highlighting**: Support syntax highlighting for various programming languages
- **Text Selection Editing**: Select specific parts to request AI modifications

#### Version Control
- **Automatic Version Creation**: Automatically create new versions for every modification
- **Version History**: View previous versions in chronological order
- **Version Restoration**: Restore to previous versions at any time
- **Version Comparison**: Check changes between versions

### 3. ⚡ Quick Action System

#### Default Quick Actions for Text Artifacts
- **Translation**: Translate to 20+ languages (Korean, English, Japanese, Chinese, etc.)
- **Reading Level Adjustment**: Adjust difficulty from elementary to expert level
- **Length Adjustment**: Rewrite text to be shorter or longer
- **Emoji Addition**: Automatically add appropriate emojis to text

#### Default Quick Actions for Code Artifacts
- **Comment Addition**: Automatically generate explanatory comments for code
- **Log Addition**: Automatically insert log statements for debugging
- **Language Porting**: Convert code to other programming languages
- **Bug Fixing**: Detect and fix potential bugs in code

#### Custom Quick Actions
User-created customized quick actions.

**Features:**
- **Prompt Definition**: Describe desired tasks in natural language
- **Option Settings**:
  - Include Reflection: Apply learned style rules
  - Include Recent Conversation: Utilize conversation context
  - Prefix Message: Include additional instructions
- **Persistence Across Sessions**: Once created, available in all sessions
- **Per-Assistant Management**: Different custom actions can be set for each assistant

### 4. 👥 Multi-Assistant Management

#### Assistant Creation and Configuration
- **Customization**: Create distinctive assistants with names, icons, colors, etc.
- **Individual Memory**: Each assistant has independent Reflection memory
- **Purpose-Based Separation**: Manage assistants by purpose (coding-only, document-writing-only, etc.)

#### Context Document Attachment
You can attach permanent context documents to each assistant.

**Supported Files:**
- Documents: TXT, PDF (max 10MB)
- Web Pages: URL input - Firecrawl scraping
- Maximum 20 files can be attached simultaneously

#### Assistant Switching
- **Switch During Conversation**: Switch to a different assistant at any time during conversation
- **Context Preservation**: Previous conversation content remains intact
- **Different Perspectives**: Check different assistants' approaches to the same problem

### 5. 💬 Conversation and Thread Management

#### Thread System
- **Automatic Thread Creation**: Create unique threads for each new conversation
- **Thread History**: Grouped by date (today, yesterday, last 7 days, earlier)
- **Automatic Title Generation**: Automatically generate titles based on conversation content
- **Thread Search**: Quickly find previous conversations
- **Thread Deletion**: Delete unnecessary conversations

#### Message Processing
- **Streaming Response**: Real-time responses through Server-Sent Events (SSE)
- **Multiple Message Types**:
  - General conversation messages
  - Artifact generation/modification messages
  - Web search result messages
  - System messages (summarization, title generation, etc.)
- **File Attachments**: Attach files to conversations to provide context
- **Feedback System**: Provide positive/negative feedback for each response

### 6. 🧠 Memory and Learning System

#### Reflection System
Continuously learns by analyzing conversations and artifacts.

**How It Works:**
1. **Automatic Analysis**: Automatically perform Reflection after artifact generation
2. **Information Extraction**:
   - Style Rules: Writing style, tone, structure preferences
   - User Memory: Facts and background information about the user
3. **Storage and Utilization**: Store extracted information in store and utilize in future conversations
4. **Cumulative Learning**: More accurate user understanding as conversations continue

### 7. 🔍 Web Search and Scraping

#### Automatic Web Search
- **Intelligent Trigger**: Automatically perform web search when latest information is needed
- **Tavily API Integration**: Provide high-quality search results
- **Result Display**: Display search results as cards in the side panel
- **Source Links**: Provide original URLs for each result

#### Web Scraping
- **Firecrawl Integration**: Extract content from URLs
- **Markdown Conversion**: Convert scraped content to markdown
- **Context Utilization**: Use scraped content as assistant context or messages

### 8. 🎨 User Interface

#### Layout
- **Resizable Panels**: Adjust chat and canvas panel sizes by dragging
- **Chat Panel Toggle**: Collapse chat panel to focus on canvas
- **Responsive Design**: Optimized for various screen sizes
- **Dark Mode**: Dark mode support to reduce eye strain

#### Editor
- **CodeMirror**: Powerful code editor
  - Syntax highlighting
  - Auto-completion
  - Multiple cursors
  - Code folding
- **BlockNote**: Rich markdown editor
  - Real-time rendering
  - Block-based editing
  - Support for images, tables, etc.

#### Model Selection
- **Model Selector**: Select model to use for each conversation
- **Model Settings**:
  - Temperature: Control creativity (0.0 ~ 1.0)
  - Max Tokens: Set maximum response length
- **Supported Models**:
  - Anthropic Claude (Haiku 4.5, Sonnet 4, Sonnet 4.5, Opus 4.1)
  - Amazon Nova (Premier, Pro, Lite, Micro)
  - Meta Llama 3.3 70B
  - DeepSeek (R1, V3)

### 9. 🔗 Integration Features

#### LangSmith Integration
- **Execution Tracking**: Track all agent executions in LangSmith
- **Feedback Collection**: Send feedback for each response to LangSmith
- **Execution Sharing**: Create shareable URLs for specific executions
- **Debugging**: Analyze agent behavior in detail

#### File and Media Processing
- **Images**: JPEG, PNG, GIF, etc. - Provided directly as context
- **PDF**: Text extraction using pdf-parse
- **Code Files**: Read as text and provide as context

## 🔧 Detailed Tech Stack

### Backend (Agents)
- **FastAPI**: High-performance asynchronous web framework
- **LangGraph**: State machine-based agent orchestration
- **LangChain**: LLM integration and message processing
- **AWS Bedrock**: Enterprise-grade LLM service
- **Pydantic**: Data validation and serialization
- **Uvicorn**: ASGI server
- **Boto3**: AWS SDK for Python
- **3rd Party API:**
  - Tavily: Web search
  - Firecrawl: Web scraping
  - LangSmith: Tracing and observability

### Frontend (Web)
- **Next.js 14**: React-based full-stack framework
- **React 18**: UI library
- **TypeScript**: Type safety
- **@assistant-ui/react**: Chat UI components
- **Radix UI**: Accessible UI primitives
- **Tailwind CSS**: Utility-first CSS framework
- **CodeMirror**: Code editor
- **BlockNote**: Markdown editor
- **Zustand**: Lightweight state management
- **React Resizable Panels**: Resizable layout
- **Framer Motion**: Animation

## 📚 Related Documentation

- [Agents Detailed Documentation](./apps/agents/README.md): Backend architecture and API
- [Web Detailed Documentation](./apps/web/README.md): Frontend structure and components
