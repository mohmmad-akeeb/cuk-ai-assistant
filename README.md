# CUK AI Assistant

Web-embeddable AI chatbot answering student questions on admissions, courses,
and deadlines, built on official CUK website data.

Architected to later become a plugin on the university's own site, with a
swappable LLM backend and event-driven sync — see `requirements.md` and
`design-log.md`.

## Structure
- `widget/` — embeddable `widget.js` chat widget (Shadow DOM isolated)
- `backend/chat-handler/` — Cloud Run entrypoint, orchestrates retrieval + LLM call
- `backend/llm-providers/` — `LLMProvider` adapter interface + implementations (Gemini first)
- `backend/retrieval/` — self-hosted chunk similarity search
- `sync/watcher-function/` — detects CUK site page changes, publishes `page-changed` events
- `sync/processor-function/` — subscribes to events, re-scrapes/chunks/embeds one page

## Docs
- `requirements.md` — static reference (do not edit ad hoc; regenerate via Kiro if scope changes)
- `design-log.md` — living technical decision log
- `tasks.md` — static task list; completion is tracked by your own reports, not assumed
