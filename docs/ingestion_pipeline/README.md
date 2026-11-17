# Ingestion Pipeline Overview

The ingestion pipeline transforms raw web and document assets into high-quality, searchable chunks for the RAG system. It follows an **ELT (Extract-Load-Transform)** architecture designed to handle diverse data sources while ensuring consistency and quality.

## Pipeline Phases

1. **Collector (`cuk_assistant/ingestion/collector/`)**
   - Extracts data from the CUK portal (web, API, PDF).
   - Manages raw data storage in `data/raw/` in an immutable, versioned format.
   - Handles route discovery and sitemap crawling.

2. **Parsers (`cuk_assistant/ingestion/parsers/`)**
   - Offline parsing of HTML, API responses, and PDF documents.
   - Extracts structured textual content, metadata, and tables.

3. **Normalization (`cuk_assistant/ingestion/normalize/`)**
   - Reconciles metadata across sources.
   - Performs PII scrubbing and schema alignment.
   - Detects data deltas (using SHA-256) to ensure idempotency.

4. **Chunking (`cuk_assistant/ingestion/chunking/`)**
   - Implements `HierarchicalChunker` to break down normalized documents.
   - Establishes parent-child relationships between chunks to maintain context during retrieval.

## Operational Workflow
The pipeline is driven by specialized CLI commands (e.g., `cuk-crawl`, `cuk-parse`, `cuk-ingest`). For detailed operation, refer to the [System Architecture Specification](../../architecture.md).
