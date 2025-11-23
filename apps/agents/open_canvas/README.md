# Open Canvas LangGraph Diagram

This diagram visualizes the LangGraph structure of Open Canvas.

## Overall Graph Structure

```mermaid
graph TD
    START([START]) --> generatePath[generatePath<br/>Path generation and routing]
    
    generatePath -->|updateArtifact| updateArtifact[updateArtifact<br/>Update highlighted code]
    generatePath -->|rewriteArtifactTheme| rewriteArtifactTheme[rewriteArtifactTheme<br/>Rewrite artifact theme]
    generatePath -->|rewriteCodeArtifactTheme| rewriteCodeArtifactTheme[rewriteCodeArtifactTheme<br/>Rewrite code artifact theme]
    generatePath -->|replyToGeneralInput| replyToGeneralInput[replyToGeneralInput<br/>Reply to general input]
    generatePath -->|generateArtifact| generateArtifact[generateArtifact<br/>Generate new artifact]
    generatePath -->|rewriteArtifact| rewriteArtifact[rewriteArtifact<br/>Rewrite entire artifact]
    generatePath -->|customAction| customAction[customAction<br/>Handle custom action]
    generatePath -->|updateHighlightedText| updateHighlightedText[updateHighlightedText<br/>Update highlighted text]
    generatePath -->|webSearch| webSearch[webSearch<br/>Perform web search]
    
    webSearch --> routePostWebSearch[routePostWebSearch<br/>Route after web search]
    routePostWebSearch -->|generateArtifact| generateArtifact
    routePostWebSearch -->|rewriteArtifact| rewriteArtifact
    
    generateArtifact --> generateFollowup[generateFollowup<br/>Generate follow-up message]
    updateArtifact --> generateFollowup
    updateHighlightedText --> generateFollowup
    rewriteArtifact --> generateFollowup
    rewriteArtifactTheme --> generateFollowup
    rewriteCodeArtifactTheme --> generateFollowup
    customAction --> generateFollowup
    replyToGeneralInput --> generateFollowup
    
    generateFollowup --> reflect[reflect<br/>Reflect on conversation and artifacts]
    reflect --> cleanState[cleanState<br/>Clean state]
    
    cleanState -->|messages.length <= 2| generateTitle[generateTitle<br/>Generate conversation title]
    cleanState -->|total_chars > 300000| summarizer[summarizer<br/>Summarize messages]
    cleanState -->|otherwise| END([END])
    
    generateTitle --> END
    summarizer --> END
    
    style START fill:#90EE90,stroke:#333,stroke-width:3px
    style END fill:#FFB6C1,stroke:#333,stroke-width:3px
    style generatePath fill:#87CEEB,stroke:#333,stroke-width:2px
    style generateArtifact fill:#FFD700,stroke:#333,stroke-width:2px
    style rewriteArtifact fill:#FFD700,stroke:#333,stroke-width:2px
    style updateArtifact fill:#FFD700,stroke:#333,stroke-width:2px
    style updateHighlightedText fill:#FFD700,stroke:#333,stroke-width:2px
    style rewriteArtifactTheme fill:#FFD700,stroke:#333,stroke-width:2px
    style rewriteCodeArtifactTheme fill:#FFD700,stroke:#333,stroke-width:2px
    style webSearch fill:#98FB98,stroke:#333,stroke-width:2px
    style routePostWebSearch fill:#98FB98,stroke:#333,stroke-width:2px
    style customAction fill:#98FB98,stroke:#333,stroke-width:2px
    style replyToGeneralInput fill:#98FB98,stroke:#333,stroke-width:2px
    style reflect fill:#DDA0DD,stroke:#333,stroke-width:2px
    style generateFollowup fill:#F0E68C,stroke:#333,stroke-width:2px
    style cleanState fill:#DDA0DD,stroke:#333,stroke-width:2px
    style generateTitle fill:#DDA0DD,stroke:#333,stroke-width:2px
    style summarizer fill:#DDA0DD,stroke:#333,stroke-width:2px
```

## Step-by-Step Flow

### 1. Entry and Routing Stage
```mermaid
graph LR
    START([START]) --> generatePath[generatePath]
    generatePath -->|Conditional routing| A[Various nodes]
    
    style START fill:#90EE90
    style generatePath fill:#87CEEB
```

### 2. Artifact Processing Stage
```mermaid
graph TD
    A[generatePath] -->|Routing| B1[generateArtifact]
    A -->|Routing| B2[rewriteArtifact]
    A -->|Routing| B3[updateArtifact]
    A -->|Routing| B4[updateHighlightedText]
    A -->|Routing| B5[rewriteArtifactTheme]
    A -->|Routing| B6[rewriteCodeArtifactTheme]
    
    B1 --> C[generateFollowup]
    B2 --> C
    B3 --> C
    B4 --> C
    B5 --> C
    B6 --> C
    
    style B1 fill:#FFD700
    style B2 fill:#FFD700
    style B3 fill:#FFD700
    style B4 fill:#FFD700
    style B5 fill:#FFD700
    style B6 fill:#FFD700
    style C fill:#F0E68C
```

### 3. Web Search Flow
```mermaid
graph LR
    A[generatePath] -->|webSearch| B[webSearch]
    B --> C[routePostWebSearch]
    C -->|generateArtifact| D[generateArtifact]
    C -->|rewriteArtifact| E[rewriteArtifact]
    D --> F[generateFollowup]
    E --> F
    
    style B fill:#98FB98
    style C fill:#98FB98
```

### 4. Post-Processing and Termination Stage
```mermaid
graph TD
    A[generateFollowup] --> B[reflect]
    B --> C[cleanState]
    C -->|messages <= 2| D[generateTitle]
    C -->|chars > 300000| E[summarizer]
    C -->|otherwise| F([END])
    D --> F
    E --> F
    
    style A fill:#F0E68C
    style B fill:#DDA0DD
    style C fill:#DDA0DD
    style D fill:#DDA0DD
    style E fill:#DDA0DD
    style F fill:#FFB6C1
```

## Node Descriptions

### Entry Point
- **generatePath**: Analyzes user requests and generates appropriate paths for routing.

### Artifact Generation/Modification Nodes
- **generateArtifact**: Generates new artifacts.
- **rewriteArtifact**: Rewrites entire artifacts.
- **updateArtifact**: Updates only highlighted code sections.
- **updateHighlightedText**: Updates highlighted text in markdown artifacts.
- **rewriteArtifactTheme**: Changes artifact themes (language, length, reading level, emoji).
- **rewriteCodeArtifactTheme**: Changes code artifact themes (comments, logs, language porting, bug fixes).

### Special Function Nodes
- **webSearch**: Performs web search.
- **routePostWebSearch**: Routes to the next node based on web search results.
- **customAction**: Handles user-defined quick actions.
- **replyToGeneralInput**: Responds to general input without artifact generation/modification.

### Post-Processing Nodes
- **generateFollowup**: Generates follow-up messages after artifact generation.
- **reflect**: Reflects on conversations and artifacts and stores them in memory.
- **cleanState**: Cleans state after processing.
- **generateTitle**: Generates conversation titles (for first conversation).
- **summarizer**: Summarizes messages when they become too long.

## Flow Description

1. **Start**: All requests start at the `generatePath` node.
2. **Routing**: `generatePath` routes to appropriate nodes based on request type.
3. **Web Search Path**: When web search is needed, artifacts are generated or rewritten based on search results.
4. **Artifact Processing**: Most artifact-related nodes move to `generateFollowup` after processing.
5. **Reflection and Cleanup**: After all processing is complete, reflection is performed and state is cleaned.
6. **Conditional Termination**: Moves to title generation, summarization, or termination based on message length and conversation state.

## Subgraph Diagrams

Open Canvas uses multiple subgraphs. Diagrams for each subgraph can be found in the README of the respective directory:

- **[Reflection Graph](./../reflection/README.md)**: Analyzes conversations and artifacts to generate style rules and memories
- **[Web Search Graph](./../web_search/README.md)**: Determines if web search is needed and performs search
- **[Summarizer Graph](./../summarizer/README.md)**: Summarizes long conversation messages
- **[Thread Title Graph](./../thread_title/README.md)**: Automatically generates conversation titles
