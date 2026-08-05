# backend/llm-providers/

`LLMProvider` adapter interface (`generate()`, `embed()`, etc.) plus concrete
implementations. Gemini is the first implementation (free tier). Swapping to
a paid provider later should mean: add one new adapter class + change a
config value — not touch `chat-handler` or anything downstream.
