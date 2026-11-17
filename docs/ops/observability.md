# Observability Documentation

## Logfire Integration
The CUK RAG Chatbot uses [Logfire](https://logfire.pydantic.dev/) for structured OpenTelemetry logging and tracing.

- **Requirements**:
  - Every workflow, API endpoint, and async task must emit structured spans.
  - Failure tagging is mandatory.

## Failure Attribution
When a step fails, degrades, or returns an empty result, it MUST be tagged with the precise diagnostic code:
- `GUARDRAIL_BLOCKED`
- `PARSING_DEFECT`
- `QUESTION_PARSING_FAILED`
- `RETRIEVAL_EMPTY`
- `RETRIEVAL_RECALL_MISS`
- `MISSED_TOP_RANKED`
- `CONTEXT_TRUNCATION`
- `LLM_EXTRACTION_FAILURE`
- `LLM_HALLUCINATION`
- `LLM_FORMAT_VIOLATION`
- `OUTPUT_SAFETY_VIOLATION`
- `CORPUS_MISSING_CONTENT`


For implementation details, refer to `cuk_assistant/core/logging_setup.py`.

---

## Related Documentation
- [System Requirements](../requirements.md)
- [System Architecture](../architecture.md)
- [Deployment](deployment.md)
- [Evaluation](evals.md)
