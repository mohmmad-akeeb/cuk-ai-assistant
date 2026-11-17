# Graph Report - cuk-rag-chatbot  (2026-11-18)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 3022 nodes · 7138 edges · 128 communities (70 shown, 58 thin omitted)
- Extraction: 87% EXTRACTED · 13% INFERRED · 0% AMBIGUOUS · INFERRED: 920 edges (avg confidence: 0.9)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `0179b4c0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- MenuHierarchyMiner
- typing
- CachedClient
- pathlib
- factory.py
- route_walker.py
- ParsedDocument
- ChunkType
- HybridRetrievalCoordinator
- LangfuseTelemetrySink
- telemetry.py
- AdaptiveRouter
- DirectApiClient
- test_retrieval_coordinator.py
- InMemoryTelemetrySink
- test_failure_attribution.py
- TwoTierReconciler
- TelemetrySinkProtocol
- node_crawler.py
- test_evaluator.py
- .retrieve
- re
- test_schemas_metadata.py
- ChunkRecord
- json
- LLMProviderPool
- process_query
- ui
- MockUserSession
- evaluator.py
- ingestion_filter
- .stream_turn
- SQLiteSessionStore
- parse_html
- test_llm_clients.py
- PdfFactExtractor
- schemas/__init__.py
- GeminiClient
- HierarchicalChunker
- normalize/pipeline.py
- asyncio
- MessageRecord
- FastEmbedAdapter
- _load
- build_metadata
- TestClient
- FailureDiagnosticCode
- GroqClient
- CircuitBreaker
- docling_adapter.py
- IngestionPipelineRunner
- consolidate_documents.py
- TokenBucket
- RateLimiterMiddleware
- test_chainlit_ui.py
- evals/cli.py
- InputGuardResult
- test_offline_parser.py
- FlashRankReranker
- TestCentralFactoryAssembly
- on_message
- input_guard.py
- GroqLlamaGuardRail
- parsers/html_parser.py
- normalise_url
- ingestion.py
- test_output_guard.py
- hierarchical_chunker.py
- DeltaDetector
- SyllabusDocMetadata
- run
- .validate_and_scrub
- delta_detector.py
- AnswerWithCitations
- FailureEvent
- OfflineHtmlParser
- TestClient
- GroqLlamaGuardOutputRail
- SessionRecord
- test_client
- register_telemetry_sink
- guardrails/__init__.py
- TestVerbatimCitationVerifier
- StudentPIIScrubber
- UniversalDocMetadata
- _load_nodes
- .parse_file
- LLMClientProtocol
- _load_docs
- TestInMemoryTelemetrySink
- TestRequiredFields
- ._send_with_retry
- _HeadingStack
- _doc_id
- .evaluate_document
- test_acceptance.py
- sources.yaml
- format_context_chunks
- get_ui_telemetry_sink
- TestIdempotency
- MockTelemetrySink
- TestStarterMenuEndpoint
- TestSessionEndpoints
- TestSyncChatEndpoint
- TestAppInfrastructure
- on_chat_start
- TestStaffPageDoc
- TestZoologyMenuExpansion
- auto_post_tasks.sh
- cuk-assistant

## God Nodes (most connected - your core abstractions)
1. `FailureDiagnosticCode` - 78 edges
2. `ChunkRecord` - 74 edges
3. `ScoredChunk` - 67 edges
4. `InMemoryTelemetrySink` - 66 edges
5. `SQLiteSessionStore` - 52 edges
6. `DirectApiClient` - 46 edges
7. `ChunkType` - 45 edges
8. `AnswerWithCitations` - 45 edges
9. `AdaptiveRouter` - 41 edges
10. `HybridRetrievalCoordinator` - 41 edges

## Surprising Connections (you probably didn't know these)
- `TestCentralFactoryAssembly` --uses--> `SessionStoreProtocol`  [INFERRED]
  tests/unit/test_factory_and_orchestrator.py → cuk_assistant/core/protocols/session.py
- `test_protocol_conformance()` --uses--> `SessionStoreProtocol`  [INFERRED]
  tests/unit/test_session_store.py → cuk_assistant/core/protocols/session.py
- `TestAdaptiveRouterBasics` --uses--> `RoutingDecision`  [INFERRED]
  tests/unit/test_router.py → cuk_assistant/agent/router.py
- `TestDataModels` --uses--> `SpanAttributes`  [INFERRED]
  tests/unit/test_failure_attribution.py → cuk_assistant/core/protocols/telemetry.py
- `MockTelemetrySink` --uses--> `FailureDiagnosticCode`  [INFERRED]
  tests/unit/test_reconciliation.py → cuk_assistant/core/protocols/telemetry.py

## Import Cycles
- None detected.

## Communities (128 total, 58 thin omitted)

### Community 0 - "MenuHierarchyMiner"
Cohesion: 0.05
Nodes (18): get_starter_menu(), MenuCategory, MenuItem, StarterMenuResponse, MenuHierarchyMiner, _add_item(), Document, TestDocumentSchemaValidation (+10 more)

### Community 1 - "typing"
Cohesion: 0.05
Nodes (11): get_telemetry_sink(), get_health(), get_readiness(), HealthResponse, delete_session(), get_session(), _get_session_meta(), get_session_store() (+3 more)

### Community 2 - "CachedClient"
Cohesion: 0.06
Nodes (16): cache_key(), _cache_paths(), CachedClient, CachedResponse, CircuitBreakerError, _read_cache(), _update_meta_fetched_at(), _write_cache() (+8 more)

### Community 3 - "pathlib"
Cohesion: 0.06
Nodes (15): _env(), load_settings(), _project_root(), _resolve(), JsonLinesHandler, setup_logging(), build_nodes_command(), crawl_command() (+7 more)

### Community 4 - "factory.py"
Cohesion: 0.06
Nodes (21): get_orchestrator(), create_citation_verifier(), create_guardrails(), create_input_guard(), create_llm_pool(), create_output_guard(), create_rag_orchestrator(), create_router() (+13 more)

### Community 5 - "route_walker.py"
Cohesion: 0.05
Nodes (24): Settings, _build(), _build(), download_pdf_cached(), ManifestEntry, ManifestWriter, _angular_url(), build_node_table() (+16 more)

### Community 6 - "ParsedDocument"
Cohesion: 0.05
Nodes (13): DocumentParserProtocol, ParsedDocument, DoclingPdfParser, _is_docling_available(), TestDoclingAdapterHtmlParsing, TestDoclingAdapterPdfParsing, TestDoclingAdapterProtocol, TestChunkTypeEnum (+5 more)

### Community 7 - "ChunkType"
Cohesion: 0.05
Nodes (9): get_vector_store_cls(), _compute_dir_size_mb(), index_main(), LanceDBStore, ChunkType, ParentChunkContainer, temp_lancedb_store(), TestLanceDBStore (+1 more)

### Community 8 - "HybridRetrievalCoordinator"
Cohesion: 0.06
Nodes (12): create_embedding_model(), create_reranker(), create_retrieval_coordinator(), RerankerProtocol, EmbeddingModelProtocol, VectorStoreProtocol, get_reranker_cls(), list_registered_components() (+4 more)

### Community 9 - "LangfuseTelemetrySink"
Cohesion: 0.07
Nodes (8): LangfuseTelemetrySink, _sanitize_trace_id(), PhoenixTelemetrySink, _to_any_value(), _to_otlp_id(), TestLangfuseTelemetrySink, TestPhoenixTelemetrySink, TestProtocolAdherence

### Community 10 - "telemetry.py"
Cohesion: 0.06
Nodes (9): RoutingDecision, AcademicIntentType, FacetedSlotFiller, QuickReplyOption, QuickReplyPayload, SlotChipPayload, SlotFillingResult, SpanAttributes (+1 more)

### Community 11 - "AdaptiveRouter"
Cohesion: 0.07
Nodes (5): AdaptiveRouter, RouteDestination, get_router(), TestAdaptiveRouterBasics, TestAdaptiveRouterIntegration

### Community 12 - "DirectApiClient"
Cohesion: 0.09
Nodes (7): DirectApiClient, _payload_suffix(), _sanitize_guid(), _unpack_list(), _fetch_node_content(), build_node_table(), TestDirectApiClientAlignment

### Community 13 - "test_retrieval_coordinator.py"
Cohesion: 0.08
Nodes (6): make_chunk_record(), MockEmbeddingModel, MockReranker, MockTelemetrySink, MockVectorStore, TestHybridRetrievalCoordinator

### Community 14 - "InMemoryTelemetrySink"
Cohesion: 0.07
Nodes (3): InMemoryTelemetrySink, TelemetryRecord, TestFeedbackEndpoint

### Community 15 - "test_failure_attribution.py"
Cohesion: 0.09
Nodes (14): ContextTruncationException, CorpusMissingContentException, DiagnosticError, GuardrailBlockedException, LLMExtractionFailureException, LLMFormatViolationException, LLMHallucinationException, MissedTopRankedException (+6 more)

### Community 16 - "TwoTierReconciler"
Cohesion: 0.09
Nodes (4): TwoTierReconciler, TestPolymorphicDomainRouting, TestTwoTierReconcilerBasics, TestUniversalIngestionGuarantee

### Community 17 - "TelemetrySinkProtocol"
Cohesion: 0.07
Nodes (4): create_telemetry_sink(), TelemetrySinkProtocol, get_telemetry_sink_cls(), TestFactoryCreation

### Community 18 - "node_crawler.py"
Cohesion: 0.08
Nodes (20): _angular_url(), _add_node(), _extract_content_params(), fetch_all_nodes(), _fetch_node_content(), _is_real_external(), _node_id(), _node_key() (+12 more)

### Community 19 - "test_evaluator.py"
Cohesion: 0.11
Nodes (21): is_chunk_relevant(), RAGEvaluator, GoldenTestCase, _make_dummy_chunk(), MockRetrievalCoordinator, test_compute_citation_metrics_grounded(), test_compute_citation_metrics_hallucinated(), test_evaluate_dataset_summary() (+13 more)

### Community 20 - ".retrieve"
Cohesion: 0.06
Nodes (5): extract_circular_reference(), format_where_filter(), __getattr__(), TestLiveHybridRetrieval, TestHelpers

### Community 21 - "re"
Cohesion: 0.09
Nodes (15): clean_guid(), extract_batch_year(), extract_circular_reference(), extract_course_code(), normalize_academic_year(), normalize_iso_date(), normalize_semester(), normalize_title() (+7 more)

### Community 22 - "test_schemas_metadata.py"
Cohesion: 0.09
Nodes (15): AdmissionDocMetadata, GeneralDocMetadata, NoticeDocMetadata, OrdinanceDocMetadata, parse_document_metadata(), ResultDocMetadata, TenderDocMetadata, _utc_now_iso() (+7 more)

### Community 23 - "ChunkRecord"
Cohesion: 0.09
Nodes (6): ChunkRecord, ScoredChunk, MockCoordinatorForApi, MockCoordinator, TestChunkRecordSchema, TestScoredChunkModel

### Community 24 - "json"
Cohesion: 0.09
Nodes (18): _content_hash(), nodes_to_jsonl(), _extract_embedded_date(), extract_pdf(), _extract_title_from_pdf(), _build_dept_page_doc(), _build_faculty_doc(), _endpoint_section() (+10 more)

### Community 25 - "LLMProviderPool"
Cohesion: 0.10
Nodes (3): LLMProviderPool, MockLLMClient, TestLLMProviderPool

### Community 26 - "process_query"
Cohesion: 0.08
Nodes (3): process_query(), TestProcessQuery, mock_stream()

### Community 27 - "ui"
Cohesion: 0.06
Nodes (37): build, command, condition, container_name, environment, healthcheck, networks, ports (+29 more)

### Community 29 - "evaluator.py"
Cohesion: 0.08
Nodes (6): EvaluationSummary, TestCaseEvalResult, evaluator(), golden_eval_summary(), TestGoldenDatasetRegression, test_evaluate_empty_dataset()

### Community 30 - "ingestion_filter"
Cohesion: 0.06
Nodes (35): blacklist_broken_endpoints, rate_limits, recommended_max_connections, slow_endpoints_timeout_seconds, pre_nep_policy, superseded_handling, superseded_programs, drop_exact_content_hash_duplicates (+27 more)

### Community 32 - "SQLiteSessionStore"
Cohesion: 0.08
Nodes (4): SQLiteSessionStore, test_error_handling_and_edge_cases(), test_protocol_conformance(), test_rate_limiting()

### Community 33 - "parse_html"
Cohesion: 0.09
Nodes (14): _classify_href(), _extract_text_and_links(), _walk(), LinkOut, _normalize_href(), parse_html(), ParsedHTML, _remove_inner_nav_bar() (+6 more)

### Community 34 - "test_llm_clients.py"
Cohesion: 0.14
Nodes (5): LLMError, LLMFormatError, RateLimitError, ServiceUnavailableError, CircuitState

### Community 35 - "PdfFactExtractor"
Cohesion: 0.11
Nodes (5): PdfFactExtractor, PdfIntrinsicFacts, TestMetadataAndChunkEnrichment, TestPdfFactExtractorDatesAndAuthorities, TestPdfFactExtractorReferenceNumbers

### Community 36 - "schemas/__init__.py"
Cohesion: 0.08
Nodes (9): chat_stream(), chat_sync(), _extract_client_ip(), record_feedback(), ChatRequest, ChatResponse, CitationCard, FeedbackRequest (+1 more)

### Community 37 - "GeminiClient"
Cohesion: 0.12
Nodes (3): GeminiClient, TestGeminiClient, handler()

### Community 38 - "HierarchicalChunker"
Cohesion: 0.11
Nodes (6): HierarchicalChunker, TestBodyTextSplittingWithOverlap, TestCodeFenceAndContainers, TestHeadingHierarchyAndBreadcrumbs, TestMarkdownTableAtomicity, TestParentChildAndBidirectionalChaining

### Community 39 - "normalize/pipeline.py"
Cohesion: 0.13
Nodes (13): __getattr__(), _content_hash(), _infer_doc_type(), _parse_grouped_pdf(), parse_manifest(), _parse_single_api(), _parse_single_html(), ParseStats (+5 more)

### Community 40 - "asyncio"
Cohesion: 0.12
Nodes (7): on_feedback_downvote(), on_feedback_upvote(), on_slot_selected(), on_starter_prompt(), MockAction, TestFeedbackCallbacks, TestOnSlotSelected

### Community 41 - "MessageRecord"
Cohesion: 0.11
Nodes (7): MessageRecord, test_append_message_and_get_session_history(), test_concurrent_writes_wal(), worker(), test_context_window_sliding_memory(), test_delete_session_cascades(), test_save_summary_and_get_latest_summary()

### Community 42 - "FastEmbedAdapter"
Cohesion: 0.11
Nodes (3): get_embedding_model_cls(), FastEmbedAdapter, TestFastEmbedAdapter

### Community 43 - "_load"
Cohesion: 0.15
Nodes (6): _load(), TestContactEmailRequired, TestDefaults, TestOverrides, TestPaths, TestUserAgent

### Community 44 - "build_metadata"
Cohesion: 0.11
Nodes (12): build_metadata(), _build_page_url(), _extract_academic_year(), _file_url_permissive(), _format_date(), _iso(), _normalize_title(), _resolve_audience() (+4 more)

### Community 45 - "TestClient"
Cohesion: 0.09
Nodes (3): TestChatStreamingEndpoint, TestHealthEndpoints, TestRateLimiterMiddleware

### Community 46 - "FailureDiagnosticCode"
Cohesion: 0.12
Nodes (4): FailureDiagnosticCode, DiagnosticAttributor, DiagnosticMetadata, TestDiagnosticTaxonomyMatrix

### Community 48 - "CircuitBreaker"
Cohesion: 0.16
Nodes (3): CircuitBreaker, FakeClock, TestCircuitBreakerStateMachine

### Community 49 - "docling_adapter.py"
Cohesion: 0.13
Nodes (4): BaseParser, LinkOut, ParsedPdf, OfflinePdfParser

### Community 50 - "IngestionPipelineRunner"
Cohesion: 0.10
Nodes (5): ingest_main(), IngestionPipelineRunner, IngestionStats, TestCukIngestCli, TestIngestionPipelineRunner

### Community 51 - "consolidate_documents.py"
Cohesion: 0.11
Nodes (8): _find_pdf_path(), main(), _make_asset_id(), _consolidate_pdf_group(), _get_html_key(), _get_pdf_key(), _is_more_complete(), main()

### Community 52 - "TokenBucket"
Cohesion: 0.16
Nodes (3): TokenBucket, TestTokenBucketAcquire, TestTokenBucketInit

### Community 53 - "RateLimiterMiddleware"
Cohesion: 0.12
Nodes (7): ApiErrorEnvelope, create_app(), http_exception_handler(), unhandled_exception_handler(), validation_exception_handler(), RateLimiterMiddleware, _get_rate_limiter_from_app()

### Community 54 - "test_chainlit_ui.py"
Cohesion: 0.11
Nodes (4): clean_mock_state(), teardown_module(), TestModuleTeardown, TestOnStarterPrompt

### Community 55 - "evals/cli.py"
Cohesion: 0.14
Nodes (3): main(), mine_queries(), run()

### Community 57 - "test_offline_parser.py"
Cohesion: 0.13
Nodes (5): aggregate_asset_references(), mask_email(), sanitize_record_dict(), TestParseManifestEndToEnd, TestSanitizerAndAggregator

### Community 60 - "on_message"
Cohesion: 0.12
Nodes (5): send_wrapper(), on_message(), MockMessage, MockText, TestOnMessage

### Community 61 - "input_guard.py"
Cohesion: 0.16
Nodes (3): FailureDiagnosticCode, LocalDomainClassifier, TestLocalDomainClassifier

### Community 63 - "parsers/html_parser.py"
Cohesion: 0.17
Nodes (5): _classify_href(), _normalize_href(), parse_html(), _remove_inner_nav(), _table_to_markdown()

### Community 66 - "test_output_guard.py"
Cohesion: 0.15
Nodes (3): GuardrailProtocol, OutputGuardResult, TestGuardrailProtocolConformance

### Community 67 - "hierarchical_chunker.py"
Cohesion: 0.18
Nodes (4): estimate_tokens(), is_table_row(), is_table_separator(), TestHierarchicalChunkerBasics

### Community 68 - "DeltaDetector"
Cohesion: 0.19
Nodes (3): DeltaDetector, TestDeltaDetectorProtocol, TestStateManagementAndPersistence

### Community 72 - "delta_detector.py"
Cohesion: 0.16
Nodes (3): DeltaRecord, DeltaStatus, TestTombstoneDetection

### Community 73 - "AnswerWithCitations"
Cohesion: 0.18
Nodes (3): AnswerWithCitations, MockLLMForApi, TestAnswerWithCitationsSchema

### Community 74 - "FailureEvent"
Cohesion: 0.18
Nodes (4): FailureEvent, FeedbackEvent, TestDataModels, TestSpanFormatting

### Community 76 - "OfflineHtmlParser"
Cohesion: 0.23
Nodes (4): OfflineApiParser, ParsedHTML, OfflineHtmlParser, TestOfflineParsers

### Community 80 - "SessionRecord"
Cohesion: 0.17
Nodes (3): _parse_datetime(), SessionRecord, test_get_or_create_session()

### Community 81 - "test_client"
Cohesion: 0.15
Nodes (4): memory_session_store(), memory_session_store(), memory_telemetry_sink(), test_client()

### Community 82 - "register_telemetry_sink"
Cohesion: 0.19
Nodes (5): register_embedding_model(), register_reranker(), register_telemetry_sink(), register_vector_store(), decorator()

### Community 86 - "UniversalDocMetadata"
Cohesion: 0.23
Nodes (4): FacultyDocMetadata, UniversalDocMetadata, TestFacultyDocMetadata, TestUniversalDocMetadata

### Community 87 - "_load_nodes"
Cohesion: 0.19
Nodes (3): _load_nodes(), TestBiotechnologyMenuCoverage, TestSchoolCoverage

### Community 98 - "sources.yaml"
Cohesion: 0.29
Nodes (6): api_base, base_url, deny_external, extra_routes, max_connections, rate_limit_rps

## Knowledge Gaps
- **1 isolated node(s):** `cuk-assistant`
  These have ≤1 connection - possible missing edges. (Counts symbols only; 1242 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **58 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `FailureDiagnosticCode` connect `FailureDiagnosticCode` to `typing`, `factory.py`, `ParsedDocument`, `HybridRetrievalCoordinator`, `LangfuseTelemetrySink`, `telemetry.py`, `test_retrieval_coordinator.py`, `InMemoryTelemetrySink`, `test_failure_attribution.py`, `TwoTierReconciler`, `TelemetrySinkProtocol`, `test_evaluator.py`, `re`, `test_schemas_metadata.py`, `evaluator.py`, `.stream_turn`, `docling_adapter.py`, `FailureEvent`, `Any`, `TestInMemoryTelemetrySink`, `MockTelemetrySink`, `._infer_code_and_component`?**
  _High betweenness centrality (0.075) - this node is a cross-community bridge._
- **Are the 41 inferred relationships involving `FailureDiagnosticCode` (e.g. with `RAGEvaluator` and `TestCaseEvalResult`) actually correct?**
  _`FailureDiagnosticCode` has 41 INFERRED edges - model-reasoned connections that need verification._
- **What connects `cuk-assistant` to the rest of the system?**
  _1 weakly-connected nodes found - possible missing edges._
- **Should `MenuHierarchyMiner` be split into smaller, more focused modules?**
  _Cohesion score 0.05225225225225225 - nodes in this community are weakly interconnected._
- **Why does `ChunkRecord` connect `ChunkRecord` to `MenuHierarchyMiner`, `test_llm_clients.py`, `hierarchical_chunker.py`, `pathlib`, `PdfFactExtractor`, `HierarchicalChunker`, `ParsedDocument`, `ChunkType`, `HybridRetrievalCoordinator`, `factory.py`, `format_context_chunks`, `test_retrieval_coordinator.py`, `IngestionPipelineRunner`, `test_evaluator.py`, `.retrieve`, `FlashRankReranker`?**
  _High betweenness centrality (0.063) - this node is a cross-community bridge._
- **Are the 19 inferred relationships involving `ChunkRecord` (e.g. with `ParsedDocument` and `MenuHierarchyMiner`) actually correct?**
  _`ChunkRecord` has 19 INFERRED edges - model-reasoned connections that need verification._
- **Should `typing` be split into smaller, more focused modules?**
  _Cohesion score 0.048130322102924845 - nodes in this community are weakly interconnected._