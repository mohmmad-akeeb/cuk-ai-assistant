# Architecture

> **Full system design document.** Covers module map, data flow, design principles, deployment topology, and caching strategy.
>
> See [`INDEX.md`](./INDEX.md) for the complete documentation table of contents.

---

## 1. System Overview

The CUK RAG Assistant is a retrieval-augmented generation chatbot for the Central University of Kashmir. It scrapes the university website, ingests documents into a hybrid vector store, and answers student queries with citation-grounded responses.

The system has **three subsystems** that run at different times and serve different purposes:

```mermaid
flowchart TB
    subgraph OFFLINE["A. Ingestion Pipeline — offline batch"]
        CRAWL["1. Crawl<br/>cuk-crawl"]
        PARSE["2. Parse<br/>cuk-parse"]
        NORM["3. Normalize<br/>reconcile + PII"]
        CHUNK["4. Chunk<br/>cuk-ingest"]
        INDEX["5. Embed + Index<br/>cuk-index"]

        CRAWL --> PARSE --> NORM --> CHUNK --> INDEX
    end

    subgraph RUNTIME["B. Request Pipeline — runtime"]
        USER["User Query"]
        GUARD["Input Guardrails"]
        ROUTE["Routing + Slot Fill"]
        RETR["Hybrid Retrieval"]
        RERANK["Reranking"]
        LLM["LLM Generation"]
        OUTGUARD["Output Guardrails + Citations"]
        RESP["Streamed Response"]

        USER --> GUARD --> ROUTE --> RETR --> RERANK --> LLM --> OUTGUARD --> RESP
    end

    subgraph INFRA["C. Infrastructure — cross-cutting"]
        FACTORY["DI Factory"]
        CONFIG["Config + Env"]
        SESSION["Session Store<br/>SQLite WAL"]
        TELEMETRY["Telemetry Sinks"]
        API["FastAPI REST + SSE"]
        UI["Chainlit UI"]
    end

    INDEX -.->|"LanceDB tables"| RETR
    FACTORY -.->|"wires all components"| RUNTIME
    TELEMETRY -.->|"spans + failures"| RUNTIME
    SESSION -.->|"chat history"| RUNTIME
    API -.->|"serves"| RUNTIME
    UI -.->|"renders"| RUNTIME

    style OFFLINE fill:#1a3a1a,color:#fff
    style RUNTIME fill:#1a2a3a,color:#fff
    style INFRA fill:#3a2a1a,color:#fff
```

**When each runs:**

| Subsystem | When | Trigger | Output |
|-----------|------|---------|--------|
| Ingestion | Offline, batch | `make ingest` / `cuk-crawl` / `cuk-index` | LanceDB tables + Tantivy FTS index |
| Request | Runtime, per user message | Chainlit UI or FastAPI endpoint | Streamed tokens + citation cards |
| Infrastructure | Always | Process startup | Configured orchestrator, API server |

---

## 2. Module Map

The `cuk_assistant/` package has 12 subpackages. Each follows the **Separation of Concerns (SoC)** principle — a module never reaches across boundaries into another module's domain.

```mermaid
flowchart LR
    subgraph CORE["core/ — interfaces, config, wiring"]
        PROT["protocols/<br/>7 Protocol interfaces"]
        REG["registry.py<br/>decorator registries"]
        FAC["factory.py<br/>DI assembly hub"]
        CFG["config.py<br/>Settings dataclass"]
    end

    subgraph INGEST["ingestion/ — offline pipeline"]
        CRAWL_MOD["crawl/<br/>node crawler"]
        PARSE_MOD["parsers/<br/>PDF + HTML + API"]
        NORM_MOD["normalization/<br/>reconciler + PII"]
        CHUNK_MOD["chunking/<br/>hierarchical chunker"]
        EMBED_MOD["embedding/<br/>FastEmbed adapter"]
        CLI_MOD["cli/<br/>crawl/parse/ingest/index"]
    end

    subgraph REQ["request pipeline"]
        PIPE["pipeline/<br/>orchestrator.py"]
        AGENT["agent/<br/>router + slot filler + session"]
        GUARD_MOD["guardrails/<br/>input + output + citation"]
        RETR_MOD["retrieval/<br/>LanceDB + FlashRank"]
        LLM_MOD["llm/<br/>Gemini + Groq + pool"]
    end

    subgraph IFACE["interfaces"]
        API_MOD["api/<br/>FastAPI REST + SSE"]
        UI_MOD["ui/<br/>Chainlit web app"]
    end

    subgraph XCUT["cross-cutting"]
        SCHEMAS["schemas/<br/>Pydantic data models"]
        OBS["observability/<br/>telemetry + failure attribution"]
        EVALS["evals/<br/>golden dataset + evaluator"]
    end

    FAC --> PIPE
    FAC --> RETR_MOD
    FAC --> LLM_MOD
    FAC --> GUARD_MOD
    FAC --> AGENT
    FAC --> OBS

    PIPE --> GUARD_MOD
    PIPE --> AGENT
    PIPE --> RETR_MOD
    PIPE --> LLM_MOD
    PIPE --> OBS

    PROT -.->|"contract"| RETR_MOD
    PROT -.->|"contract"| LLM_MOD
    PROT -.->|"contract"| GUARD_MOD
    PROT -.->|"contract"| AGENT
    PROT -.->|"contract"| OBS

    EMBED_MOD --> RETR_MOD
    SCHEMAS -.->|"shared models"| INGEST
    SCHEMAS -.->|"shared models"| REQ

    API_MOD --> PIPE
    UI_MOD --> PIPE

    style CORE fill:#2a2a3a,color:#fff
    style INGEST fill:#1a3a1a,color:#fff
    style REQ fill:#1a2a3a,color:#fff
    style IFACE fill:#3a2a1a,color:#fff
    style XCUT fill:#3a1a2a,color:#fff
```

### Module responsibilities

| Module | Responsibility | Key files | Never does |
|--------|--------------|-----------|------------|
| `core/protocols/` | Protocol interface definitions (7 contracts) | `storage.py`, `llm.py`, `session.py`, `telemetry.py`, `reranker.py`, `ingestion.py`, `document_parser.py` | Contains implementations |
| `core/registry.py` | Decorator-based component registration | `register_vector_store`, `register_embedding_model`, etc. | Instantiates components |
| `core/factory.py` | Dependency injection — wires all components | `create_rag_orchestrator()` | Contains business logic |
| `core/config.py` | Environment-driven configuration | `Settings` dataclass, `load_settings()` | Reads secrets at module level |
| `ingestion/crawl/` | Scrape CUK website (Angular SPA) | `node_crawler.py`, `direct_client.py`, `pdf_extractor.py` | Calls vector DBs or LLMs |
| `ingestion/parsers/` | Parse PDF/HTML/API into structured records | `pdf_parser.py`, `html_parser.py`, `docling_adapter.py` | Calls vector DBs or LLMs |
| `ingestion/normalization/` | Reconcile metadata, scrub PII, detect deltas | `reconciler.py`, `sanitizer.py`, `delta_detector.py` | Performs retrieval |
| `ingestion/chunking/` | Hierarchical AST markdown chunking | `hierarchical_chunker.py` | Generates embeddings |
| `ingestion/embedding/` | Dense vector embeddings | `fastembed_adapter.py` | Performs retrieval |
| `agent/` | Intent routing, slot filling, session memory | `router.py`, `slot_filler.py`, `session_store.py` | Performs retrieval or LLM generation |
| `guardrails/` | Input/output safety, PII scrub, citation verify | `input_guard.py`, `output_guard.py`, `citation_verifier.py` | Generates responses |
| `retrieval/` | Hybrid vector + BM25 storage and reranking | `lancedb_store.py`, `coordinator.py`, `flashrank_reranker.py` | Formulates conversational responses |
| `llm/` | LLM inference + provider failover | `gemini_client.py`, `groq_client.py`, `pool.py` | Performs retrieval |
| `pipeline/orchestrator.py` | Workflow orchestration via injected protocols | `RAGOrchestrator` | Instantiates concrete classes |
| `api/` | FastAPI REST + SSE transport | `main.py`, `routes/chat.py`, `routes/sessions.py` | Contains business logic |
| `ui/` | Chainlit web presentation | `app.py` | Contains business logic |
| `schemas/` | Pure Pydantic data models | `metadata.py`, `chunks.py`, `chat.py`, `retrieval.py`, `llm.py` | Imports database or vendor libs |
| `observability/` | Telemetry sinks + failure attribution | `in_memory_sink.py`, `langfuse_sink.py`, `failure_attribution.py` | Mutates pipeline behavior |
| `evals/` | Offline evaluation harness | `evaluator.py`, `query_miner.py`, `cli.py` | Runs during request flow |

---

## 3. Design Principles

Three invariants govern every file in the codebase (enforced via `GEMINI.md`):

### 3.1 Separation of Concerns (SoC)

Each module has one job. The ingestion pipeline never calls the LLM. The retrieval layer never formulates responses. The orchestrator never instantiates concrete classes. This means you can test, replace, or rewrite any module without touching the others.

### 3.2 Dependency Injection (DI)

Components receive their dependencies through constructors as abstract `Protocol` types. No module imports a concrete adapter class — except `core/factory.py`, which is the single place where concrete classes are instantiated and wired together.

```mermaid
flowchart TD
    subgraph PROTOCOLS["core/protocols/ — abstract contracts"]
        VSP["VectorStoreProtocol"]
        EMP["EmbeddingModelProtocol"]
        LLP["LLMClientProtocol"]
        RRK["RerankerProtocol"]
        SSP["SessionStoreProtocol"]
        TSP["TelemetrySinkProtocol"]
    end

    subgraph CONCRETE["concrete adapters"]
        LDB["LanceDBStore"]
        FEB["FastEmbedAdapter"]
        GEM["GeminiClient"]
        GRQ["GroqClient"]
        FRR["FlashRankReranker"]
        SQL["SQLiteSessionStore"]
        LFS["LangfuseTelemetrySink"]
        IMS["InMemoryTelemetrySink"]
    end

    subgraph FACTORY["core/factory.py — single wiring point"]
        CFO["create_rag_orchestrator()"]
    end

    subgraph CONSUMER["pipeline/orchestrator.py"]
        ORC["RAGOrchestrator"]
    end

    LDB -.->|"implements"| VSP
    FEB -.->|"implements"| EMP
    GEM -.->|"implements"| LLP
    GRQ -.->|"implements"| LLP
    FRR -.->|"implements"| RRK
    SQL -.->|"implements"| SSP
    LFS -.->|"implements"| TSP
    IMS -.->|"implements"| TSP

    CFO -->|"instantiates"| LDB
    CFO -->|"instantiates"| FEB
    CFO -->|"instantiates"| GEM
    CFO -->|"instantiates"| GRQ
    CFO -->|"instantiates"| FRR
    CFO -->|"instantiates"| SQL
    CFO -->|"instantiates"| LFS
    CFO -->|"instantiates"| IMS
    CFO -->|"injects into"| ORC

    ORC -->|"uses"| VSP
    ORC -->|"uses"| LLP
    ORC -->|"uses"| RRK
    ORC -->|"uses"| SSP
    ORC -->|"uses"| TSP

    style PROTOCOLS fill:#2a2a3a,color:#fff
    style CONCRETE fill:#1a3a1a,color:#fff
    style FACTORY fill:#3a2a1a,color:#fff
    style CONSUMER fill:#1a2a3a,color:#fff
```

### 3.3 Open/Closed Principle (OCP)

New adapters are added by creating a class and decorating it with the appropriate registry. Zero modifications to existing pipeline code are needed.

```python
# To add a new vector store:
@register_vector_store("qdrant")
class QdrantStore(VectorStoreProtocol):
    def hybrid_search(self, ...): ...

# To add a new LLM provider:
class OpenAIClient(LLMClientProtocol):
    async def generate_answer(self, ...): ...

# Factory picks them up automatically — no orchestrator changes needed.
```

---

## 4. Data Flow

### 4.1 Ingestion data flow (offline)

```mermaid
flowchart LR
    WEB["CUK Website<br/>cukashmir.ac.in"]
    RAW["Raw Assets<br/>data/raw/"]
    MANIFEST["manifest.jsonl"]
    DOCS["documents.jsonl"]
    CANON["documents_canonical.jsonl"]
    CHUNKS["chunks.jsonl"]
    LAN["LanceDB<br/>data/lancedb/"]

    WEB -->|"cuk-crawl crawl"| RAW
    WEB -->|"cuk-crawl build-nodes"| MANIFEST
    RAW -->|"cuk-parse"| DOCS
    DOCS -->|"consolidate_documents.py"| CANON
    CANON -->|"cuk-ingest"| CHUNKS
    CHUNKS -->|"cuk-index"| LAN

    style WEB fill:#3a1a1a,color:#fff
    style LAN fill:#1a3a1a,color:#fff
```

**Data formats at each stage:**

| Stage | File | Format | Key fields |
|-------|------|--------|------------|
| Crawl | `data/raw/pdf/`, `data/raw/html/` | Binary PDFs, HTML files | Scraped assets |
| Crawl | `data/raw/manifest.jsonl` | JSONL | `asset_id`, `asset_type`, `source_url`, `provenance` |
| Parse | `data/processed/documents.jsonl` | JSONL | `text`, `metadata` (universal schema) |
| Normalize | `data/processed/documents_canonical.jsonl` | JSONL | Deduped, reconciled, PII-scrubbed |
| Chunk | `data/processed/chunks.jsonl` | JSONL | `chunk_id`, `doc_id`, `text`, `chunk_type`, `parent_chunk_id`, `metadata` |
| Index | `data/lancedb/chunks.lance` | LanceDB (Arrow) | `chunk_id`, `vector`, `text`, `metadata_json`, top-level columns |
| Index | `data/lancedb/parent_sections.lance` | LanceDB (Arrow) | `parent_chunk_id`, `full_section_text`, `child_chunk_ids` |

### 4.2 Request data flow (runtime)

```mermaid
flowchart TD
    MSG["User message<br/>'What is the syllabus of DBMS?'"]
    IG["InputGuard.validate()"]
    IG_RESULT{"Safe + in domain?"}

    ROUTER["AdaptiveRouter.route()"]
    ROUTE_RESULT{"Route destination?"}

    SLOT_FILL{"Mandatory slots<br/>complete?"}
    CHIP["Emit slot_prompt<br/>with quick-reply chips"]
    FILTER["Build metadata filter<br/>doc_type == 'syllabus' AND ..."]

    RETRIEVE["HybridRetrievalCoordinator.retrieve()"]
    RERANK["FlashRankReranker.rerank()"]

    LLM["LLMProviderPool.generate_answer()"]
    LLM_RESULT{"Generation succeeded?"}

    CIT_VERIFY["VerbatimCitationVerifier.verify()"]
    CIT_RESULT{"Citations grounded?"}

    OUT_GUARD["OutputGuard.scrub() + safety check"]
    CARDS["Build citation cards"]
    STREAM["Stream tokens + cards to client"]
    PERSIST["Persist to SQLite session"]

    MSG --> IG --> IG_RESULT
    IG_RESULT -->|"No"| DEFLECT["Deflection message"]
    IG_RESULT -->|"Yes"| ROUTER --> ROUTE_RESULT

    ROUTE_RESULT -->|"DEFLECTED"| DEFLECT
    ROUTE_RESULT -->|"DIRECT_CONVERSATIONAL"| GREET["Greeting response"]
    ROUTE_RESULT -->|"FACETED_ACADEMIC"| SLOT_FILL

    SLOT_FILL -->|"No"| CHIP
    SLOT_FILL -->|"Yes"| FILTER --> RETRIEVE

    RETRIEVE --> RERANK --> LLM --> LLM_RESULT
    LLM_RESULT -->|"No"| FALLBACK["Fallback text"]
    LLM_RESULT -->|"Yes"| CIT_VERIFY --> CIT_RESULT

    CIT_RESULT -->|"No"| REDACT["Redact unverified claims"]
    CIT_RESULT -->|"Yes"| OUT_GUARD

    REDACT --> OUT_GUARD
    FALLBACK --> OUT_GUARD

    OUT_GUARD --> CARDS --> STREAM --> PERSIST

    style DEFLECT fill:#3a1a1a,color:#fff
    style GREET fill:#3a1a1a,color:#fff
    style CHIP fill:#3a2a1a,color:#fff
    style STREAM fill:#1a3a1a,color:#fff
```

---

## 5. Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| Language | Python | 3.12+ | Application code |
| Package manager | uv | 0.13+ | Dependency management, build |
| Web framework (API) | FastAPI | 0.163+ | REST + SSE endpoints |
| Web framework (UI) | Chainlit | 2.12+ | Chat interface |
| Vector store | LanceDB | 0.41+ | Hybrid dense + sparse search |
| Full-text search | Tantivy | 0.27+ | BM25 lexical index |
| Embeddings | FastEmbed | 0.9+ | BGE-small-en-v1.5 (384-dim) |
| Reranker | FlashRank | 0.2+ | ms-marco-TinyBERT-L-2-v2 |
| LLM (primary) | Google Gemini | — | gemini-flash-latest |
| LLM (fallback) | Groq | — | qwen3.8-27b / llama-3.3-70b |
| Data models | Pydantic | 2.14+ | Schemas, validation, coercion |
| Session store | SQLite | — | WAL mode conversation memory |
| Observability | Logfire + Langfuse + Phoenix | — | Telemetry, tracing, failure attribution |
| PDF parsing | PyMuPDF + Docling | — | PDF text + table extraction |
| HTML parsing | BeautifulSoup + lxml | — | HTML scraping |
| Containerization | Docker + docker-compose | — | Multi-stage build, dual-service deploy |
| Linting | Ruff | 0.17+ | Code quality + formatting |
| Testing | pytest + pytest-asyncio | — | Unit + integration tests |

---

## 6. Deployment Topology

### 6.1 Docker Compose (production)

```mermaid
flowchart TB
    subgraph HOST["Docker Host"]
        subgraph API_SVC["Service: api (FastAPI)"]
            API_APP["uvicorn<br/>cuk_assistant.api.main:app<br/>port 8000"]
            API_ORC["RAGOrchestrator<br/>(singleton via factory)"]
            API_RET["LanceDBStore"]
            API_LLM["LLMProviderPool<br/>Gemini → Groq"]
            API_SES["SQLiteSessionStore<br/>sessions.db"]
        end

        subgraph UI_SVC["Service: ui (Chainlit)"]
            UI_APP["chainlit run<br/>cuk_assistant/ui/app.py<br/>port 8001"]
            UI_ORC["RAGOrchestrator<br/>(singleton via factory)"]
        end

        subgraph VOLUME["Volume: cuk_data"]
            LAN_DATA["data/lancedb/<br/>chunks.lance + parent_sections.lance"]
            SQLITE["data/sessions.db"]
        end

        subgraph CACHE["Model Cache (pre-warmed)"]
            FE_CACHE["FastEmbed cache<br/>/opt/model_cache/fastembed<br/>BGE-small-en-v1.5"]
            FR_CACHE["FlashRank cache<br/>/opt/model_cache/flashrank<br/>ms-marco-TinyBERT"]
        end
    end

    EXT_GEM["Google Gemini API"]
    EXT_GROQ["Groq API"]
    EXT_LF["Logfire / Langfuse<br/>(optional)"]

    API_APP --> API_ORC
    UI_APP --> UI_ORC

    API_ORC --> API_RET
    API_ORC --> API_LLM
    API_ORC --> API_SES

    API_RET --> LAN_DATA
    API_SES --> SQLITE
    UI_ORC -.->|"shared volume"| LAN_DATA

    API_LLM -->|"primary"| EXT_GEM
    API_LLM -->|"failover"| EXT_GROQ
    UI_ORC -.->|"LLM calls"| EXT_GEM

    API_ORC -.->|"telemetry"| EXT_LF
    UI_ORC -.->|"telemetry"| EXT_LF

    style API_SVC fill:#1a2a3a,color:#fff
    style UI_SVC fill:#3a2a1a,color:#fff
    style VOLUME fill:#1a3a1a,color:#fff
    style CACHE fill:#2a2a3a,color:#fff
```

### 6.2 Local development

```bash
# Ingestion (offline)
make ingest          # chunk + embed + index

# API server
make run-api         # uvicorn on :8000

# UI server
make ui              # chainlit on :8001

# Tests
make test-unit       # pytest tests/unit/
```

### 6.3 Environment variables

| Variable | Default | Used by | Purpose |
|----------|---------|---------|---------|
| `GEMINI_API_KEY` | — | `llm/gemini_client.py` | Primary LLM provider |
| `GROQ_API_KEY` | — | `llm/groq_client.py` | Fallback LLM provider |
| `GEMINI_MODEL` | `gemini-flash-latest` | Factory | Gemini model name |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Factory | Groq model name |
| `LANCEDB_DIR` | `data/lancedb` | `LanceDBStore` | Vector store path |
| `SQLITE_DB_PATH` | `data/sessions.db` | `SQLiteSessionStore` | Session DB path |
| `FASTEMBED_CACHE_PATH` | — | `FastEmbedAdapter` | Embedding model cache |
| `FLASHRANK_CACHE_PATH` | — | `FlashRankReranker` | Reranker model cache |
| `LOGFIRE_TOKEN` | — | Telemetry | Logfire integration |
| `LANGFUSE_PUBLIC_KEY` | — | Telemetry | Langfuse integration |
| `LANGFUSE_SECRET_KEY` | — | Telemetry | Langfuse integration |
| `PHOENIX_COLLECTOR_ENDPOINT` | — | Telemetry | Phoenix/Arize integration |
| `BASE_URL` | `https://www.cukashmir.ac.in` | Crawler | Target website |
| `CONTACT_EMAIL` | — | API | Rate limit contact |

---

## 7. Caching Strategy

The system has four caching layers, each serving a different purpose:

```mermaid
flowchart TB
    subgraph LAYER1["Layer 1: HTTP Response Cache"]
        HTTP["core/http_cache.py<br/>in-memory LRU<br/>caches crawler HTTP responses"]
    end

    subgraph LAYER2["Layer 2: Model Cache (disk)"]
        FE["FastEmbed ONNX models<br/>/opt/model_cache/fastembed/<br/>BAAI/bge-small-en-v1.5"]
        FR["FlashRank ONNX models<br/>/opt/model_cache/flashrank/<br/>ms-marco-TinyBERT-L-2-v2"]
    end

    subgraph LAYER3["Layer 3: LanceDB (disk)"]
        LAN["data/lancedb/chunks.lance<br/>vectors + text + metadata_json<br/>columnar Arrow format"]
        FTS["Tantivy BM25 index<br/>full-text lexical index<br/>embedded in LanceDB"]
        PAR["data/lancedb/parent_sections.lance<br/>parent chunk context expansion"]
    end

    subgraph LAYER4["Layer 4: SQLite Session (disk)"]
        SES["data/sessions.db<br/>WAL mode<br/>conversation history + summaries"]
    end

    CRAWLER["Crawler"] -->|"GET requests"| HTTP
    EMBED["Embedding pipeline"] -->|"loads ONNX once"| FE
    RERANK["Reranking"] -->|"loads ONNX once"| FR
    RETRIEVAL["Hybrid retrieval"] -->|"vector + FTS queries"| LAN
    RETRIEVAL -->|"BM25 queries"| FTS
    RETRIEVAL -->|"context expansion"| PAR
    ORCHESTRATOR["RAGOrchestrator"] -->|"chat history"| SES

    style LAYER1 fill:#3a1a2a,color:#fff
    style LAYER2 fill:#2a2a3a,color:#fff
    style LAYER3 fill:#1a3a1a,color:#fff
    style LAYER4 fill:#3a2a1a,color:#fff
```

| Layer | Type | Location | Lifetime | Invalidated by |
|-------|------|----------|----------|---------------|
| HTTP cache | In-memory LRU | Process memory | Process lifetime | TTL expiry |
| Model cache | Disk (ONNX) | `/opt/model_cache/` | Until image rebuild | Docker rebuild |
| LanceDB | Disk (Arrow) | `data/lancedb/` | Until re-indexing | `cuk-index` command |
| SQLite session | Disk (WAL) | `data/sessions.db` | Manual deletion | Session delete API |

### 7.1 Model pre-warming in Docker

The Dockerfile pre-warms both ONNX models during the builder stage so the runtime image starts without cold-start latency:

```dockerfile
# Builder stage pre-warms models into /opt/model_cache/
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5', ...)"
RUN python -c "from flashrank import Ranker; Ranker(model_name='ms-marco-TinyBERT-L-2-v2', ...)"
```

---

## 8. Entry Points

```mermaid
flowchart LR
    subgraph ENTRY["Entry points"]
        CLI_CRAWL["cuk-crawl"]
        CLI_PARSE["cuk-parse"]
        CLI_INGEST["cuk-ingest"]
        CLI_INDEX["cuk-index"]
        CLI_EVAL["cuk-eval"]
        CLI_UI["cuk-ui"]
        UVICORN["uvicorn<br/>cuk_assistant.api.main:app"]
        CHAINLIT["chainlit run<br/>cuk_assistant/ui/app.py"]
    end

    subgraph TARGET["Target module"]
        CRAWL_MOD["ingestion/cli/crawl.py"]
        PARSE_MOD["ingestion/cli/parse.py"]
        INGEST_MOD["ingestion/cli/ingest.py"]
        INDEX_MOD["ingestion/cli/index.py"]
        EVAL_MOD["evals/cli.py"]
        UI_MOD["ui/app.py"]
        API_MOD["api/main.py"]
    end

    CLI_CRAWL --> CRAWL_MOD
    CLI_PARSE --> PARSE_MOD
    CLI_INGEST --> INGEST_MOD
    CLI_INDEX --> INDEX_MOD
    CLI_EVAL --> EVAL_MOD
    CLI_UI --> UI_MOD
    UVICORN --> API_MOD
    CHAINLIT --> UI_MOD

    style ENTRY fill:#3a2a1a,color:#fff
    style TARGET fill:#1a2a3a,color:#fff
```

| Command | Entry point | Subsystem | Purpose |
|---------|------------|-----------|---------|
| `cuk-crawl crawl` | `ingestion/cli/crawl.py` | Ingestion | Scrape CUK website |
| `cuk-crawl build-nodes` | `ingestion/cli/crawl.py` | Ingestion | Build navigation hierarchy |
| `cuk-crawl save-pdfs` | `ingestion/cli/crawl.py` | Ingestion | Download PDFs |
| `cuk-parse` | `ingestion/cli/parse.py` | Ingestion | Parse raw assets to documents |
| `cuk-ingest` | `ingestion/cli/ingest.py` | Ingestion | Chunk documents |
| `cuk-index` | `ingestion/cli/index.py` | Ingestion | Embed + index into LanceDB |
| `cuk-eval run` | `evals/cli.py` | Evaluation | Run golden dataset benchmark |
| `cuk-ui` | `ui/app.py` | UI | Launch Chainlit web UI |
| `uvicorn cuk_assistant.api.main:app` | `api/main.py` | API | Launch FastAPI server |

---

## 9. Known Issues and Gaps

These are documented in detail in their respective module docs:

| Issue | Where documented | Status |
|-------|-----------------|--------|
| Metadata filter column mismatch — slot-filler builds filters against `program`, `batch_year`, `semester` etc., but these fields live inside `metadata_json`, not as top-level LanceDB columns. Filters silently stripped by sanitizer. | [`pipeline/routing-slots.md`](./pipeline/routing-slots.md) | **Broken** |
| Slot selection chip → nothing happens — UI dispatches `on_slot_selected` but the orchestrator re-evaluates from scratch instead of continuing slot filling. | [`api-ui/ui.md`](./api-ui/ui.md) | **Broken** |
| Obvious slots (department inferred from course) still asked — no inference logic to skip department when course implies it. | [`pipeline/routing-slots.md`](./pipeline/routing-slots.md) | **Missing feature** |
| `README.md` referenced in `pyproject.toml` but doesn't exist — `uv` build fails. | — | **Broken reference** |
| `chainlit.md` referenced in Dockerfile but doesn't exist — Docker build fails. | — | **Broken reference** |

---

## 10. Further Reading

| Topic | Document |
|-------|----------|
| Ingestion pipeline overview | [`ingestion/overview.md`](./ingestion/overview.md) |
| Crawler internals | [`ingestion/crawl.md`](./ingestion/crawl.md) |
| Parse + normalize | [`ingestion/parse-normalize.md`](./ingestion/parse-normalize.md) |
| Chunk + embed + index | [`ingestion/chunk-index.md`](./ingestion/chunk-index.md) |
| Request pipeline overview | [`pipeline/overview.md`](./pipeline/overview.md) |
| Guardrails | [`pipeline/guardrails.md`](./pipeline/guardrails.md) |
| Routing + slot filling | [`pipeline/routing-slots.md`](./pipeline/routing-slots.md) |
| Retrieval + reranking | [`pipeline/retrieval-rerank.md`](./pipeline/retrieval-rerank.md) |
| LLM failover | [`pipeline/llm-failover.md`](./pipeline/llm-failover.md) |
| Session memory | [`pipeline/session.md`](./pipeline/session.md) |
| DI + factory | [`core/di-factory.md`](./core/di-factory.md) |
| Schemas | [`core/schemas.md`](./core/schemas.md) |
| API | [`api-ui/api.md`](./api-ui/api.md) |
| Chainlit UI | [`api-ui/ui.md`](./api-ui/ui.md) |
| Telemetry | [`observability/telemetry.md`](./observability/telemetry.md) |
| Deployment | [`deployment/deployment.md`](./deployment/deployment.md) |
| Evaluation | [`evals/evaluation.md`](./evals/evaluation.md) |
