# backend/chat-handler/

Cloud Run entrypoint. Orchestrates: receive question -> retrieve relevant
chunks (via `backend/retrieval`) -> call LLM (via `backend/llm-providers`) ->
return answer.
