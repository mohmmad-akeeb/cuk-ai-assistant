# LLM Generation + Circuit Breaker Failover

> **Gemini primary, Groq fallback.** The `LLMProviderPool` wraps both providers in per-provider circuit breakers for automatic failover.
>
> Related: [Pipeline Overview](./overview.md)

---

## 1. Purpose

Step 5 of the request pipeline generates a structured answer with citations. The `LLMProviderPool` provides round-robin load balancing and automatic failover when a provider is rate-limited (429) or unavailable (503). Each provider has its own circuit breaker that trips after failures and recovers after a cooloff period.

---

## 2. Circuit Breaker State Machine

```mermaid
stateDiagram-v2
    [*] --> CLOSED: Pool initialized

    CLOSED --> OPEN: record_failure()<br/>failure_count >= threshold<br/>(default threshold = 1)
    note right of CLOSED: Healthy state<br/>All traffic passes

    OPEN --> HALF_OPEN: cooloff elapsed<br/>(default 60s)
    note right of OPEN: Tripped state<br/>All traffic blocked<br/>for this provider

    HALF_OPEN --> CLOSED: record_success()<br/>Probe request succeeded
    note right of HALF_OPEN: Testing state<br/>Single probe request allowed

    HALF_OPEN --> OPEN: record_failure()<br/>Probe request failed
    note right of HALF_OPEN: If probe fails,<br/>trip back to OPEN
```

### State behaviors

| State | `is_available()` | Behavior |
|-------|-----------------|----------|
| `CLOSED` | True | Provider accepts traffic. Failures increment count. |
| `OPEN` | False | Provider blocked. After `cooloff_seconds` (60s), transitions to `HALF_OPEN`. |
| `HALF_OPEN` | True | Single probe request allowed. Success → `CLOSED`, failure → `OPEN`. |

---

## 3. Failover Flow

```mermaid
flowchart TD
    REQUEST["generate_answer() called<br/>query + context_chunks + chat_history"]
    SELECT["Select next healthy provider<br/>_select_next_healthy_provider()"]
    SKIP["Skip providers in tried_providers set"]

    GEMINI["Gemini (primary)<br/>GeminiClient.generate_answer()"]
    GEMINI_CHECK{"Gemini available?<br/>(circuit CLOSED or HALF_OPEN)"}
    GEMINI_TRY["Try Gemini"]
    GEMINI_RESULT{"Success?"}
    GEMINI_SUCCESS["Record success<br/>circuit → CLOSED<br/>Return AnswerWithCitations"]
    GEMINI_FAIL["Record failure<br/>circuit → OPEN<br/>Add to tried_providers"]

    GROQ["Groq (fallback)<br/>GroqClient.generate_answer()"]
    GROQ_CHECK{"Groq available?"}
    GROQ_TRY["Try Groq"]
    GROQ_RESULT{"Success?"}
    GROQ_SUCCESS["Record success<br/>circuit → CLOSED<br/>Return AnswerWithCitations"]
    GROQ_FAIL["Record failure<br/>circuit → OPEN"]

    ALL_FAIL["All providers exhausted<br/>Raise ServiceUnavailableError<br/>diagnostic: LLM_EXTRACTION_FAILURE"]

    REQUEST --> SELECT
    SELECT --> GEMINI_CHECK
    GEMINI_CHECK -->|"Yes"| GEMINI_TRY --> GEMINI_RESULT
    GEMINI_CHECK -->|"No"| GROQ_CHECK
    GEMINI_RESULT -->|"Yes"| GEMINI_SUCCESS
    GEMINI_RESULT -->|"No"| GEMINI_FAIL --> GROQ_CHECK
    GROQ_CHECK -->|"Yes"| GROQ_TRY --> GROQ_RESULT
    GROQ_CHECK -->|"No"| ALL_FAIL
    GROQ_RESULT -->|"Yes"| GROQ_SUCCESS
    GROQ_RESULT -->|"No"| GROQ_FAIL --> ALL_FAIL

    style GEMINI_SUCCESS fill:#1a3a1a,color:#fff
    style GROQ_SUCCESS fill:#1a3a1a,color:#fff
    style ALL_FAIL fill:#3a1a1a,color:#fff
    style GEMINI_FAIL fill:#3a2a1a,color:#fff
    style GROQ_FAIL fill:#3a2a1a,color:#fff
```

### Trip conditions

The `_should_trip_breaker()` method determines if an exception should trip the circuit:

| Exception type | Trip? | Reason |
|----------------|-------|--------|
| `RateLimitError` (429) | Yes | Rate limited — wait and retry later |
| `ServiceUnavailableError` (503) | Yes | Provider down |
| `httpx.HTTPStatusError` 401/403 | Yes | Auth failure — won't recover without config change |
| `httpx.HTTPStatusError` 429 | Yes | Rate limited |
| `httpx.HTTPStatusError` 500/502/503/504 | Yes | Server error |
| `httpx.TransportError` | Yes | Network failure |
| `httpx.TimeoutException` | Yes | Request timed out |
| Other exceptions | No | Propagated immediately (e.g. bad user payload) |

---

## 4. Provider Configuration

| Provider | Model | Priority | Purpose |
|----------|-------|----------|---------|
| Google Gemini | `gemini-flash-latest` (env: `GEMINI_MODEL`) | Primary | Fast, high-quality generation |
| Groq | `qwen3.8-27b` (env: `GROQ_MODEL`) | Fallback | Failover when Gemini is rate-limited |

The factory (`create_llm_pool`) reads API keys from environment variables or `.env` file:

```python
gemini_client = GeminiClient(api_key=gemini_key, model=gemini_model)
groq_client = GroqClient(api_key=groq_key, model=groq_model)
pool = LLMProviderPool(
    providers=[gemini_client, groq_client],
    cooloff_seconds=60.0,
    failure_threshold=1,
)
```

---

## 5. AnswerWithCitations Schema

The LLM returns a structured answer:

```python
class AnswerWithCitations(BaseModel):
    direct_answer: str              # The generated response text
    quoted_snippets: list[str]      # Verbatim quotes from retrieved chunks
    citation_chunk_ids: list[str]   # Chunk IDs cited in the answer
    confidence_score: float         # LLM's confidence [0, 1]
```

The orchestrator uses:
- `direct_answer` → streamed as tokens to the client
- `quoted_snippets` → verified against retrieved chunks by `VerbatimCitationVerifier`
- `citation_chunk_ids` → used to build citation cards

---

## 6. Orchestrator Integration

```mermaid
flowchart TD
    CONTEXT["Context payload<br/>from Step 4 (retrieval)"]
    HISTORY["Chat history<br/>from Step 2 (session)"]
    PERSONA["System persona<br/>(optional)"]

    LLM_POOL["LLMProviderPool.generate_answer()"]
    GEMINI["1. Try Gemini<br/>GeminiClient → Google API"]
    GROQ["2. Try Groq<br/>GroqClient → Groq API"]

    SUCCESS["AnswerWithCitations<br/>direct_answer + quoted_snippets<br/>+ citation_chunk_ids"]
    FAILURE["Exception caught by orchestrator<br/>Tag: LLM_EXTRACTION_FAILURE<br/>Fallback text generated"]

    CONTEXT --> LLM_POOL
    HISTORY --> LLM_POOL
    PERSONA --> LLM_POOL
    LLM_POOL --> GEMINI
    GEMINI -->|"Success"| SUCCESS
    GEMINI -->|"Failure"| GROQ
    GROQ -->|"Success"| SUCCESS
    GROQ -->|"Failure"| FAILURE

    style SUCCESS fill:#1a3a1a,color:#fff
    style FAILURE fill:#3a1a1a,color:#fff
```

### Fallback text on total failure

When all providers are exhausted, the orchestrator generates a fallback:

```python
fallback_text = (
    f"Here is the official information regarding '{query}'. "
    "Please refer to the verified campus documents below for complete regulations."
)
answer = AnswerWithCitations(
    direct_answer=fallback_text,
    quoted_snippets=[],
    citation_chunk_ids=[],
    confidence_score=0.5,
)
```

---

## 7. Error Hierarchy

```mermaid
flowchart TD
    BASE["LLMError<br/>(base exception)"]
    RATE["RateLimitError<br/>HTTP 429"]
    UNAVAIL["ServiceUnavailableError<br/>HTTP 503 / all providers down"]
    FORMAT["LLMFormatError<br/>Response parsing failed"]

    BASE --> RATE
    BASE --> UNAVAIL
    BASE --> FORMAT

    RATE --> TRIP["Trip circuit breaker"]
    UNAVAIL --> TRIP
    FORMAT --> PROP["Propagate to caller<br/>(non-failover error)"]

    style TRIP fill:#3a2a1a,color:#fff
    style PROP fill:#3a1a1a,color:#fff
```

---

## 8. Key Files

| File | Responsibility |
|------|---------------|
| `llm/pool.py` | `LLMProviderPool`, `CircuitBreaker`, `CircuitState` |
| `llm/gemini_client.py` | `GeminiClient` — Google Gemini API client |
| `llm/groq_client.py` | `GroqClient` — Groq API client |
| `core/protocols/llm.py` | `LLMClientProtocol` |
| `schemas/llm.py` | `AnswerWithCitations`, `CitationCard` |
| `core/factory.py` | `create_llm_pool()` — wires providers with API keys |
