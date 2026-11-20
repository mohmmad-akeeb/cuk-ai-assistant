# Chunk + Embed + Index

> **Stages 4–5 of the ingestion pipeline.** Splits documents into hierarchical chunks, generates dense vectors, and indexes into LanceDB.
>
> Related: [Ingestion Overview](./overview.md) · [Parse + Normalize](./parse-normalize.md)

---

## 1. Purpose

Two CLI commands transform canonical documents into a searchable vector store:

- **`cuk-ingest`** — Reads `documents.jsonl`, enriches metadata with `PdfFactExtractor`, splits text into hierarchical chunks via `HierarchicalChunker`, writes `chunks.jsonl`.
- **`cuk-index`** — Reads `chunks.jsonl`, generates 384-dim dense vectors with FastEmbed, writes to LanceDB (Arrow columnar) with a Tantivy BM25 full-text index.

---

## 2. End-to-End Flow

```mermaid
flowchart LR
    subgraph STAGE4["Stage 4: Chunk (cuk-ingest)"]
        DOCS["documents.jsonl<br/>One line per document"]
        RUNNER["IngestionPipelineRunner.run()"]
        FACTS["PdfFactExtractor<br/>enrich_document_metadata()"]
        PREP["Prepend '# {title}' if<br/>no heading markers"]
        CHUNKER["HierarchicalChunker<br/>chunk_markdown()"]
        ADJUST["Ensure parent_chunk_id<br/>links on orphaned chunks"]
        CHUNKS_OUT["chunks.jsonl<br/>Atomic write (.tmp → rename)"]
    end

    subgraph STAGE5["Stage 5: Embed + Index (cuk-index)"]
        CHUNKS["chunks.jsonl"]
        EMBED["FastEmbedAdapter<br/>BGE-small-en-v1.5 (384-dim ONNX)"]
        BATCH["Batch embedding<br/>batch_size=64"]
        LANCE["LanceDBStore<br/>add_chunks()"]
        PARENT["Build parent_sections.lance<br/>from HEADING chunks"]
        INDICES["create_indices()<br/>IVF-PQ vector + Tantivy FTS<br/>+ BTree scalar"]
        VERIFY["Test query verification"]
        LAN_OUT["data/lancedb/<br/>chunks.lance<br/>parent_sections.lance"]
    end

    DOCS --> RUNNER
    RUNNER --> FACTS --> PREP --> CHUNKER --> ADJUST --> CHUNKS_OUT
    CHUNKS_OUT --> CHUNKS
    CHUNKS --> EMBED --> BATCH --> LANCE
    CHUNKS --> PARENT
    LANCE --> INDICES --> VERIFY --> LAN_OUT

    style STAGE4 fill:#1a3a2a,color:#fff
    style STAGE5 fill:#2a1a3a,color:#fff
```

---

## 3. Hierarchical Chunking

The `HierarchicalChunker` parses markdown text into structural blocks (headings, tables, paragraphs) and creates parent-child relationships between heading sections and their content.

### Chunking pipeline

```mermaid
flowchart TD
    INPUT["Markdown text<br/>+ base_metadata"]
    PREP{"Starts with '#'<br/>heading marker?"}
    PREPEND["Prepend '# {title}\\n\\n'"]
    NOOP["No change needed"]

    PARSE["Phase 1: Parse blocks<br/>_parse_blocks(lines)"]
    HEADING_BLOCK["HEADING block<br/># to ######<br/>level, title, text"]
    TABLE_BLOCK["TABLE block<br/>GFM table (pipe-delimited)<br/>header + separator + rows"]
    TEXT_BLOCK["TEXT block<br/>Paragraph(s) of body text"]

    HEADING_STACK["_HeadingStack<br/>Maintains active heading hierarchy"]
    PUSH["heading_stack.push(level, title, chunk_id)<br/>Returns parent heading chunk_id"]
    PARENT_LINK["Set parent_chunk_id<br/>from heading stack"]

    SPLIT["Phase 2: Convert blocks to chunks"]
    TEXT_SPLIT["_split_text_with_overlap()<br/>Splits long text by paragraphs/sentences<br/>target=120 tokens, max=180, overlap=25"]

    PHASE3["Phase 3: Construct ChunkRecords<br/>Bidirectional chaining:<br/>prev_chunk_id ↔ next_chunk_id"]
    PHASE4["Phase 4: Construct ParentChunkContainers<br/>full_section_text = all child texts joined"]

    INPUT --> PREP
    PREP -->|"No"| PREPEND --> PARSE
    PREP -->|"Yes"| NOOP --> PARSE
    PARSE --> HEADING_BLOCK
    PARSE --> TABLE_BLOCK
    PARSE --> TEXT_BLOCK

    HEADING_BLOCK --> HEADING_STACK --> PUSH
    PUSH --> PARENT_LINK
    TABLE_BLOCK --> PARENT_LINK
    TEXT_BLOCK --> TEXT_SPLIT

    PARENT_LINK --> SPLIT
    TEXT_SPLIT --> SPLIT
    SPLIT --> PHASE3 --> PHASE4

    style PREPEND fill:#3a2a1a,color:#fff
    style HEADING_STACK fill:#1a2a3a,color:#fff
    style TEXT_SPLIT fill:#1a3a2a,color:#fff
```

### Block detection rules

```mermaid
flowchart TD
    LINE["Each line in markdown"]
    CODE_FENCE{"Starts with ``` or ~~~?"}
    TOGGLE["Toggle in_code_fence<br/>(lines inside fence are TEXT)"]
    HEADING_CHECK{"Matches ^(#{1,6})\s+(.+)$?"}
    HEADING["HEADING block<br/>level = len(#), title = group(2)"]
    TABLE_CHECK{"Current line has |<br/>AND next line is table separator?<br/>(|:---:|---|)"}
    TABLE["TABLE block<br/>Consume all consecutive pipe-lines"]
    BODY["Add to pending text lines"]
    FLUSH["Flush pending TEXT block"]

    LINE --> CODE_FENCE
    CODE_FENCE -->|"Yes"| TOGGLE
    CODE_FENCE -->|"No"| HEADING_CHECK
    HEADING_CHECK -->|"Yes"| FLUSH --> HEADING
    HEADING_CHECK -->|"No"| TABLE_CHECK
    TABLE_CHECK -->|"Yes"| FLUSH --> TABLE
    TABLE_CHECK -->|"No"| BODY
    BODY --> LINE

    style HEADING fill:#1a2a3a,color:#fff
    style TABLE fill:#1a3a1a,color:#fff
    style BODY fill:#2a2a3a,color:#fff
```

### Text splitting with overlap

When a TEXT block exceeds `max_chunk_tokens` (180), it's split respecting paragraph and sentence boundaries:

```mermaid
flowchart TD
    TEXT["Long text block<br/>(> max_chunk_tokens)"]
    PARA["Split into paragraphs<br/>regex: \\n\\s*\\n"]
    PARA_CHECK{"Paragraph > target tokens?"}
    KEEP["Keep as single unit"]
    SENTENCE["Split into sentences<br/>regex: (?<=[.!?])\\s+"]
    SENTENCE_CHECK{"Sentence > max tokens?"}
    SENTENCE_KEEP["Keep sentence as unit"]
    WORD_SPLIT["Word-level fallback<br/>Step = target_tokens / 1.3 words"]

    ACCUM["Accumulate units until<br/>current_tokens + unit_tokens > target"]
    EMIT["Emit chunk<br/>(join units with \\n\\n)"]
    OVERLAP["Compute overlap prefix<br/>from trailing sentences (~25 tokens)"]
    NEXT["Start new chunk with<br/>overlap prefix + next unit"]

    TEXT --> PARA --> PARA_CHECK
    PARA_CHECK -->|"No"| KEEP --> ACCUM
    PARA_CHECK -->|"Yes"| SENTENCE --> SENTENCE_CHECK
    SENTENCE_CHECK -->|"No"| SENTENCE_KEEP --> ACCUM
    SENTENCE_CHECK -->|"Yes"| WORD_SPLIT --> ACCUM

    ACCUM -->|"Threshold reached"| EMIT --> OVERLAP --> NEXT
    ACCUM -->|"More units"| ACCUM
    NEXT --> ACCUM

    style EMIT fill:#1a3a2a,color:#fff
    style OVERLAP fill:#3a2a1a,color:#fff
```

### Chunk types

| `ChunkType` | Description | Generated from |
|-------------|-------------|----------------|
| `HEADING` | Section heading (`#` to `######`) | Markdown heading lines |
| `PARAGRAPH` | Body text chunk | Split from TEXT blocks |
| `MARKDOWN_TABLE` | Complete GFM table | Consecutive pipe-delimited lines |

> Tables are **atomic** — never split across chunks.

### Parent-child linking

```mermaid
flowchart TD
    subgraph DOC["Document: B.Tech CSE Syllabus"]
        H1["# B.Tech CSE Syllabus<br/>HEADING chunk<br/>parent_chunk_id: None<br/>chunk_id: doc::c0"]
        H2["## Semester 4<br/>HEADING chunk<br/>parent_chunk_id: doc::c0<br/>chunk_id: doc::c1"]
        P1["Database Management Systems...<br/>PARAGRAPH chunk<br/>parent_chunk_id: doc::c1<br/>chunk_id: doc::c2"]
        P2["Credits: 4<br/>PARAGRAPH chunk<br/>parent_chunk_id: doc::c1<br/>chunk_id: doc::c3"]
        H3["### Course Objectives<br/>HEADING chunk<br/>parent_chunk_id: doc::c1<br/>chunk_id: doc::c4"]
        P3["Students will learn...<br/>PARAGRAPH chunk<br/>parent_chunk_id: doc::c4<br/>chunk_id: doc::c5"]
        T1["| Unit | Topic | Hours |<br/>|---|---|---|<br/>| 1 | ER Diagrams | 8 |<br/>TABLE chunk<br/>parent_chunk_id: doc::c4<br/>chunk_id: doc::c6"]
    end

    subgraph PARENTS["ParentChunkContainers"]
        P0["doc::p0<br/>full_section_text: all text under # B.Tech...<br/>child_chunk_ids: [c0, c1, c2, c3, c4, c5, c6]"]
        P1_C["doc::p1<br/>full_section_text: all text under ## Semester 4<br/>child_chunk_ids: [c1, c2, c3, c4, c5, c6]"]
        P2_C["doc::p2<br/>full_section_text: all text under ### Course Objectives<br/>child_chunk_ids: [c4, c5, c6]"]
    end

    H1 -.->|"container"| P0
    H2 -.->|"container"| P1_C
    H3 -.->|"container"| P2_C

    style H1 fill:#1a2a3a,color:#fff
    style H2 fill:#1a2a3a,color:#fff
    style H3 fill:#1a2a3a,color:#fff
    style T1 fill:#1a3a1a,color:#fff
```

Each `HEADING` chunk creates a `ParentChunkContainer` that accumulates all child chunk texts. At retrieval time, the coordinator can expand a child chunk to its full parent section for richer context.

---

## 4. PdfFactExtractor

Before chunking, each document's metadata is enriched with intrinsic facts extracted from text:

```mermaid
flowchart LR
    META["Raw metadata dict"]
    TEXT["Document text"]
    TITLE["Document title"]

    EXTRACT["PdfFactExtractor.extract_facts()"]

    subgraph PATTERNS["Regex extraction"]
        REF["Reference/circular number<br/>CUK/Acad/2023/123<br/>NIT No 04 of 2026"]
        DATE["Notification date<br/>Dated: 15-11-2024 → 2024-11-15"]
        SUBJ["Subject line<br/>Subject: Examination Schedule"]
        YEAR["Academic year<br/>2023-24 → 2023-2024"]
        AUTH["Issuing authority<br/>Registrar, Dean, VC, COE, HOD"]
        SIGN["Signatories<br/>Sd/- Name (Designation)"]
    end

    FACTS["PdfIntrinsicFacts<br/>(reference_number, notification_date,<br/>issuing_authority, signatories,<br/>subject, academic_year)"]
    ENRICH["enrich_document_metadata()<br/>Backfill missing fields<br/>(don't overwrite existing)"]
    OUT["Enriched metadata<br/>reference_number, circular_number,<br/>published_date, issuing_authority,<br/>academic_year, subject"]

    META --> EXTRACT
    TEXT --> EXTRACT
    TITLE --> EXTRACT
    EXTRACT --> PATTERNS
    PATTERNS --> FACTS
    FACTS --> ENRICH
    META --> ENRICH
    ENRICH --> OUT

    style PATTERNS fill:#1a2a3a,color:#fff
    style ENRICH fill:#1a3a2a,color:#fff
```

Extraction uses the first 3000 characters (header) and last 3000 characters (tail) of document text. Signatories and authority designations are searched in both header and tail.

---

## 5. Embedding (FastEmbed)

The `FastEmbedAdapter` generates 384-dimensional dense vectors using the BAAI/bge-small-en-v1.5 ONNX model:

```mermaid
flowchart TD
    CHUNKS["chunks.jsonl<br/>List of ChunkRecord"]
    BATCH["Batch of 64 chunks<br/>per forward pass"]
    EMBED["FastEmbedAdapter.embed_documents()<br/>TextEmbedding.embed(batch)<br/>ONNX CPU inference"]
    VECTORS["List of 384-dim float vectors"]
    STORE["LanceDBStore.add_chunks()<br/>chunks + embeddings → Arrow table"]

    CHUNKS --> BATCH --> EMBED --> VECTORS --> STORE

    style EMBED fill:#2a1a3a,color:#fff
    style STORE fill:#1a3a1a,color:#fff
```

### Model details

| Property | Value |
|----------|-------|
| Model | BAAI/bge-small-en-v1.5 |
| Dimension | 384 |
| Runtime | ONNX CPU (via FastEmbed) |
| Query embedding | `query_embed()` (query-optimized) with fallback to `embed()` |
| Caching | `/opt/model_cache/fastembed/` (Docker pre-warmed) |
| Threading | Configurable via `--threads` flag |

---

## 6. LanceDB Schema

The LanceDB store uses Apache Arrow columnar format. Two tables are created:

### chunks table (CHUNKS_ARROW_SCHEMA)

```mermaid
flowchart TB
    subgraph TOP_LEVEL["Top-level columns (directly queryable)"]
        CID["chunk_id<br/>string"]
        DID["doc_id<br/>string"]
        TEXT_COL["text<br/>string"]
        VEC["vector<br/>fixed_size_list<float32>[384]"]
        PID["parent_chunk_id<br/>string"]
        SCHOOL["school<br/>string (nullable)"]
        DEPT["department<br/>string (nullable)"]
        ASSOC["associated_departments<br/>list<string>"]
        UNI["is_university_wide<br/>bool"]
        DOC_TYPE["doc_type<br/>string"]
        SOURCE["source_url<br/>string"]
        PAGE_URL["page_url<br/>string"]
        TITLE["title<br/>string"]
        CHUNK_IDX["chunk_index<br/>int32"]
        CHUNK_TYPE["chunk_type<br/>string"]
        TOKEN_CT["token_count<br/>int32"]
        PAGE_NUM["page_number<br/>int32"]
        META_JSON["metadata_json<br/>string (JSON serialized)"]
    end

    subgraph NESTED["Inside metadata_json (NOT directly queryable)"]
        PROG["program"]
        BATCH["batch_year"]
        SEM["semester"]
        COURSE["course_code"]
        COURSE_T["course_title"]
        CREDITS["credits"]
        EXAM_SES["exam_session"]
        ADM_YEAR["admission_year"]
        OTHER["...all other metadata fields"]
    end

    META_JSON -.->|"contains"| NESTED

    style TOP_LEVEL fill:#1a3a1a,color:#fff
    style NESTED fill:#3a1a1a,color:#fff
```

> **Known issue:** The slot-filler builds WHERE clauses like `program == 'B.Tech'` against `program` as if it were a top-level column, but `program` lives inside `metadata_json`. LanceDB's SQL filter engine cannot query inside a JSON string column. The filter sanitizer in `hybrid_search` strips these clauses, causing **silent filter failure**. See [routing-slots.md](../pipeline/routing-slots.md) for details.

### parent_sections table (PARENT_SECTIONS_ARROW_SCHEMA)

| Column | Type | Description |
|--------|------|-------------|
| `parent_chunk_id` | string | Parent section identifier |
| `doc_id` | string | Document ID |
| `heading_title` | string | Section heading text |
| `heading_level` | int32 | Heading depth (1–6) |
| `section_token_count` | int32 | Total tokens in section |
| `full_section_text` | string | Concatenated text of all child chunks |
| `child_chunk_ids` | list<string> | All child chunk IDs in this section |

---

## 7. Indexing Pipeline

```mermaid
flowchart TD
    START["cuk-index CLI"]
    READ["Read chunks.jsonl<br/>line by line"]
    DESERIALIZE["ChunkRecord.model_validate()"]
    PARENT_BUILD["Build ParentChunkContainer dict<br/>from HEADING chunks + child accumulation"]

    BATCH_LOOP["Batch loop (batch_size=64)"]
    EMBED_BATCH["embed_documents(texts, batch_size)<br/>→ 384-dim vectors"]
    ADD_CHUNKS["LanceDBStore.add_chunks()<br/>chunks + embeddings → Arrow table<br/>(create_indices=False)"]
    CLEAR["Clear batch buffer"]

    REMAINING["Process remaining chunks<br/>(< batch_size)"]
    ADD_PARENTS["LanceDBStore.add_parent_chunks()"]
    CREATE_INDICES["LanceDBStore.create_indices()<br/>FTS + IVF-PQ + BTree scalar"]
    TEST_QUERY["Test query: 'Biotechnology syllabus'<br/>Verify retrieval latency"]
    DONE["Indexing complete"]

    START --> READ --> DESERIALIZE --> PARENT_BUILD
    PARENT_BUILD --> BATCH_LOOP
    BATCH_LOOP -->|"batch full"| EMBED_BATCH --> ADD_CHUNKS --> CLEAR
    CLEAR --> BATCH_LOOP
    BATCH_LOOP -->|"end of file"| REMAINING
    REMAINING --> EMBED_BATCH
    ADD_PARENTS --> CREATE_INDICES --> TEST_QUERY --> DONE

    style EMBED_BATCH fill:#2a1a3a,color:#fff
    style CREATE_INDICES fill:#1a3a1a,color:#fff
    style TEST_QUERY fill:#3a2a1a,color:#fff
```

### Indices created

| Index | Type | Columns | Purpose |
|-------|------|---------|---------|
| FTS | Tantivy full-text | `text` | BM25 lexical search |
| Vector | IVF-PQ | `vector` | Approximate nearest neighbor (dense) |
| Scalar | BTree | `doc_type`, `school`, `department` | Metadata filter acceleration |

---

## 8. Output Verification

After indexing, `cuk-index` runs a test query to verify the store is functional:

```python
test_query = "Biotechnology syllabus"
test_vec = embedder.embed_query(test_query)
test_results = vector_store.hybrid_search(
    query_text=test_query,
    query_vector=test_vec,
    top_k=3,
)
# Reports latency + candidate count
```

This catches indexing issues before the RAG pipeline tries to use the store.

---

## 9. CLI Commands

```bash
# Chunk documents
cuk-ingest --input data/processed/documents.jsonl --output data/processed/chunks.jsonl

# Index into LanceDB
cuk-index --chunks-file data/processed/chunks.jsonl --db-dir data/lancedb --batch-size 64

# Check index health (no re-indexing)
cuk-index --stats

# Or via Makefile
make ingest    # runs cuk-ingest + cuk-index in sequence
```

---

## 10. Key Files

| File | Responsibility |
|------|---------------|
| `ingestion/cli/ingest.py` | CLI entry point (`cuk-ingest`) |
| `ingestion/cli/index.py` | CLI entry point (`cuk-index`) |
| `ingestion/runner.py` | `IngestionPipelineRunner` — chunk orchestration |
| `ingestion/chunking/hierarchical_chunker.py` | `HierarchicalChunker` — AST markdown chunking |
| `ingestion/parsers/subsystems/pdf_fact_extractor.py` | `PdfFactExtractor` — intrinsic fact extraction |
| `ingestion/embedding/fastembed_adapter.py` | `FastEmbedAdapter` — ONNX embedding (BGE-small) |
| `retrieval/subsystems/lancedb_store.py` | `LanceDBStore` — Arrow columnar store + hybrid search |
| `schemas/chunks.py` | `ChunkRecord`, `ChunkType`, `ParentChunkContainer` |
