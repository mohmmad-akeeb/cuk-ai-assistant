# Retrieval + Reranking

> **Hybrid vector + BM25 search with cross-encoder reranking, scope fallback, and deterministic regex recovery.**
>
> Related: [Pipeline Overview](./overview.md) · [Chunk + Index](../ingestion/chunk-index.md)

---

## 1. Purpose

The `HybridRetrievalCoordinator.retrieve()` method is Step 4 of the request pipeline. It embeds the query, searches LanceDB with hybrid dense + sparse (BM25) fusion, reranks with a cross-encoder, and falls back gracefully when results are sparse or missing.

---

## 2. Retrieval Lifecycle

```mermaid
flowchart TD
    QUERY["User query"]
    FILTERS["Metadata filters<br/>(from slot-filler or slots dict)"]

    EMBED["Step 1: Query Embedding<br/>embedding_model.embed_query(query)<br/>→ 384-dim vector"]
    FORMAT["Step 2: Format WHERE filter<br/>format_where_filter(filters)"]
    HYBRID["Step 3: Hybrid Search<br/>vector_store.hybrid_search()<br/>top_k=30 candidates<br/>dense + BM25 via RRF fusion"]

    SCOPE_CHECK{"Results empty<br/>AND filter applied?"}
    RELAX["Step 3b: Scope Fallback<br/>Re-search with where_filter=None<br/>Global unfiltered search<br/>Tag: scope_relaxed=True"]
    EMPTY["Proceed with empty results"]

    RERANK["Step 4: Cross-Encoder Reranking<br/>flashrank_reranker.rerank()<br/>ms-marco-TinyBERT<br/>→ top_k=5 best candidates"]
    SORT["Fallback: Sort by score<br/>if no reranker available"]

    RELEVANCE{"Top score<br/>< 0.35 threshold?"}
    REGEX["Step 5: Deterministic Regex Fallback<br/>extract_circular_reference(query)<br/>→ vector_store.deterministic_regex_search()"]
    REGEX_CHECK{"Regex matches<br/>found?"}
    REGEX_WRAP["Wrap matches as ScoredChunk<br/>score=1.0, regex_fallback=True"]
    NO_REGEX["Tag: RETRIEVAL_EMPTY<br/>or CORPUS_MISSING_CONTENT"]

    EXPAND["Step 6: Parent Context Expansion<br/>For each candidate:<br/>→ get_parent_chunk(parent_chunk_id)<br/>→ Attach full_section_text to metadata<br/>→ Set scope_relaxed + regex_fallback flags"]

    RESULT["list[ScoredChunk] → Step 5 (LLM)"]

    QUERY --> EMBED --> FORMAT --> HYBRID
    FILTERS --> FORMAT
    HYBRID --> SCOPE_CHECK
    SCOPE_CHECK -->|"Yes"| RELAX --> RERANK
    SCOPE_CHECK -->|"No"| RERANK
    SCOPE_CHECK -->|"No results, no filter"| EMPTY
    RERANK --> RELEVANCE
    RELEVANCE -->|"Yes (low score)"| REGEX
    RELEVANCE -->|"No (good score)"| EXPAND
    REGEX --> REGEX_CHECK
    REGEX_CHECK -->|"Yes"| REGEX_WRAP --> EXPAND
    REGEX_CHECK -->|"No"| NO_REGEX
    EMPTY --> RELEVANCE
    EXPAND --> RESULT

    style RELAX fill:#3a2a1a,color:#fff
    style REGEX_WRAP fill:#3a1a2a,color:#fff
    style NO_REGEX fill:#3a1a1a,color:#fff
    style RESULT fill:#1a3a1a,color:#fff
```

---

## 3. Hybrid Search (LanceDB)

The `LanceDBStore.hybrid_search()` method fuses dense vector similarity and sparse BM25 lexical search using Reciprocal Rank Fusion (RRF):

```mermaid
flowchart LR
    subgraph INPUT["Inputs"]
        QT["query_text<br/>(for BM25 FTS)"]
        QV["query_vector<br/>(384-dim, for dense)"]
        WF["where_filter<br/>(SQL clause)"]
        TK["top_k=30"]
    end

    subgraph SANITIZE["Filter Sanitization"]
        COLS["valid_cols = table.schema.names"]
        SPLIT["Split filter by ' AND '"]
        CHECK["For each clause:<br/>Match column name against valid_cols"]
        KEEP["Keep if column is valid"]
        STRIP["Drop if column unknown"]
        CLEAN["clean_where = valid clauses joined<br/>(or None if all stripped)"]
    end

    subgraph DENSE["Dense Vector Search"]
        VECTOR["LanceDB vector search<br/>Cosine similarity<br/>IVF-PQ approximate NN"]
    end

    subgraph SPARSE["Sparse BM25 Search"]
        FTS["Tantivy full-text search<br/>BM25 scoring<br/>On 'text' column"]
    end

    subgraph FUSION["Reciprocal Rank Fusion"]
        RRF["RRF(K=60)<br/>score = Σ 1/(K + rank_i)<br/>for each ranking (dense + sparse)"]
    end

    subgraph OUTPUT["Output"]
        RAW["raw_results = builder.to_list()"]
        SCORE["Extract _relevance_score<br/>Normalize to [0, 1]<br/>= score / MAX_RRF_SCORE"]
        CHUNKS["Convert to ScoredChunk list"]
    end

    QT --> SPARSE
    QV --> DENSE
    WF --> SANITIZE --> CLEAN
    CLEAN --> DENSE
    CLEAN --> SPARSE
    DENSE --> RRF
    SPARSE --> RRF
    RRF --> RAW --> SCORE --> CHUNKS

    style STRIP fill:#3a1a1a,color:#fff
    style RRF fill:#1a2a3a,color:#fff
```

### Where filter sanitization

The sanitizer checks each clause's column name against the actual LanceDB table schema. Clauses referencing unknown columns are silently dropped. This is the mechanism that causes the [metadata filter column mismatch](./routing-slots.md#91-metadata-filter-column-mismatch-critical) — `program`, `batch_year`, `semester` are not top-level columns, so their clauses are stripped.

### RRF scoring

RRF (Reciprocal Rank Fusion) combines dense and sparse rankings:

```
RRF_score = Σ 1 / (K + rank_i)

where K = 60 (constant)
      rank_i = position in ranking i (1-indexed)
```

With 2 rankings (dense + sparse), max theoretical score = `2 / (60 + 1) ≈ 0.0328`. This is normalized to `[0, 1]` by dividing by `MAX_RRF_SCORE`.

### Fallback paths

| Condition | Fallback |
|-----------|----------|
| Hybrid search raises exception | Dense vector-only search (no BM25) |
| Dense-only search also fails | Empty results |
| FTS-only (no vector available) | Text search with where filter |

---

## 4. Cross-Encoder Reranking

The `FlashRankReranker` uses ms-marco-TinyBERT-L-2-v2 (ONNX, ~3ms per query) to rescore candidates:

```mermaid
flowchart LR
    INPUT["30 candidates from hybrid search"]
    PAIRS["Build (query, chunk_text) pairs<br/>for each candidate"]
    SCORE["Cross-encoder scores each pair<br/>ms-marco-TinyBERT ONNX inference"]
    SORT["Sort by cross-encoder score descending"]
    TOP["Return top_k=5 best candidates"]

    INPUT --> PAIRS --> SCORE --> SORT --> TOP

    style SCORE fill:#2a1a3a,color:#fff
    style TOP fill:#1a3a1a,color:#fff
```

If no reranker is configured, candidates are sorted by their RRF score and truncated to `top_k`.

---

## 5. Deterministic Regex Fallback

When the top candidate score is below the relevance threshold (0.35), the coordinator extracts a reference code from the query and performs a full-corpus regex scan:

```mermaid
flowchart TD
    LOW["Top score < 0.35<br/>or no candidates"]
    EXTRACT["extract_circular_reference(query)"]
    CHECK{"Code extracted?"}
    SCAN["vector_store.deterministic_regex_search(pattern)<br/>Full-corpus regex scan<br/>on chunk text"]
    MATCH_CHECK{"Matches found?"}
    WRAP["Wrap matches as ScoredChunk:<br/>score=1.0, lexical_score=1.0,<br/>regex_fallback=True"]
    MISS["Tag: RETRIEVAL_RECALL_MISS<br/>or CORPUS_MISSING_CONTENT"]

    LOW --> EXTRACT --> CHECK
    CHECK -->|"Yes"| SCAN
    CHECK -->|"No"| MISS
    SCAN --> MATCH_CHECK
    MATCH_CHECK -->|"Yes"| WRAP
    MATCH_CHECK -->|"No"| MISS

    style WRAP fill:#3a1a2a,color:#fff
    style MISS fill:#3a1a1a,color:#fff
```

### Reference extraction patterns

The `extract_circular_reference()` function checks in order:

1. **Circular/notice keyword** — `circular no. CUK/Acad/2023/123`, `notification # 102`
2. **Multi-segment alphanumeric** — `CUK/Acad/2023/102`, `CUKmr/Acad/2023/45` (must have letters + digits, or ≥2 slashes/dashes)
3. **Course code** — `BT-101`, `CS204` (2-4 letters + 3-4 digits)

Dates (e.g. `15-11-2024`) are excluded.

---

## 6. Parent Context Expansion

For each retrieved candidate, the coordinator expands its parent section for richer LLM context:

```mermaid
flowchart LR
    CANDIDATE["ScoredChunk"]
    CHUNK["chunk = candidate.chunk"]
    PARENT_ID["parent_chunk_id<br/>(from chunk metadata)"]
    GET_PARENT["vector_store.get_parent_chunk(parent_id)"]
    PARENT_CONTAINER["ParentChunkContainer<br/>full_section_text = all child texts<br/>heading_title, heading_level"]
    ATTACH["Attach to chunk.metadata:<br/>parent_context = full_section_text<br/>parent_section_text = full_section_text"]
    FLAGS["Set metadata flags:<br/>scope_relaxed = True/False<br/>regex_fallback = True/False"]

    CANDIDATE --> CHUNK --> PARENT_ID --> GET_PARENT --> PARENT_CONTAINER --> ATTACH --> FLAGS

    style PARENT_CONTAINER fill:#1a2a3a,color:#fff
    style ATTACH fill:#1a3a2a,color:#fff
```

This gives the LLM the full section text (all paragraphs under the heading) in addition to the specific chunk that was retrieved.

---

## 7. ScoredChunk Model

```python
class ScoredChunk(BaseModel):
    chunk: ChunkRecord | dict       # The actual chunk (with enriched metadata)
    score: float                    # Normalized relevance score [0, 1]
    dense_score: float              # Dense vector similarity score
    lexical_score: float            # BM25 lexical score
    rrf_rank: int                   # Rank in RRF fusion
    scope_relaxed: bool             # True if filter was dropped
    regex_fallback: bool            # True if regex scan was used
    chunk_id: str                   # Convenience accessor
    text_content: str               # Convenience accessor
    metadata: dict                  # Convenience accessor
```

---

## 8. Key Files

| File | Responsibility |
|------|---------------|
| `retrieval/subsystems/coordinator.py` | `HybridRetrievalCoordinator` — search lifecycle |
| `retrieval/subsystems/lancedb_store.py` | `LanceDBStore` — Arrow columnar store + hybrid search |
| `retrieval/subsystems/flashrank_reranker.py` | `FlashRankReranker` — cross-encoder reranking |
| `core/protocols/storage.py` | `VectorStoreProtocol`, `EmbeddingModelProtocol` |
| `core/protocols/reranker.py` | `RerankerProtocol` |
| `schemas/retrieval.py` | `ScoredChunk` |
