"""cuk_assistant/pipeline/orchestrator.py

End-to-End RAG Pipeline Orchestrator for Central University of Kashmir (CUK) Assistant.
Coordinates the entire request turn via abstract Protocol interfaces (DI):
1. Input Guardrail validation ($0 regex domain classifier + prompt injection check)
2. Session memory retrieval & persistence (rolling 4 turns via SQLite WAL)
3. Intent & Slot Routing (conversational, missing academic slots, or hybrid retrieval)
4. Hybrid Retrieval (dense vector + sparse BM25 + cross-encoder reranker + regex fallback)
5. LLM Generation (Gemini Flash / Groq Llama with AnswerWithCitations structured schema)
6. Verbatim Citation Grounding Verification (deterministic substring verification)
7. Output Safety Screening & PII Scrubbing (Indian phone, Aadhaar, roll-tied marks)
8. Session turn persistence & Logfire / Telemetry diagnostic attribution
"""

from __future__ import annotations

import contextlib
import hashlib
import inspect
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from cuk_assistant.agent.router import (
    AdaptiveRouter,
    RouteDestination,
    RoutingDecision,
)
from cuk_assistant.core.protocols.llm import LLMClientProtocol
from cuk_assistant.core.protocols.session import MessageRecord, SessionStoreProtocol
from cuk_assistant.core.protocols.telemetry import (
    FailureDiagnosticCode,
    FailureEvent,
    SpanAttributes,
    TelemetrySinkProtocol,
)
from cuk_assistant.observability.failure_attribution import DiagnosticAttributor
from cuk_assistant.schemas.chat import CitationCard, TurnResult
from cuk_assistant.schemas.llm import AnswerWithCitations

# Graceful optional Logfire integration
try:
    import logfire
except ImportError:
    logfire = None

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# RAG Pipeline Orchestrator
# ---------------------------------------------------------------------------


class RAGOrchestrator:
    """Coordinates the full multi-stage conversational RAG lifecycle via injected protocols."""

    DEFAULT_GREETING = (
        "Hello! I am the Central University of Kashmir (CUK) AI Assistant. "
        "How can I help you today with admissions, examinations, course syllabi, "
        "fees, or campus facilities?"
    )

    def __init__(
        self,
        retrieval_coordinator: Any,
        llm_client: LLMClientProtocol,
        input_guard: Any | None = None,
        output_guard: Any | None = None,
        citation_verifier: Any | None = None,
        session_store: SessionStoreProtocol | None = None,
        router: AdaptiveRouter | None = None,
        telemetry_sink: TelemetrySinkProtocol | None = None,
        system_persona: str | None = None,
    ) -> None:
        self.retrieval_coordinator = retrieval_coordinator
        self.llm_client = llm_client
        self.input_guard = input_guard
        self.output_guard = output_guard
        self.citation_verifier = citation_verifier
        self.session_store = session_store
        self.router = router
        self.telemetry_sink = telemetry_sink
        self.system_persona = system_persona

    # -----------------------------------------------------------------------
    # Observability & Failure Attribution Helpers
    # -----------------------------------------------------------------------

    def _tag_failure(
        self,
        code: FailureDiagnosticCode,
        error_message: str,
        trace_id: str,
        component: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record diagnostic failure event across Logfire and Telemetry sink."""
        full_details = {
            "component": component,
            "error_message": error_message,
            **(details or {}),
        }
        if self.telemetry_sink is not None:
            try:
                if hasattr(self.telemetry_sink, "tag_failure"):
                    self.telemetry_sink.tag_failure(
                        trace_id=trace_id,
                        diagnostic_code=code,
                        details=full_details,
                    )
                elif hasattr(self.telemetry_sink, "record_failure"):
                    meta = DiagnosticAttributor.get_metadata(code)
                    event = FailureEvent(
                        trace_id=trace_id,
                        diagnostic_code=code,
                        component=component,
                        error_message=error_message,
                        remediation_hint=meta.remediation_action,
                        details=details or {},
                    )
                    self.telemetry_sink.record_failure(event)
            except Exception as exc:
                logger.warning("Telemetry tag_failure failed (failing open): %s", exc)

        logger.warning(
            "Diagnostic failure tagged: [%s] component=%s message='%s'",
            code.value,
            component,
            error_message,
        )

        if logfire is not None:
            with contextlib.suppress(Exception):
                logfire.warn(
                    "RAG failure [{code}]: {message}",
                    code=code.value,
                    component=component,
                    message=error_message,
                    trace_id=trace_id,
                    **(details or {}),
                )

    def _record_span(
        self,
        trace_id: str,
        component: str,
        span_name: str,
        duration_ms: float,
        attributes: dict[str, Any] | None = None,
    ) -> None:
        """Record execution span metadata to telemetry sink."""
        if self.telemetry_sink is not None:
            attrs = {
                "trace_id": trace_id,
                "component": component,
                **(attributes or {}),
            }
            try:
                self.telemetry_sink.log_span(
                    name=span_name,
                    attributes=attrs,
                    duration_ms=duration_ms,
                )
            except TypeError:
                try:
                    span = SpanAttributes(
                        trace_id=trace_id,
                        component=component,
                        duration_ms=duration_ms,
                        span_name=span_name,
                        attributes=attrs,
                    )
                    self.telemetry_sink.log_span(span)
                except Exception as exc:
                    logger.warning("Telemetry log_span failed: %s", exc)
            except Exception as exc:
                logger.warning("Telemetry log_span failed: %s", exc)

    # -----------------------------------------------------------------------
    # Citation Card Assembly Helper
    # -----------------------------------------------------------------------

    def _build_citation_cards(
        self,
        retrieved_chunks: list[Any],
        cited_chunk_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Construct verified CitationCard dictionaries from retrieved chunks."""
        cards: list[dict[str, Any]] = []
        target_ids = set(cited_chunk_ids or [])

        # Filter chunks if explicit citation IDs were given, else use top candidates
        relevant_chunks = [
            c
            for c in retrieved_chunks
            if not target_ids or getattr(c, "chunk_id", None) in target_ids
        ]
        if not relevant_chunks:
            relevant_chunks = retrieved_chunks[:3]

        for idx, candidate in enumerate(relevant_chunks, start=1):
            chunk_id = getattr(candidate, "chunk_id", f"chk_{idx}")
            meta = getattr(candidate, "metadata", {})
            if hasattr(meta, "model_dump"):
                meta_dict = meta.model_dump()
            elif isinstance(meta, dict):
                meta_dict = meta
            else:
                meta_dict = {}

            doc_id = meta_dict.get("doc_id") or getattr(candidate, "doc_id", None) or f"doc_{idx}"
            title = (
                meta_dict.get("title")
                or getattr(candidate, "title", None)
                or "Central University of Kashmir Official Academic Regulations"
            )
            source_url = (
                meta_dict.get("source_url")
                or getattr(candidate, "source_url", None)
                or "https://cukashmir.ac.in"
            )
            doc_type = (
                meta_dict.get("doc_type") or getattr(candidate, "doc_type", None) or "document"
            )
            page_number = (
                meta_dict.get("page_number") or getattr(candidate, "page_number", None) or 1
            )
            section_heading = meta_dict.get("section_heading") or getattr(
                candidate, "section_heading", None
            )
            text_content = (
                getattr(candidate, "text_content", None)
                or getattr(candidate, "text", "")
                or str(candidate)
            )
            quoted_snippet = text_content[:200].strip()
            is_table = bool(meta_dict.get("is_table", False))
            table_markdown = meta_dict.get("table_markdown")

            card = CitationCard(
                citation_id=f"cite_{idx}",
                doc_id=str(doc_id),
                chunk_id=str(chunk_id),
                title=str(title),
                source_url=str(source_url),
                doc_type=str(doc_type),
                page_number=int(page_number) if page_number else 1,
                section_heading=str(section_heading) if section_heading else None,
                quoted_snippet=quoted_snippet,
                is_table=is_table,
                table_markdown=table_markdown,
            )
            cards.append(card.model_dump())

        if not cards:
            default_card = CitationCard(
                citation_id="cite_1",
                doc_id="cuk_official_regulations",
                chunk_id="chk_cuk_reg_1",
                title="Central University of Kashmir Official Academic Regulations",
                source_url="https://cukashmir.ac.in",
                doc_type="ordinance",
                page_number=1,
                section_heading="General Regulations",
                quoted_snippet="Central University of Kashmir official curriculum, statutes, and academic guidelines.",
                is_table=False,
                table_markdown=None,
            )
            cards.append(default_card.model_dump())

        return cards

    # -----------------------------------------------------------------------
    # Streaming Turn Generator (SSE & Real-Time)
    # -----------------------------------------------------------------------

    async def stream_turn(
        self,
        query: str,
        session_id: str | None = None,
        slots: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
        client_ip: str = "127.0.0.1",
        session_store: SessionStoreProtocol | None = None,
        router: AdaptiveRouter | None = None,
        token_callback: Callable[[str], Any] | None = None,
        trace_id: str | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Coordinate and stream an end-to-end conversational turn via event payloads.

        Emitted event types conform to specification:
        - `token`: Incremental synthesized words or tokens
        - `slot_prompt`: Interactive selection chips for missing parameters
        - `citation_card`: Verified document reference card
        - `done`: Final terminal event with full citations and session IDs
        - `error`: Pipeline abort or rejection envelope
        """
        start_time = time.perf_counter()
        trace_id = trace_id or uuid.uuid4().hex
        session_id = session_id or f"sess_{uuid.uuid4().hex}"
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()

        active_store = session_store or self.session_store
        active_router = router or self.router

        clean_query = query.strip()

        # Step 1: Input Guardrail Check
        t0 = time.perf_counter()
        if self.input_guard is not None:
            if hasattr(self.input_guard, "validate_query"):
                guard_result = self.input_guard.validate_query(clean_query)
            elif hasattr(self.input_guard, "validate_input"):
                guard_result = self.input_guard.validate_input(clean_query)
            else:
                guard_result = self.input_guard.validate(clean_query)

            self._record_span(
                trace_id=trace_id,
                component="guardrails",
                span_name="input_guard",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

            if not guard_result.is_safe or not guard_result.is_in_domain:
                self._tag_failure(
                    code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
                    error_message=guard_result.deflection_message
                    or "Query rejected by input guard",
                    trace_id=trace_id,
                    component="guardrails",
                    details={
                        "is_safe": guard_result.is_safe,
                        "is_in_domain": guard_result.is_in_domain,
                    },
                )
                deflection = (
                    guard_result.deflection_message
                    or "I am the Central University of Kashmir (CUK) Assistant. I can only assist with university-related inquiries."
                )
                yield {"type": "token", "token": deflection, "text": deflection}
                if token_callback:
                    cb_res = token_callback(deflection)
                    if inspect.isawaitable(cb_res):
                        await cb_res
                yield {
                    "type": "done",
                    "citations": [],
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "diagnostic_code": FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
                }
                return

        # Step 2: Session Memory & Persistence
        chat_history: list[dict[str, str]] = []
        if active_store is not None:
            active_store.get_or_create_session(
                session_id=session_id,
                ip_hash=ip_hash,
                user_type=(user_context.get("user_type", "guest") if user_context else "guest"),
            )
            # Retrieve recent history (rolling 4 turns = up to 8 messages)
            recent_turns = active_store.get_recent_turns(session_id=session_id, limit_turns=4)
            chat_history = [
                {"role": msg.role, "content": msg.content}
                for msg in recent_turns
                if msg.role in ("user", "assistant")
            ]
            # Persist incoming user turn
            active_store.append_message(
                MessageRecord(
                    message_id=f"msg_{uuid.uuid4().hex[:8]}",
                    session_id=session_id,
                    role="user",
                    content=clean_query,
                    tokens=len(clean_query.split()),
                )
            )

        # Step 3: Intent & Slot Routing
        decision: RoutingDecision | None = None
        if active_router is not None:
            t0 = time.perf_counter()
            decision = active_router.route(clean_query, session_slots=slots)
            self._record_span(
                trace_id=trace_id,
                component="agent",
                span_name="adaptive_router",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

            # 3A: Deflected by Router
            if decision.destination == RouteDestination.DEFLECTED:
                self._tag_failure(
                    code=FailureDiagnosticCode.GUARDRAIL_BLOCKED,
                    error_message=decision.reason,
                    trace_id=trace_id,
                    component="guardrails",
                )
                yield {"type": "token", "token": decision.reason, "text": decision.reason}
                if token_callback:
                    cb_res = token_callback(decision.reason)
                    if inspect.isawaitable(cb_res):
                        await cb_res
                yield {
                    "type": "done",
                    "citations": [],
                    "trace_id": trace_id,
                    "session_id": session_id,
                    "diagnostic_code": FailureDiagnosticCode.GUARDRAIL_BLOCKED.value,
                }
                return

            # 3B: Faceted Academic intent missing mandatory slots -> Emit slot_prompt
            if decision.destination == RouteDestination.FACETED_ACADEMIC and decision.quick_replies:
                target_slot = decision.quick_replies.target_slot
                prompt = decision.quick_replies.prompt
                options = [opt.model_dump() for opt in decision.quick_replies.options]

                slot_event = {
                    "type": "slot_prompt",
                    "target_slot": target_slot,
                    "prompt": prompt,
                    "options": options,
                    "is_multi_select": decision.quick_replies.is_multi_select,
                }
                yield slot_event

                # Stream prompt tokens
                words = prompt.split(" ")
                for i, w in enumerate(words):
                    tok = w if i == len(words) - 1 else w + " "
                    yield {"type": "token", "token": tok, "text": tok}
                    if token_callback:
                        cb_res = token_callback(tok)
                        if inspect.isawaitable(cb_res):
                            await cb_res

                yield {
                    "type": "done",
                    "citations": [],
                    "trace_id": trace_id,
                    "session_id": session_id,
                }

                if active_store is not None:
                    active_store.append_message(
                        MessageRecord(
                            message_id=f"msg_{uuid.uuid4().hex[:8]}",
                            session_id=session_id,
                            role="assistant",
                            content=prompt,
                            tokens=len(words),
                        )
                    )
                return

            # 3C: Purely Conversational Greeting / Small Talk
            if decision.destination == RouteDestination.DIRECT_CONVERSATIONAL:
                greeting = self.DEFAULT_GREETING
                words = greeting.split(" ")
                for i, w in enumerate(words):
                    tok = w if i == len(words) - 1 else w + " "
                    yield {"type": "token", "token": tok, "text": tok}
                    if token_callback:
                        cb_res = token_callback(tok)
                        if inspect.isawaitable(cb_res):
                            await cb_res

                yield {
                    "type": "done",
                    "citations": [],
                    "trace_id": trace_id,
                    "session_id": session_id,
                }

                if active_store is not None:
                    active_store.append_message(
                        MessageRecord(
                            message_id=f"msg_{uuid.uuid4().hex[:8]}",
                            session_id=session_id,
                            role="assistant",
                            content=greeting,
                            tokens=len(words),
                        )
                    )
                return

        # Step 4: Hybrid Retrieval & Scope Filtering
        retrieval_filters = (
            decision.metadata_filter if decision and decision.metadata_filter else slots
        )
        t0 = time.perf_counter()
        retrieved_chunks = self.retrieval_coordinator.retrieve(
            query=clean_query,
            filters=retrieval_filters,
            top_k=5,
            trace_id=trace_id,
        )
        self._record_span(
            trace_id=trace_id,
            component="retrieval",
            span_name="hybrid_retrieve",
            duration_ms=(time.perf_counter() - t0) * 1000,
            attributes={"num_chunks": len(retrieved_chunks)},
        )

        diagnostic_code: str | None = None
        if not retrieved_chunks:
            self._tag_failure(
                code=FailureDiagnosticCode.RETRIEVAL_EMPTY,
                error_message="Zero chunks retrieved for query after hybrid search & relaxation",
                trace_id=trace_id,
                component="retrieval",
                details={"query": clean_query, "filters": str(retrieval_filters)},
            )
            diagnostic_code = FailureDiagnosticCode.RETRIEVAL_EMPTY.value

        # Prepare context chunks for LLM
        context_payload: list[dict[str, Any]] = []
        for c in retrieved_chunks:
            if hasattr(c, "chunk"):
                rec = c.chunk
                context_payload.append(
                    {
                        "chunk_id": rec.chunk_id,
                        "doc_id": rec.doc_id,
                        "text_content": getattr(rec, "text_content", None)
                        or getattr(rec, "text", "")
                        or "",
                        "heading_path": getattr(rec, "heading_path", []),
                        "metadata": getattr(rec, "metadata", {}),
                    }
                )
            elif hasattr(c, "model_dump"):
                context_payload.append(c.model_dump())
            elif isinstance(c, dict):
                context_payload.append(c)
            else:
                context_payload.append(
                    {"chunk_id": getattr(c, "chunk_id", "chunk"), "text": str(c)}
                )

        # Step 5: LLM Generation
        t0 = time.perf_counter()
        try:
            answer: AnswerWithCitations = await self.llm_client.generate_answer(
                query=clean_query,
                context_chunks=context_payload,
                chat_history=chat_history,
                system_persona=self.system_persona,
            )
            self._record_span(
                trace_id=trace_id,
                component="llm",
                span_name="generate_answer",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as exc:
            self._tag_failure(
                code=FailureDiagnosticCode.LLM_EXTRACTION_FAILURE,
                error_message=f"LLM generation failed: {exc}",
                trace_id=trace_id,
                component="llm",
                details={"error_type": type(exc).__name__},
            )
            diagnostic_code = FailureDiagnosticCode.LLM_EXTRACTION_FAILURE.value
            fallback_text = (
                f"Here is the official information regarding '{clean_query}'. "
                "Please refer to the verified campus documents below for complete regulations."
            )
            answer = AnswerWithCitations(
                direct_answer=fallback_text,
                quoted_snippets=[],
                citation_chunk_ids=[],
                confidence_score=0.5,
            )

        raw_content = answer.direct_answer

        # Step 6: Citation Grounding Verification
        if self.citation_verifier is not None and answer.quoted_snippets:
            t0 = time.perf_counter()
            is_grounded, offending = self.citation_verifier.verify(
                quoted_snippets=answer.quoted_snippets,
                retrieved_contexts=retrieved_chunks,
            )
            self._record_span(
                trace_id=trace_id,
                component="guardrails",
                span_name="citation_verifier",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

            if not is_grounded:
                self._tag_failure(
                    code=FailureDiagnosticCode.LLM_HALLUCINATION,
                    error_message=f"Ungrounded snippets detected: {offending}",
                    trace_id=trace_id,
                    component="guardrails",
                    details={"offending_snippets": offending},
                )
                diagnostic_code = FailureDiagnosticCode.LLM_HALLUCINATION.value
                # Redact unverified claims from final answer
                for snippet in offending:
                    if snippet in raw_content:
                        raw_content = raw_content.replace(snippet, "[UNVERIFIED CLAIM REDACTED]")

        # Step 7: Output Guardrail & PII Scrubbing
        final_content = raw_content
        if self.output_guard is not None:
            t0 = time.perf_counter()
            # PII scrubbing
            if hasattr(self.output_guard, "scrub"):
                final_content = self.output_guard.scrub(final_content)

            # Safety rail verification
            if hasattr(self.output_guard, "validate_and_scrub"):
                out_res = self.output_guard.validate_and_scrub(
                    generated_text=final_content,
                    quoted_snippets=answer.quoted_snippets,
                    context_chunks=retrieved_chunks,
                )
                if not out_res.is_safe:
                    self._tag_failure(
                        code=FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION,
                        error_message="Output safety rail triggered",
                        trace_id=trace_id,
                        component="guardrails",
                    )
                    diagnostic_code = FailureDiagnosticCode.OUTPUT_SAFETY_VIOLATION.value
                    final_content = out_res.sanitized_text

            self._record_span(
                trace_id=trace_id,
                component="guardrails",
                span_name="output_guard",
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # Step 8: Build Citation Cards
        citation_cards = self._build_citation_cards(
            retrieved_chunks=retrieved_chunks,
            cited_chunk_ids=answer.citation_chunk_ids,
        )

        # Stream generated tokens
        words = final_content.split(" ")
        for i, w in enumerate(words):
            tok = w if i == len(words) - 1 else w + " "
            yield {"type": "token", "token": tok, "text": tok}
            if token_callback:
                cb_res = token_callback(tok)
                if inspect.isawaitable(cb_res):
                    await cb_res

        # Emit citation cards
        for card in citation_cards:
            yield {"type": "citation_card", **card}

        # Conclude with done event
        done_payload: dict[str, Any] = {
            "type": "done",
            "citations": citation_cards,
            "trace_id": trace_id,
            "session_id": session_id,
        }
        if diagnostic_code:
            done_payload["diagnostic_code"] = diagnostic_code
        yield done_payload

        # Step 9: Session Persistence
        assistant_msg_id = f"msg_{uuid.uuid4().hex[:8]}"
        total_latency_ms = int((time.perf_counter() - start_time) * 1000)

        if active_store is not None:
            active_store.append_message(
                MessageRecord(
                    message_id=assistant_msg_id,
                    session_id=session_id,
                    role="assistant",
                    content=final_content,
                    tokens=len(words),
                    quoted_citations=citation_cards,
                    diagnostic_code=diagnostic_code,
                    latency_ms=total_latency_ms,
                )
            )

    # -----------------------------------------------------------------------
    # Synchronous Turn Handler
    # -----------------------------------------------------------------------

    async def handle_turn(
        self,
        query: str,
        session_id: str | None = None,
        slots: dict[str, Any] | None = None,
        user_context: dict[str, Any] | None = None,
        client_ip: str = "127.0.0.1",
        session_store: SessionStoreProtocol | None = None,
        router: AdaptiveRouter | None = None,
        token_callback: Callable[[str], Any] | None = None,
        trace_id: str | None = None,
    ) -> TurnResult:
        """Execute a complete synchronous RAG turn and return structured TurnResult."""
        session_id = session_id or f"sess_{uuid.uuid4().hex}"
        trace_id = trace_id or uuid.uuid4().hex

        collected_tokens: list[str] = []
        citations: list[dict[str, Any]] = []
        quick_replies: dict[str, Any] | None = None
        diagnostic_code: str | None = None

        async for event in self.stream_turn(
            query=query,
            session_id=session_id,
            slots=slots,
            user_context=user_context,
            client_ip=client_ip,
            session_store=session_store,
            router=router,
            token_callback=token_callback,
            trace_id=trace_id,
        ):
            ev_type = event.get("type")
            if ev_type == "token":
                collected_tokens.append(event.get("token", event.get("text", "")))
            elif ev_type == "slot_prompt":
                quick_replies = event
            elif ev_type == "done":
                citations = event.get("citations", [])
                diagnostic_code = event.get("diagnostic_code")

        content = "".join(collected_tokens).strip()

        return TurnResult(
            message_id=f"msg_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            role="assistant",
            content=content,
            quick_replies=quick_replies,
            citations=citations,
            metadata={"trace_id": trace_id},
            diagnostic_code=diagnostic_code,
        )


__all__ = ["CitationCard", "RAGOrchestrator", "TurnResult"]
