# Schemas

> **Pydantic v2 data models shared across ingestion and request pipelines.**
>
> Related: [DI + Factory](./di-factory.md) · [Architecture](../architecture.md)

---

## 1. Schema Inheritance Tree

```mermaid
flowchart TD
    subgraph METADATA["schemas/metadata.py — Polymorphic metadata"]
        BASE["UniversalDocMetadata<br/>(frozen, extra=forbid)<br/>doc_id, title, source_url,<br/>school, department, node_path,<br/>published_date, academic_year,<br/>content_hash, scraped_at"]

        SYL["SyllabusDocMetadata<br/>program, batch_year, semester,<br/>course_code, course_title, credits"]
        RES["ResultDocMetadata<br/>exam_session, notification_number,<br/>result_type, program, declaration_date"]
        ADM["AdmissionDocMetadata<br/>admission_year, program, stage,<br/>intake_capacity"]
        NOT["NoticeDocMetadata<br/>reference_number, issuing_office,<br/>is_urgent, expiry_date"]
        TEN["TenderDocMetadata<br/>tender_number, nit_date,<br/>closing_date, emd_amount"]
        ORD["OrdinanceDocMetadata<br/>ordinance_number, subject,<br/>governing_body, effective_date"]
        FAC["FacultyDocMetadata<br/>employee_name, designation,<br/>email, qualifications, research_areas"]
        GEN["GeneralDocMetadata<br/>(fallback — no extra fields)"]
    end

    BASE --> SYL
    BASE --> RES
    BASE --> ADM
    BASE --> NOT
    BASE --> TEN
    BASE --> ORD
    BASE --> FAC
    BASE --> GEN

    SYL -.->|"doc_type='syllabus'"| SYL
    RES -.->|"doc_type='result'"| RES
    ADM -.->|"doc_type='admission'"| ADM
    NOT -.->|"doc_type='notice'"| NOT
    TEN -.->|"doc_type='tender'"| TEN
    ORD -.->|"doc_type='ordinance'"| ORD
    FAC -.->|"doc_type='faculty'"| FAC
    GEN -.->|"doc_type='general'"| GEN

    style BASE fill:#1a2a3a,color:#fff
    style SYL fill:#1a3a1a,color:#fff
    style GEN fill:#3a2a3a,color:#fff
```

### Discriminator

All metadata models use `doc_type` as the polymorphic discriminator. The `parse_document_metadata()` function routes to the correct model:

```python
DocumentMetadataUnion = Annotated[
    SyllabusDocMetadata | ResultDocMetadata | AdmissionDocMetadata
    | NoticeDocMetadata | TenderDocMetadata | OrdinanceDocMetadata
    | FacultyDocMetadata | GeneralDocMetadata,
    Field(discriminator="doc_type"),
]
```

### Invariants

- `extra="forbid"` — no unknown fields allowed
- `frozen=True` — immutable after creation
- `extra="forbid"` on all models prevents field leakage

---

## 2. Chunk Schemas

```mermaid
flowchart TB
    subgraph CHUNKS["schemas/chunks.py"]
        CT["ChunkType (StrEnum)<br/>• PARAGRAPH<br/>• MARKDOWN_TABLE<br/>• HEADING<br/>• LIST_ITEM<br/>• CODE_OR_FORMULA"]

        CR["ChunkRecord<br/>(frozen, extra=forbid)<br/>chunk_id, doc_id, chunk_index,<br/>chunk_type, text_content, token_count,<br/>page_number, section_heading,<br/>heading_path (breadcrumb),<br/>parent_chunk_id,<br/>prev_chunk_id ↔ next_chunk_id,<br/>metadata (dict)"]

        PC["ParentChunkContainer<br/>(frozen, extra=forbid)<br/>parent_chunk_id, doc_id,<br/>heading_title, heading_level,<br/>section_token_count,<br/>full_section_text,<br/>child_chunk_ids (list)"]
    end

    CT --> CR
    CR -.->|"parent link"| PC
    PC -.->|"contains"| CR

    style CT fill:#3a2a1a,color:#fff
    style CR fill:#1a3a1a,color:#fff
    style PC fill:#1a2a3a,color:#fff
```

### ChunkRecord auto-fill

The `_fill_text_and_hash` validator ensures `text_content` and `text` are always synchronized, and `content_hash` is auto-computed:

```python
@model_validator(mode="before")
def _fill_text_and_hash(cls, data):
    # If text_content is None but text exists, copy text → text_content
    # If text is None but text_content exists, copy text_content → text
    # If content_hash is missing, compute SHA-256 of text_content
```

---

## 3. Request/Response Schemas

```mermaid
flowchart LR
    subgraph CHAT["schemas/chat.py"]
        REQ["ChatRequest<br/>query (or message alias),<br/>session_id, slots, user_context"]
        RES["ChatResponse<br/>message_id, session_id, role,<br/>content, quick_replies,<br/>citations, metadata"]
        FB["FeedbackRequest<br/>trace_id, score (-1|+1),<br/>feedback_category, comment"]
        CC["CitationCard<br/>citation_id, doc_id, chunk_id,<br/>title, source_url, doc_type,<br/>page_number, section_heading,<br/>quoted_snippet, is_table, table_markdown"]
        TR["TurnResult<br/>message_id, session_id, role,<br/>content, quick_replies,<br/>citations, metadata, diagnostic_code"]
    end

    subgraph LLM["schemas/llm.py"]
        AWC["AnswerWithCitations<br/>(frozen, extra=forbid)<br/>direct_answer,<br/>quoted_snippets (list[str]),<br/>citation_chunk_ids (list[str]),<br/>confidence_score (float)"]
    end

    subgraph RETR["schemas/retrieval.py"]
        SC["ScoredChunk<br/>(frozen, extra=forbid)<br/>chunk (ChunkRecord|dict),<br/>score, dense_score, lexical_score,<br/>rrf_rank, scope_relaxed, regex_fallback<br/>Properties: chunk_id, text_content, metadata"]
    end

    subgraph DOC["schemas/document.py"]
        DOC_M["Document<br/>text: str<br/>metadata: dict[str, Any]"]
    end

    REQ -->|"generates"| TR
    AWC -->|"cited in"| CC
    CC -->|"included in"| RES
    SC -->|"context for"| AWC

    style CHAT fill:#1a2a3a,color:#fff
    style LLM fill:#1a3a1a,color:#fff
    style RETR fill:#3a2a1a,color:#fff
    style DOC fill:#3a1a2a,color:#fff
```

### ChatRequest field harmonization

The `ChatRequest` model accepts either `query` or `message` as the input field. A `model_validator` harmonizes them:

```python
@model_validator(mode="before")
def harmonize_fields(cls, values):
    if not values.get("query") and values.get("message"):
        values["query"] = values["message"]
    elif not values.get("message") and values.get("query"):
        values["message"] = values["query"]
    return values
```

### FeedbackRequest validation

Score must be exactly `-1` (downvote) or `+1` (upvote):

```python
@field_validator("score")
def validate_score(cls, v):
    if v not in (-1, 1):
        raise ValueError("Score must be strictly -1 or 1.")
    return v
```

---

## 4. ScoredChunk Properties

The `ScoredChunk` provides convenience properties for accessing chunk fields regardless of whether the chunk is a `ChunkRecord` object or a dict:

```python
@property
def chunk_id(self) -> str:
    if isinstance(self.chunk, dict):
        return str(self.chunk.get("chunk_id", ""))
    return str(getattr(self.chunk, "chunk_id", ""))

@property
def text_content(self) -> str:
    if isinstance(self.chunk, dict):
        return str(self.chunk.get("text_content", ""))
    return str(getattr(self.chunk, "text_content", ""))

@property
def metadata(self) -> dict[str, Any]:
    if isinstance(self.chunk, dict):
        return self.chunk.get("metadata", {})
    return getattr(self.chunk, "metadata", {})
```

---

## 5. Key Files

| File | Schemas |
|------|--------|
| `schemas/metadata.py` | `UniversalDocMetadata`, 7 domain schemas, `parse_document_metadata()` |
| `schemas/chunks.py` | `ChunkType`, `ChunkRecord`, `ParentChunkContainer` |
| `schemas/chat.py` | `ChatRequest`, `ChatResponse`, `FeedbackRequest`, `CitationCard`, `TurnResult` |
| `schemas/llm.py` | `AnswerWithCitations` |
| `schemas/retrieval.py` | `ScoredChunk` |
| `schemas/document.py` | `Document` |
