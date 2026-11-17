"""cuk_assistant/retrieval/lancedb_store.py

Embedded Hybrid Storage Subsystem using LanceDB + Tantivy BM25 + PyArrow.
Combines 384-dimensional dense semantic search (cosine) with sparse BM25 keyword search
via Reciprocal Rank Fusion (RRF, k=60).
Conforms to VectorStoreProtocol and OCP component registration.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa
from lancedb.index import FTS, BTree, IvfPq
from lancedb.rerankers import RRFReranker

from cuk_assistant.core.protocols.storage import VectorStoreProtocol
from cuk_assistant.core.registry import register_vector_store
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType, ParentChunkContainer
from cuk_assistant.schemas.retrieval import ScoredChunk

logger = logging.getLogger(__name__)

DEFAULT_LANCEDB_DIR = "data/lancedb"
CHUNKS_TABLE_NAME = "chunks"
PARENT_TABLE_NAME = "parent_sections"
EMBEDDING_DIM = 384

# Apache Arrow Schema for child chunks (CHUNKS_ARROW_SCHEMA)
CHUNKS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("chunk_id", pa.string(), nullable=False),
        pa.field("doc_id", pa.string(), nullable=False),
        pa.field("text", pa.string(), nullable=False),
        pa.field("vector", pa.list_(pa.float32(), EMBEDDING_DIM), nullable=False),
        pa.field("parent_chunk_id", pa.string(), nullable=True),
        pa.field("school", pa.string(), nullable=True),
        pa.field("department", pa.string(), nullable=True),
        pa.field("associated_departments", pa.list_(pa.string()), nullable=False),
        pa.field("is_university_wide", pa.bool_(), nullable=False),
        pa.field("doc_type", pa.string(), nullable=False),
        pa.field("source_url", pa.string(), nullable=False),
        pa.field("page_url", pa.string(), nullable=False),
        pa.field("title", pa.string(), nullable=False),
        pa.field("chunk_index", pa.int32(), nullable=False),
        pa.field("chunk_type", pa.string(), nullable=False),
        pa.field("token_count", pa.int32(), nullable=False),
        pa.field("page_number", pa.int32(), nullable=False),
        pa.field("metadata_json", pa.string(), nullable=False),
    ]
)

# Apache Arrow Schema for parent container sections
PARENT_SECTIONS_ARROW_SCHEMA = pa.schema(
    [
        pa.field("parent_chunk_id", pa.string(), nullable=False),
        pa.field("doc_id", pa.string(), nullable=False),
        pa.field("heading_title", pa.string(), nullable=False),
        pa.field("heading_level", pa.int32(), nullable=False),
        pa.field("section_token_count", pa.int32(), nullable=False),
        pa.field("full_section_text", pa.string(), nullable=False),
        pa.field("child_chunk_ids", pa.list_(pa.string()), nullable=False),
    ]
)

# Maximum theoretical score for RRF with K=60 across 2 rankings (dense + sparse)
MAX_RRF_SCORE = 2.0 / (60.0 + 1.0)


@register_vector_store("lancedb")
class LanceDBStore(VectorStoreProtocol):
    """Embedded hybrid vector & lexical store backed by LanceDB and Tantivy."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        table_name: str = CHUNKS_TABLE_NAME,
        parent_table_name: str = PARENT_TABLE_NAME,
    ) -> None:
        if db_path is None:
            db_path = os.environ.get("LANCEDB_DIR") or DEFAULT_LANCEDB_DIR
        raw_path = Path(db_path)
        if raw_path.name.endswith(".lance"):
            # If path points directly to chunks.lance, use its parent as DB dir
            self._db_path = raw_path.parent
            self._table_name = raw_path.stem
        else:
            self._db_path = raw_path
            self._table_name = table_name

        self._parent_table_name = parent_table_name
        self._db_path.mkdir(parents=True, exist_ok=True)

        logger.info("Opening LanceDB connection at %s", self._db_path)
        self._db = lancedb.connect(str(self._db_path))

        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create or open chunks and parent_sections tables."""
        if hasattr(self._db, "list_tables"):
            existing_tables = set(self._db.list_tables())
        else:
            existing_tables = set(self._db.table_names())

        if self._table_name in existing_tables:
            self._table = self._db.open_table(self._table_name)
        else:
            logger.info("Creating LanceDB table '%s'", self._table_name)
            self._table = self._db.create_table(
                self._table_name,
                schema=CHUNKS_ARROW_SCHEMA,
                mode="create",
            )

        if self._parent_table_name in existing_tables:
            self._parent_table = self._db.open_table(self._parent_table_name)
        else:
            logger.info("Creating LanceDB table '%s'", self._parent_table_name)
            self._parent_table = self._db.create_table(
                self._parent_table_name,
                schema=PARENT_SECTIONS_ARROW_SCHEMA,
                mode="create",
            )

    @property
    def table(self) -> lancedb.table.Table:
        """Access underlying LanceDB child chunks table."""
        return self._table

    @property
    def parent_table(self) -> lancedb.table.Table:
        """Access underlying LanceDB parent sections table."""
        return self._parent_table

    def add_chunks(
        self,
        chunks: list[Any],
        embeddings: list[list[float]],
        create_indices: bool = True,
    ) -> None:
        """Batch upsert chunks and dense vectors into storage."""
        if not chunks:
            return

        if len(chunks) != len(embeddings):
            raise ValueError(f"Mismatch: got {len(chunks)} chunks but {len(embeddings)} embeddings")

        records: list[dict[str, Any]] = []
        for chunk, emb in zip(chunks, embeddings, strict=True):
            rec = self._extract_chunk_record(chunk, emb)
            records.append(rec)

        logger.info("Adding %d chunk records to table '%s'", len(records), self._table_name)
        self._table.add(records)

        # Ensure indices are updated if requested
        if create_indices:
            self.create_indices()

    def add_parent_chunks(self, parent_chunks: list[Any]) -> None:
        """Batch upsert parent section containers into parent_sections table."""
        if not parent_chunks:
            return

        records: list[dict[str, Any]] = []
        for p in parent_chunks:
            if isinstance(p, ParentChunkContainer):
                records.append(
                    {
                        "parent_chunk_id": p.parent_chunk_id,
                        "doc_id": p.doc_id,
                        "heading_title": p.heading_title,
                        "heading_level": p.heading_level,
                        "section_token_count": p.section_token_count,
                        "full_section_text": p.full_section_text,
                        "child_chunk_ids": list(p.child_chunk_ids),
                    }
                )
            elif isinstance(p, dict):
                records.append(
                    {
                        "parent_chunk_id": str(p["parent_chunk_id"]),
                        "doc_id": str(p["doc_id"]),
                        "heading_title": str(p.get("heading_title", "")),
                        "heading_level": int(p.get("heading_level", 1)),
                        "section_token_count": int(p.get("section_token_count", 0)),
                        "full_section_text": str(p.get("full_section_text", "")),
                        "child_chunk_ids": list(p.get("child_chunk_ids", [])),
                    }
                )

        if records:
            logger.info(
                "Adding %d parent sections to table '%s'", len(records), self._parent_table_name
            )
            self._parent_table.add(records)

    def create_indices(self) -> None:
        """Create or refresh Tantivy FTS index, scalar BTree indices, and IVF-PQ vector index."""
        try:
            self._table.create_index("text", config=FTS(), replace=True)
            logger.info("Tantivy FTS index created/refreshed on 'text'")
        except Exception as e:
            try:
                if hasattr(self._table, "create_fts_index"):
                    self._table.create_fts_index("text", replace=True)
                    logger.info("Tantivy FTS index created via create_fts_index on 'text'")
                else:
                    logger.warning("Failed to create Tantivy FTS index: %s", e)
            except Exception as fts_err:
                logger.warning("Failed to create Tantivy FTS index: %s (fts_err: %s)", e, fts_err)

        # Scalar BTree indices on doc_id and source_url for filtered queries
        for col in ("doc_id", "source_url"):
            try:
                self._table.create_index(col, config=BTree(), replace=True)
                logger.info("BTree scalar index created/refreshed on '%s'", col)
            except Exception as e:
                logger.warning("Failed to create scalar index on '%s': %s", col, e)

        # Build IVF-PQ vector index only if sufficient rows exist (e.g. >= 1000)
        try:
            row_count = self._table.count_rows()
            if row_count >= 1000:
                self._table.create_index(
                    "vector",
                    config=IvfPq(
                        distance_type="cosine",
                        num_partitions=min(16, max(4, row_count // 100)),
                        num_sub_vectors=min(48, EMBEDDING_DIM // 8),
                    ),
                    replace=True,
                )
                logger.info("IVF-PQ vector index created for %d rows", row_count)
        except Exception as e:
            logger.debug("Skipping vector index build: %s", e)

    def get_stats(self) -> dict[str, Any]:
        """Return diagnostic statistics about the LanceDB store."""
        total_chunks = self._table.count_rows() if self._table is not None else 0
        total_parents = self._parent_table.count_rows() if self._parent_table is not None else 0
        indices: list[dict[str, Any]] = []
        if self._table is not None:
            try:
                for idx in self._table.list_indices():
                    indices.append(
                        {
                            "name": idx.name,
                            "index_type": str(idx.index_type),
                            "columns": list(idx.columns),
                        }
                    )
            except Exception as e:
                logger.debug("Failed listing indices: %s", e)
        return {
            "total_chunks": total_chunks,
            "total_parents": total_parents,
            "indices": indices,
        }

    def hybrid_search(
        self,
        query_text: str,
        query_vector: list[float],
        top_k: int = 30,
        where_filter: str | None = None,
    ) -> list[ScoredChunk]:
        """Execute fused dense cosine and sparse BM25 search via Reciprocal Rank Fusion (k=60)."""
        if self._table.count_rows() == 0 or top_k <= 0:
            return []

        clean_text = query_text.strip() if query_text else ""
        has_text = bool(clean_text)
        has_vector = bool(query_vector) and any(v != 0.0 for v in query_vector)

        # Sanitize where_filter against table columns to prevent LanceDB SQL schema errors
        clean_where = None
        if where_filter and self._table is not None:
            valid_cols = set(self._table.schema.names)
            raw_clauses = [
                c.strip() for c in re.split(r"\s+AND\s+", where_filter, flags=re.IGNORECASE)
            ]
            valid_clauses = []
            for clause in raw_clauses:
                m = re.match(
                    r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:==|=|!=|<=|>=|<|>|\bIN\b)",
                    clause,
                    re.IGNORECASE,
                )
                if m:
                    if m.group(1) in valid_cols:
                        valid_clauses.append(clause)
                else:
                    valid_clauses.append(clause)
            clean_where = " AND ".join(valid_clauses) if valid_clauses else None

        try:
            if has_text and has_vector:
                try:
                    builder = (
                        self._table.search(query_type="hybrid")
                        .vector(query_vector)
                        .text(clean_text)
                    )
                    if clean_where:
                        builder = builder.where(clean_where)
                    builder = builder.rerank(RRFReranker(K=60)).limit(top_k)
                    raw_results = builder.to_list()
                except Exception as hybrid_err:
                    logger.warning(
                        "Hybrid search execution error: %s. Falling back to dense vector search.",
                        hybrid_err,
                    )
                    builder = self._table.search(query_vector, query_type="vector")
                    if clean_where:
                        builder = builder.where(clean_where)
                    raw_results = builder.limit(top_k).to_list()
            elif has_vector:
                builder = self._table.search(query_vector, query_type="vector")
                if clean_where:
                    builder = builder.where(clean_where)
                raw_results = builder.limit(top_k).to_list()
            elif has_text:
                builder = self._table.search(clean_text, query_type="fts")
                if clean_where:
                    builder = builder.where(clean_where)
                raw_results = builder.limit(top_k).to_list()
            else:
                return []
        except Exception as e:
            logger.warning("Hybrid search execution error: %s. Falling back to empty.", e)
            return []

        scored_chunks: list[ScoredChunk] = []
        for rank_idx, item in enumerate(raw_results, start=1):
            chunk_rec = self._row_to_chunk_record(item)

            # Extract scores
            raw_rrf = item.get("_relevance_score")
            if raw_rrf is not None:
                # Normalize RRF score to [0.0, 1.0]
                normalized_score = min(1.0, float(raw_rrf) / MAX_RRF_SCORE)
                dense_score = float(item.get("_distance", 0.0))
                lexical_score = float(item.get("_score", 0.0))
            else:
                distance = item.get("_distance")
                score = item.get("_score")
                if distance is not None:
                    # Cosine distance to similarity: 1.0 - (dist / 2.0)
                    normalized_score = max(0.0, min(1.0, 1.0 - float(distance)))
                    dense_score = normalized_score
                    lexical_score = 0.0
                elif score is not None:
                    normalized_score = min(1.0, max(0.0, float(score) / 10.0))
                    dense_score = 0.0
                    lexical_score = float(score)
                else:
                    normalized_score = 1.0
                    dense_score = 0.0
                    lexical_score = 0.0

            scored = ScoredChunk(
                chunk=chunk_rec,
                score=normalized_score,
                dense_score=dense_score,
                lexical_score=lexical_score,
                rrf_rank=rank_idx,
            )
            scored_chunks.append(scored)

        return scored_chunks

    def get_parent_chunk(self, parent_chunk_id: str) -> ParentChunkContainer | None:
        """Retrieve full parent container section for O(1) context expansion."""
        if not parent_chunk_id or self._parent_table.count_rows() == 0:
            return None

        escaped_id = parent_chunk_id.replace("'", "''")
        alt_id = (
            escaped_id.replace("::c", "::p")
            if "::c" in escaped_id
            else escaped_id.replace("::p", "::c")
        )
        try:
            results = (
                self._parent_table.search()
                .where(f"parent_chunk_id = '{escaped_id}' OR parent_chunk_id = '{alt_id}'")
                .limit(1)
                .to_list()
            )
            if not results:
                return None

            row = results[0]
            return ParentChunkContainer(
                parent_chunk_id=row["parent_chunk_id"],
                doc_id=row["doc_id"],
                heading_title=row["heading_title"],
                heading_level=int(row["heading_level"]),
                section_token_count=int(row["section_token_count"]),
                full_section_text=row["full_section_text"],
                child_chunk_ids=list(row.get("child_chunk_ids", [])),
            )
        except Exception as e:
            logger.warning("Error fetching parent chunk '%s': %s", parent_chunk_id, e)
            return None

    def deterministic_regex_search(self, pattern: str) -> list[ChunkRecord]:
        """Full-corpus deterministic regex scan used on retrieval misses."""
        if not pattern or self._table.count_rows() == 0:
            return []

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            regex = re.compile(re.escape(pattern), re.IGNORECASE)

        matching_chunks: list[ChunkRecord] = []
        try:
            arrow_table = self._table.to_arrow()
            for row in arrow_table.to_pylist():
                text = row.get("text", "")
                title = row.get("title", "")
                doc_id = row.get("doc_id", "")
                chunk_id = row.get("chunk_id", "")
                meta_json = row.get("metadata_json", "")

                if (
                    regex.search(text)
                    or regex.search(title)
                    or regex.search(chunk_id)
                    or regex.search(doc_id)
                    or regex.search(meta_json)
                ):
                    matching_chunks.append(self._row_to_chunk_record(row))
        except Exception as e:
            logger.warning("Regex search error for pattern '%s': %s", pattern, e)

        return matching_chunks

    def delete_document(self, doc_id: str) -> None:
        """Remove all chunks associated with a specific doc_id during delta sync."""
        if not doc_id:
            return

        escaped = doc_id.replace("'", "''")
        try:
            self._table.delete(f"doc_id = '{escaped}'")
            logger.info("Deleted chunks for doc_id '%s'", doc_id)
        except Exception as e:
            logger.warning("Error deleting chunks for doc_id '%s': %s", doc_id, e)

        try:
            self._parent_table.delete(f"doc_id = '{escaped}'")
            logger.info("Deleted parent sections for doc_id '%s'", doc_id)
        except Exception as e:
            logger.debug("Error deleting parent sections for doc_id '%s': %s", doc_id, e)

    def _extract_chunk_record(self, chunk: Any, embedding: list[float]) -> dict[str, Any]:
        """Normalize chunk object into dictionary matching CHUNKS_ARROW_SCHEMA."""
        if isinstance(chunk, ChunkRecord):
            metadata = dict(chunk.metadata)
            doc_id = chunk.doc_id
            chunk_id = chunk.chunk_id
            text = chunk.text_content or chunk.text or ""
            parent_chunk_id = chunk.parent_chunk_id or metadata.get("parent_chunk_id")
            chunk_index = chunk.chunk_index
            chunk_type = (
                chunk.chunk_type.value
                if isinstance(chunk.chunk_type, ChunkType)
                else str(chunk.chunk_type)
            )
            token_count = chunk.token_count
            page_number = chunk.page_number
        elif isinstance(chunk, dict):
            metadata = dict(chunk.get("metadata", {}))
            doc_id = str(chunk.get("doc_id", ""))
            chunk_id = str(chunk.get("chunk_id", ""))
            text = str(chunk.get("text_content") or chunk.get("text") or "")
            parent_chunk_id = chunk.get("parent_chunk_id") or metadata.get("parent_chunk_id")
            chunk_index = int(chunk.get("chunk_index", 0))
            chunk_type = str(chunk.get("chunk_type", "paragraph"))
            token_count = int(chunk.get("token_count", len(text.split())))
            page_number = int(chunk.get("page_number", 1))
        else:
            metadata = getattr(chunk, "metadata", {}) or {}
            doc_id = str(getattr(chunk, "doc_id", ""))
            chunk_id = str(getattr(chunk, "chunk_id", ""))
            text = str(
                getattr(chunk, "text_content", "") or getattr(chunk, "text", "") or str(chunk)
            )
            parent_chunk_id = getattr(chunk, "parent_chunk_id", None) or metadata.get(
                "parent_chunk_id"
            )
            chunk_index = int(getattr(chunk, "chunk_index", 0))
            chunk_type = str(getattr(chunk, "chunk_type", "paragraph"))
            token_count = int(getattr(chunk, "token_count", len(text.split())))
            page_number = int(getattr(chunk, "page_number", 1))

        if parent_chunk_id is not None:
            metadata["parent_chunk_id"] = str(parent_chunk_id)

        # Flatten metadata fields per spec
        school = metadata.get("school") or metadata.get("school_name")
        department = metadata.get("department") or metadata.get("department_name")
        assoc_depts = metadata.get("associated_departments") or []
        if isinstance(assoc_depts, (str, bytes)):
            assoc_depts = [str(assoc_depts)]
        elif isinstance(assoc_depts, (list, tuple, set)):
            assoc_depts = [str(d) for d in assoc_depts]
        else:
            assoc_depts = []

        is_uni_wide = bool(metadata.get("is_university_wide", False))
        doc_type = str(metadata.get("doc_type", "general"))
        source_url = str(metadata.get("source_url", ""))
        page_url = str(metadata.get("page_url", ""))
        title = str(metadata.get("title", ""))

        return {
            "chunk_id": chunk_id,
            "doc_id": doc_id,
            "text": text,
            "vector": embedding,
            "parent_chunk_id": parent_chunk_id,
            "school": str(school) if school is not None else None,
            "department": str(department) if department is not None else None,
            "associated_departments": assoc_depts,
            "is_university_wide": is_uni_wide,
            "doc_type": doc_type,
            "source_url": source_url,
            "page_url": page_url,
            "title": title,
            "chunk_index": chunk_index,
            "chunk_type": chunk_type,
            "token_count": token_count,
            "page_number": page_number,
            "metadata_json": json.dumps(metadata),
        }

    def _row_to_chunk_record(self, row: dict[str, Any]) -> ChunkRecord:
        """Convert a LanceDB row dict into a canonical ChunkRecord."""
        try:
            metadata = json.loads(row.get("metadata_json", "{}"))
        except Exception:
            metadata = {}

        # Merge flattened fields into metadata
        if row.get("school") is not None:
            metadata["school"] = row["school"]
        if row.get("department") is not None:
            metadata["department"] = row["department"]
        if row.get("associated_departments"):
            metadata["associated_departments"] = row["associated_departments"]
        metadata["is_university_wide"] = row.get("is_university_wide", False)
        metadata["doc_type"] = row.get("doc_type", "general")
        metadata["source_url"] = row.get("source_url", "")
        metadata["page_url"] = row.get("page_url", "")
        metadata["title"] = row.get("title", "")
        resolved_parent_id = row.get("parent_chunk_id") or metadata.get("parent_chunk_id")
        if resolved_parent_id:
            metadata["parent_chunk_id"] = str(resolved_parent_id)

        chunk_type_raw = row.get("chunk_type", "paragraph")
        try:
            chunk_type = ChunkType(chunk_type_raw)
        except ValueError:
            chunk_type = ChunkType.PARAGRAPH

        return ChunkRecord(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            chunk_index=int(row.get("chunk_index", 0)),
            chunk_type=chunk_type,
            text_content=row["text"],
            text=row["text"],
            token_count=int(row.get("token_count", 0)),
            page_number=int(row.get("page_number", 1)),
            parent_chunk_id=resolved_parent_id,
            metadata=metadata,
        )


__all__ = [
    "CHUNKS_ARROW_SCHEMA",
    "CHUNKS_TABLE_NAME",
    "DEFAULT_LANCEDB_DIR",
    "EMBEDDING_DIM",
    "LanceDBStore",
    "PARENT_SECTIONS_ARROW_SCHEMA",
    "PARENT_TABLE_NAME",
]
