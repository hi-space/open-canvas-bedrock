# Reflection Graph

The Reflection graph is a subgraph that analyzes conversations and artifacts to generate user style rules and memories.

## Graph Structure

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	reflect(reflect)
	__end__([<p>__end__</p>]):::last
	__start__ --> reflect;
	reflect --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## Node Description

- **reflect**: Analyzes conversation messages and artifacts to generate style rules and user memories, and stores them.

## Flow

1. **Start**: `__start__` → `reflect`
2. **Reflect**: Use LLM to analyze conversations and artifacts and generate new style rules and memories
3. **Store**: Store generated reflections in memory store
4. **End**: `reflect` → `__end__`

## Usage Location

This graph is called from the `reflect` node in the `open_canvas` main graph.

