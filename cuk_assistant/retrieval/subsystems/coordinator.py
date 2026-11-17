"""cuk_assistant.retrieval.subsystems.coordinator.py

Hybrid Retrieval Coordinator with Scope Fallback and Deterministic Regex Recovery.
Implements FR-4.1, FR-4.2, FR-4.3, FR-4.4, and FR-4.5.
Zero external vendor dependencies per GEMINI.md.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from cuk_assistant.core.protocols.reranker import RerankerProtocol
from cuk_assistant.core.protocols.storage import (
    EmbeddingModelProtocol,
    VectorStoreProtocol,
)
from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    TelemetrySinkProtocol,
)
from cuk_assistant.schemas.chunks import ChunkRecord, ParentChunkContainer
from cuk_assistant.schemas.retrieval import ScoredChunk

logger = logging.getLogger(__name__)

# Patterns for extracting circular IDs, course codes, and alphanumeric codes
CIRCULAR_KEYWORD_PATTERN = re.compile(
    r"(?:circular|notice|notification|order)\s*(?:no\.?|number|#)?\s*[:\s]?\s*([A-Za-z0-9/_\-\.]+)",
    re.IGNORECASE,
)
MULTI_SEGMENT_PATTERN = re.compile(r"\b[A-Za-z0-9]+(?:[/\-\.][A-Za-z0-9]+)+\b")
COURSE_CODE_PATTERN = re.compile(r"\b[A-Z]{2,4}[-/\s]?\d{3,4}\b")
DATE_PATTERN = re.compile(r"^\d{1,4}[/\-\.]\d{1,2}[/\-\.]\d{1,4}$")


def extract_circular_reference(query: str) -> str | None:
    """Extract circular reference numbers, course codes, or alphanumeric IDs from query."""
    # 1. Circular / Notice explicit keyword match
    m = CIRCULAR_KEYWORD_PATTERN.search(query)
    if m:
        extracted = m.group(1).strip(".,;:!? '\"")
        if extracted and any(c.isalnum() for c in extracted):
            return extracted

    # 2. Multi-segment alphanumeric code (e.g. CUK/Acad/2023/102, CUKmr/Acad/2023/45)
    for m_seg in MULTI_SEGMENT_PATTERN.finditer(query):
        val = m_seg.group(0).strip(".,;:!? '\"")
        if DATE_PATTERN.match(val):
            continue
        if any(c.isalpha() for c in val) and any(c.isdigit() for c in val):
            return val
        if val.count("/") >= 2 or val.count("-") >= 2:
            return val

    # 3. Course code or department identifier (e.g. BT-101, CS204)
    m_code = COURSE_CODE_PATTERN.search(query)
    if m_code:
        return m_code.group(0).strip(".,;:!? '\"")

    return None


def format_where_filter(filters: dict[str, Any] | str | None) -> str | None:
    """Format dictionary or string filter into SQL-like where clause."""
    if not filters:
        return None
    if isinstance(filters, str):
        cleaned = filters.strip()
        return cleaned if cleaned else None
    if not isinstance(filters, dict):
        return None

    clauses: list[str] = []
    for key, value in filters.items():
        if value is None:
            continue
        if isinstance(value, bool):
            clauses.append(f"{key} = {str(value).lower()}")
        elif isinstance(value, (int, float)):
            clauses.append(f"{key} = {value}")
        elif isinstance(value, str):
            escaped = value.replace("'", "''")
            clauses.append(f"{key} = '{escaped}'")
        elif isinstance(value, (list, tuple, set)):
            items: list[str] = []
            for item in value:
                if isinstance(item, str):
                    items.append(f"'{item.replace("'", "''")}'")
                elif isinstance(item, bool):
                    items.append(str(item).lower())
                else:
                    items.append(str(item))
            clauses.append(f"{key} IN ({', '.join(items)})")
        else:
            escaped = str(value).replace("'", "''")
            clauses.append(f"{key} = '{escaped}'")

    return " AND ".join(clauses) if clauses else None


class HybridRetrievalCoordinator:
    """Coordinates the search lifecycle across vector, lexical, reranking, and fallback systems.

    Lifecycle:
    1. Query embedding (EmbeddingModelProtocol)
    2. Hybrid search with metadata filter (VectorStoreProtocol)
    3. FR-4.4 Scope Fallback (Auto-relaxation to global search on empty results)
    4. FR-4.3 Cross-Encoder Reranking (RerankerProtocol)
    5. FR-4.5 Deterministic Regex Fallback on low relevance or recall misses
    6. Parent section context expansion (get_parent_chunk)
    """

    def __init__(
        self,
        vector_store: VectorStoreProtocol,
        embedding_model: EmbeddingModelProtocol,
        reranker: RerankerProtocol | None = None,
        relevance_threshold: float = 0.35,
        telemetry_sink: TelemetrySinkProtocol | None = None,
    ) -> None:
        self.vector_store = vector_store
        self.embedding_model = embedding_model
        self.reranker = reranker
        self.relevance_threshold = relevance_threshold
        self.telemetry_sink = telemetry_sink
        self.last_scope_relaxed: bool = False
        self.last_regex_fallback: bool = False

    def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | str | None = None,
        top_k: int = 5,
        expand_parent_context: bool = True,
        trace_id: str | None = None,
    ) -> list[ScoredChunk]:
        """Execute the coordinated retrieval lifecycle."""
        self.last_scope_relaxed = False
        self.last_regex_fallback = False
        scope_relaxed = False
        regex_fallback_triggered = False

        # Step 1: Dense Query Embedding
        query_vector = self.embedding_model.embed_query(query)

        # Step 2: Scoped Hybrid Search
        where_filter = format_where_filter(filters)
        candidates = self.vector_store.hybrid_search(
            query_text=query,
            query_vector=query_vector,
            top_k=30,
            where_filter=where_filter,
        )

        # Step 3: FR-4.4 Scope Fallback (Auto-Relaxation)
        if where_filter is not None and not candidates:
            logger.info(
                "Scoped search returned 0 results for filter '%s'. Relaxing to global search.",
                where_filter,
            )
            scope_relaxed = True
            self.last_scope_relaxed = True
            candidates = self.vector_store.hybrid_search(
                query_text=query,
                query_vector=query_vector,
                top_k=30,
                where_filter=None,
            )

        # Step 4: Cross-Encoder Reranking
        if self.reranker is not None and candidates:
            candidates = self.reranker.rerank(
                query=query,
                candidates=candidates,
                top_k=top_k,
            )
        elif candidates:
            candidates = sorted(candidates, key=lambda c: c.score, reverse=True)[:top_k]

        # Step 5: FR-4.5 Deterministic Regex Fallback
        top_score = candidates[0].score if candidates else 0.0
        if not candidates or top_score < self.relevance_threshold:
            detected_code = extract_circular_reference(query)
            if detected_code:
                logger.info(
                    "Low relevance (top_score=%.3f < %.3f) with detected code '%s'. Triggering regex fallback.",
                    top_score,
                    self.relevance_threshold,
                    detected_code,
                )
                regex_matches = self.vector_store.deterministic_regex_search(pattern=detected_code)
                if regex_matches:
                    regex_fallback_triggered = True
                    self.last_regex_fallback = True
                    wrapped_candidates: list[ScoredChunk] = []
                    for idx, match in enumerate(regex_matches):
                        if isinstance(match, ScoredChunk):
                            wrapped = match.model_copy(
                                update={
                                    "score": 1.0,
                                    "dense_score": 0.0,
                                    "lexical_score": 1.0,
                                    "rrf_rank": idx + 1,
                                    "regex_fallback": True,
                                    "scope_relaxed": scope_relaxed,
                                }
                            )
                        elif isinstance(match, (ChunkRecord, dict)):
                            wrapped = ScoredChunk(
                                chunk=match,
                                score=1.0,
                                dense_score=0.0,
                                lexical_score=1.0,
                                rrf_rank=idx + 1,
                                regex_fallback=True,
                                scope_relaxed=scope_relaxed,
                            )
                        else:
                            wrapped = ScoredChunk(
                                chunk={"chunk_id": f"regex_{idx}", "text_content": str(match)},
                                score=1.0,
                                dense_score=0.0,
                                lexical_score=1.0,
                                rrf_rank=idx + 1,
                                regex_fallback=True,
                                scope_relaxed=scope_relaxed,
                            )
                        wrapped_candidates.append(wrapped)

                    candidates = wrapped_candidates[:top_k]

                    if self.telemetry_sink is not None:
                        self.telemetry_sink.tag_failure(
                            trace_id=trace_id or "retrieval",
                            diagnostic_code=FailureDiagnosticCode.RETRIEVAL_RECALL_MISS,
                            details={
                                "pattern": detected_code,
                                "matches_count": len(regex_matches),
                                "prior_top_score": top_score,
                            },
                        )
                else:
                    if not candidates and self.telemetry_sink is not None:
                        self.telemetry_sink.tag_failure(
                            trace_id=trace_id or "retrieval",
                            diagnostic_code=FailureDiagnosticCode.CORPUS_MISSING_CONTENT,
                            details={"pattern": detected_code, "query": query},
                        )
            else:
                if not candidates and self.telemetry_sink is not None:
                    self.telemetry_sink.tag_failure(
                        trace_id=trace_id or "retrieval",
                        diagnostic_code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
                        details={"query": query, "where_filter": where_filter},
                    )

        # Step 6: Parent Context Expansion & Flag Propagation
        result_chunks: list[ScoredChunk] = []
        for candidate in candidates[:top_k]:
            hydrated = self._process_candidate(
                candidate=candidate,
                scope_relaxed=scope_relaxed,
                regex_fallback=regex_fallback_triggered or candidate.regex_fallback,
                expand_parent_context=expand_parent_context,
            )
            result_chunks.append(hydrated)

        return result_chunks

    def _process_candidate(
        self,
        candidate: ScoredChunk,
        scope_relaxed: bool,
        regex_fallback: bool,
        expand_parent_context: bool,
    ) -> ScoredChunk:
        """Hydrate parent section context and synchronize scope_relaxed / regex_fallback flags."""
        chunk = candidate.chunk
        parent_text: str | None = None

        if expand_parent_context:
            parent_id: str | None = None
            if isinstance(chunk, ChunkRecord):
                parent_id = chunk.parent_chunk_id
            elif isinstance(chunk, dict):
                parent_id = chunk.get("parent_chunk_id")

            if parent_id:
                parent = self.vector_store.get_parent_chunk(parent_id)
                if parent is not None:
                    if isinstance(parent, ParentChunkContainer) or hasattr(
                        parent, "full_section_text"
                    ):
                        parent_text = parent.full_section_text
                    elif hasattr(parent, "text_content"):
                        parent_text = parent.text_content
                    elif isinstance(parent, dict):
                        parent_text = (
                            parent.get("full_section_text")
                            or parent.get("text_content")
                            or str(parent)
                        )
                    else:
                        parent_text = str(parent)

        # Update underlying chunk metadata
        if isinstance(chunk, ChunkRecord):
            meta_dict = dict(chunk.metadata)
            if scope_relaxed:
                meta_dict["scope_relaxed"] = True
            if regex_fallback:
                meta_dict["regex_fallback"] = True
            if parent_text is not None:
                meta_dict["parent_context"] = parent_text
                meta_dict["parent_section_text"] = parent_text
            updated_chunk: ChunkRecord | dict[str, Any] = chunk.model_copy(
                update={"metadata": meta_dict}
            )
        elif isinstance(chunk, dict):
            updated_dict = dict(chunk)
            meta_dict = dict(updated_dict.get("metadata", {}))
            if scope_relaxed:
                meta_dict["scope_relaxed"] = True
            if regex_fallback:
                meta_dict["regex_fallback"] = True
            if parent_text is not None:
                meta_dict["parent_context"] = parent_text
                meta_dict["parent_section_text"] = parent_text
            updated_dict["metadata"] = meta_dict
            updated_chunk = updated_dict
        else:
            updated_chunk = chunk

        return candidate.model_copy(
            update={
                "chunk": updated_chunk,
                "scope_relaxed": scope_relaxed or candidate.scope_relaxed,
                "regex_fallback": regex_fallback or candidate.regex_fallback,
            }
        )


__all__ = [
    "HybridRetrievalCoordinator",
    "extract_circular_reference",
    "format_where_filter",
    "main",
]


def main() -> None:
    """CLI entrypoint for testing hybrid retrieval."""
    import sys
    import time

    from cuk_assistant.core.factory import create_retrieval_coordinator

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "Biotechnology syllabus"
    coordinator = create_retrieval_coordinator()

    start = time.perf_counter()
    results = coordinator.retrieve(query=query, top_k=5)
    elapsed_ms = (time.perf_counter() - start) * 1000

    print(f"Query: '{query}'")
    print(f"Retrieved: {len(results)} chunks (Latency: {elapsed_ms:.2f}ms)")
    print(
        f"Scope relaxed: {coordinator.last_scope_relaxed} | Regex fallback: {coordinator.last_regex_fallback}"
    )
    for idx, c in enumerate(results, 1):
        print(
            f"  [{idx}] Score: {c.score:.4f} | ID: {c.chunk_id} | Title: {c.metadata.get('title', 'N/A')}"
        )
        snippet = (c.text_content or "").replace("\n", " ")[:120]
        print(f"      Snippet: {snippet}...")


if __name__ == "__main__":
    main()
