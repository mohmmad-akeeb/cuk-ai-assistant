# Data Schemas

## Overview
All data models are Pydantic schemas defined in `cuk_assistant/schemas/`.

## Core Schemas

### 1. Document Schema (`document.py`)
Defines the structure of ingested documents.

### 2. Chunk Schema (`chunks.py`)
Defines how documents are split into searchable units (`ChunkRecord`).

### 3. LLM Schema (`llm.py`)
- `AnswerWithCitations`: Enforces structured output from LLMs (`answer: str, citations: list[str]`).

### 4. Retrieval Schema (`retrieval.py`)
- `ScoredChunk`: Represents a chunk returned by the vector store with a relevance score.


### 5. Chat Schema (`chat.py`)
Models for user input, session state, and response payloads.

---

## Related Documentation
- [System Requirements](requirements.md)
- [System Architecture](architecture.md)
- [API Contracts](api_contracts.md)
