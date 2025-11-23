# Open Canvas Web

Open Canvas is an open-source web application for collaborating with AI agents to write documents and code. Inspired by OpenAI's "Canvas", it is open-source and provides a memory system and the ability to start from existing documents.

## Key Features

### 1. Multi-Assistant Management

- **Custom Assistant Creation**: Create and manage multiple assistants by setting names, icons, and colors
- **Context Documents**: Attach text, PDF, audio, video files, or URLs to each assistant to provide context for all conversations
  - Supports up to 20 files
  - Document: 10MB, Audio: 25MB, Video: 1GB limits
- **Assistant Switching**: Switch to a different assistant at any time during conversation

### 2. Artifact Management

- **Code and Markdown Support**: Generate and edit both code and markdown text
- **Multiple Programming Languages**: Support for various languages including Python, JavaScript, Java, C++, Rust, SQL, HTML, PHP, C#, Clojure, etc.
- **Version Control**: All artifacts have version history and can be reverted to previous versions
- **Real-Time Markdown Rendering**: View rendered results while editing markdown
- **Text Selection Editing**: Select text in artifacts to modify specific parts

### 3. Quick Actions

#### Quick Actions for Text Artifacts
- **Translation**: Translate to various languages
- **Reading Level Adjustment**: Adjust text reading difficulty
- **Length Adjustment**: Make text shorter or longer
- **Emoji Addition**: Automatically add emojis to text

#### Quick Actions for Code Artifacts
- **Comment Addition**: Automatically add explanatory comments to code
- **Log Addition**: Add log statements for debugging
- **Language Porting**: Convert code to other programming languages
- **Bug Fixing**: Automatically detect and fix bugs in code

#### Custom Quick Actions
- **User-Defined Action Creation**: Write your own prompts and save them as quick actions
- **Persistence Across Sessions**: Custom quick actions created are available in all sessions
- **Context Inclusion Options**: Configure whether to include Reflection (Reflections), recent conversation history, and prefix

### 4. Memory and Reflection System

- **Automatic Reflection Generation**: Automatically extract user's style rules and preferences by analyzing conversation content
- **Style Rule Storage**: Learn and store writing styles, tones, and format preferences to provide consistent responses
- **User Memory**: Store facts and information about users to provide personalized experiences
- **Reflection Review**: View and delete generated style rules and content reflections in the Reflection dialog

### 5. Web Search Integration

- **Automatic Web Search**: Automatically perform web searches when needed by analyzing conversation content
- **Search Result Display**: Display search results as cards in the side panel
- **Real-Time Information**: Support content generation with latest information

### 6. Conversation Management

- **Thread History**: Manage all conversations as threads, grouped by date (today, yesterday, last 7 days, earlier)
- **Automatic Thread Title Generation**: Automatically generate thread titles based on conversation content
- **Thread Search and Deletion**: Search and delete previous conversations

### 7. Model Selection and Configuration

- **Various AWS Bedrock Model Support**:
  - Anthropic: Claude Haiku 4.5, Sonnet 4, Sonnet 4.5, Opus 4.1
  - Amazon: Nova Premier, Pro, Lite, Micro
  - Meta: Llama 3.3 70B Instruct
  - DeepSeek: R1, V3
- **Model Settings**: Adjust temperature and max tokens
- **Per-Conversation Model Selection**: Select the model to use for each conversation

### 8. File Attachments and Media Support

- **File Attachments**: Attach text, PDF, image, audio, video files to conversations
- **Audio Transcription**: Automatic transcription of audio files via Whisper
- **Web Scraping**: Web page scraping and content extraction via Firecrawl

### 9. User Interface

- **Resizable Panels**: Adjust chat and canvas panel sizes by dragging
- **Chat Panel Collapse/Expand**: Collapse chat panel to get more space for canvas
- **Responsive Design**: Layout optimized for various screen sizes

### 10. Feedback and Sharing

- **Execution Feedback**: Provide feedback for each AI response
- **Execution Sharing**: Execution tracking and sharing via LangSmith

## Tech Stack

- **Framework**: Next.js 14
- **UI Library**: React, Radix UI, Tailwind CSS
- **Agent UI**: @assistant-ui/react
- **Editor**: CodeMirror (code), BlockNote (markdown)
- **State Management**: Zustand, React Context

## Getting Started

### Prerequisites

- Node.js 18+
- Yarn package manager

### Running Development Server

```bash
# Start development server
yarn dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser to view the application.

## Project Structure

```
apps/web/
├── src/
│   ├── app/              # Next.js app router
│   │   ├── api/          # API routes
│   │   └── auth/         # Authentication pages
│   ├── components/       # React components
│   │   ├── artifacts/    # Artifact rendering and editing
│   │   ├── assistant-select/  # Assistant selection and management
│   │   ├── chat-interface/    # Chat interface
│   │   ├── canvas/       # Main canvas
│   │   └── ui/           # Reusable UI components
│   ├── contexts/         # React Context
│   ├── hooks/            # Custom hooks
│   ├── lib/              # Utility functions
│   └── shared/           # Shared types and constants
├── public/               # Static files
└── package.json
```

## Key Components

### Canvas
The main canvas component that manages the chat panel and artifact renderer.

### ArtifactRenderer
Renders code and markdown artifacts and provides editing functionality.

### AssistantSelect
Component for selecting, creating, editing, and deleting assistants.

### ChatInterface
Provides chat functionality including message display, input, and thread management.

