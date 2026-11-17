# System Requirements & Failure Taxonomy

## Requirements
- Maintain high-relevance retrieval for academic queries.
- Ensure response groundedness through automated citation verification.
- Provide a robust API and interactive UI.
- Maintain high system availability.

## Failure Taxonomy
When a component fails, the following diagnostic codes are used for attribution:
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
