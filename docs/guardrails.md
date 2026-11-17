# Guardrails

The guardrails system ensures input query safety, output quality, and factual grounding through verification.

## Architectural Design
- Input Guard: Validates user queries for domain relevance and safety.
- Output Guard: Scrubs PII and verifies factual citations.
- Citation Verifier: Ensures LLM responses are grounded in the retrieved context.

## Key Components
- `cuk_assistant/guardrails/input_guard.py`: Implements input validation.
- `cuk_assistant/guardrails/output_guard.py`: Implements output scrubbing and verification.
- `cuk_assistant/guardrails/citation_verifier.py`: Verifies factual assertions.
