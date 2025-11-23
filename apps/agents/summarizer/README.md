# Summarizer Graph

The Summarizer graph is a subgraph that compresses context by summarizing conversation messages when they become too long.

## Graph Structure

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	summarize(summarize)
	__end__([<p>__end__</p>]):::last
	__start__ --> summarize;
	summarize --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Node Description

- **summarize**: Summarizes all conversation messages into a single summary message. The summary message is not visible to users and is used as context in subsequent conversations.

## Flow

1. **Start**: `__start__` → `summarize`
2. **Summarize**: Use LLM to summarize all messages
3. **Generate**: Add summarized message to `_messages` (not visible to users)
4. **End**: `summarize` → `__end__`

## Usage Location

This graph is called from the `summarizer` node in the `open_canvas` main graph. It is automatically called when the total message length exceeds 300,000 characters.

