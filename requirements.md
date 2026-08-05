# CUK AI Assistant — Project Handoff Package

*Generated from scoping session in AgenticCodingLab on 2026-07-27. Paste this into the CUK AI Assistant's own Claude Project as the starting point for `requirements.md`, `design-log.md`, and the File Map.*

---

## Project Goal

Build a web-embeddable AI chatbot that answers student questions on admissions, courses, and deadlines using official university data — built entirely on free-tier tools and services, but architected from day one so the university can later adopt it as a plugin on their own site, swap in a paid LLM, and increase sync frequency/relevance without a rewrite.

---

## Requirements Summary

| Area | Decision |
|---|---|
| **Interface** | Web chat widget, delivered as a single embeddable `<script>` tag (plugin-style) so the university can drop it into their existing site later |
| **Data source** | Public CUK website (admissions, courses, deadlines) — scraped, not an official API |
| **Sync freshness** | Event-driven: a watcher detects page changes and triggers reprocessing of only what changed, rather than a blanket re-scrape |
| **Retrieval quality** | Semantic chunking + real embeddings + similarity search, not keyword matching — addresses relevance, not just freshness |
| **Runtime LLM (now)** | Gemini Flash-Lite, free tier (1,500 req/day, no card... *see gotcha below*) |
| **Runtime LLM (later)** | Swappable via a provider-adapter interface — no specific paid provider chosen yet, deliberately kept open |
| **Hosting (backend)** | GCP: Cloud Run + Firestore + Pub/Sub + Cloud Scheduler — one ecosystem, one billing dashboard, integrates natively with Gemini |
| **Hosting (widget)** | Static `widget.js` via CDN (Firebase Hosting or Cloud Storage), OR Vercel/Netlify if you prefer to keep frontend separate from GCP |
| **Build tools** | Kiro for spec/design phase → GitHub Copilot / OpenAI Codex CLI / Google Antigravity split across implementation tasks by difficulty/type |
| **Budget** | $0 today across the entire stack |
| **Mobile app (Phase 2)** | PWA — installable on Android + iOS home screens, $0, no store fees. Built after the web widget ships; reuses the same Cloud Run backend and `LLMProvider` adapter rather than a separate codebase. Native app (React Native/Flutter, store-published) is a possible future phase, not scoped now — would reintroduce $99/yr (Apple) + $25 (Google) costs, so only worth it if a store-only capability (e.g. reliable iOS push notifications) becomes a real requirement |

**Known gotcha to plan around:** GCP requires a valid billing account (card on file) to enable Cloud Run/Cloud Functions, even while usage stays inside the Always Free quota. If avoiding a stored card entirely is a hard requirement (not just avoiding charges), flag this before committing to GCP — Vercel/Netlify don't require this for their free tier.

---

## Architecture Overview

**Current architecture summary:**
Three loosely-coupled pieces: (1) an embeddable widget that talks to (2) a Cloud Run backend exposing a chat endpoint, which retrieves relevant chunks from a self-hosted similarity index and calls an LLM through a provider-adapter, and (3) a separate sync pipeline — a watcher function that polls for site changes and publishes events, and a processor function that re-scrapes/re-chunks/re-embeds only the changed pages. The watcher/processor split is the key seam: it's the one piece designed to be swapped out later without touching anything downstream.

```
[widget.js on university site]
        |
        v
[Cloud Run: chat API] --> [LLMProvider adapter] --> [Gemini today / paid model later]
        |
        v
[Similarity search over chunk store]
        ^
        |
[Firestore: chunks + embeddings + source URL + last-updated]
        ^
        |
[Processor function] <-- Pub/Sub "page-changed" event <-- [Watcher function (Cloud Scheduler, polls for changes)]
```

**Scaling considerations:** Sync cost scales with how much changed, not corpus size — important as the course catalog grows. Self-hosted similarity search (Chroma/FAISS in the Cloud Run container) is fine for one university's catalog size but won't scale past a few thousand chunks — would need a real vector DB if this expands to multiple institutions.

**Error handling strategy:** Watcher failures fail silently and retry on the next scheduled run (low stakes — worst case is a stale page for a few hours). Processor failures (scrape/embed errors) dead-letter to a Pub/Sub DLQ and alert rather than silently dropping a page, since a missed deadline update is real-world harm, not just a bug.

**Known bottlenecks / technical debt:**
- Self-hosted similarity search caps out around a few thousand chunks.
- Watcher is polling-based, not a true webhook, until university IT confirms whether their CMS can push change events.
- No auth/rate-limiting on the widget yet — fine for a pilot, needed before real public launch.

---

## Low-Level Design Decisions (seed for `design-log.md`)

| Date | Component/File | Choice made | Why | Alternatives considered |
|---|---|---|---|---|
| 2026-07-27 | Widget delivery | Single `widget.js`, CDN-served, embedded via one `<script>` tag, Shadow DOM for style isolation | One-tag install for the university now; theme-safe if embedded directly into their site later | Full iframe app — heavier, harder to theme-match |
| 2026-07-27 | LLM integration | Provider-adapter interface (`LLMProvider.generate()`), Gemini as first implementation, selected via env var | Swapping to a paid model later is a config change + one adapter class, not a rewrite | Hardcoding Gemini calls directly |
| 2026-07-27 | Retrieval | Section/heading-based chunking (not fixed-length), chunk + embedding + source URL + last-updated stored together; self-hosted similarity search | Directly improves relevance; corpus is small enough for free-tier compute | Managed vector DB (Pinecone, Vertex Vector Search) — both paid |
| 2026-07-27 | Sync trigger | Watcher (Cloud Scheduler, polls for change) → Pub/Sub event → Processor (reprocesses only changed page) | Decouples "detect change" from "act on change" — swap in a real CMS webhook later without touching the processor or anything downstream | Full weekly re-scrape of everything |

---

## File Map (seed — expand as files are created)

| File path | Purpose | Created/modified by task |
|---|---|---|
| `widget.js` | Embeddable chat widget, Shadow DOM isolated | — |
| `backend/chat-handler` | Cloud Run entrypoint, orchestrates retrieval + LLM call | — |
| `backend/llm-providers/gemini.js` | Gemini implementation of `LLMProvider` interface | — |
| `backend/retrieval/similarity-search.js` | Self-hosted chunk similarity search | — |
| `sync/watcher-function` | Polls site for changes, publishes `page-changed` events | — |
| `sync/processor-function` | Subscribes to events, re-scrapes/chunks/embeds one page | — |
| `requirements.md` | Static reference — this document | — |
| `design-log.md` | Living technical decision log | — |
| `tasks.md` | Static task list — progress tracked via your own reports, not assumed | — |

---

## Phase 2: Mobile (PWA) — not in scope for initial Kiro spec

**Approach:** Progressive Web App, not a native app. Installs on Android + iOS home screens directly from the browser — no Apple Developer Program ($99/yr) or Google Play fee ($25), no app-store review.

**Why it's low-incremental-cost:** it's the same widget UI plus a web app manifest and a service worker, talking to the same Cloud Run backend through the same `LLMProvider` adapter — not a parallel codebase or a second retrieval/LLM integration.

**Known trade-off to revisit at build time:** iOS PWA support (push notifications, storage limits) lags Android's and has shifted a few times under regulatory pressure — re-check current behavior before committing to any push-notification-dependent feature (e.g. deadline alerts).

**Trigger for reconsidering native instead:** only if a store-only capability becomes a hard requirement — otherwise PWA stays the plan.

---

## Next Concrete Steps

1. Set up a dedicated Claude Project for "CUK AI Assistant" — copy in `design-log-template.md`, this handoff doc as `requirements.md`, and start `tasks.md` + File Map there.
2. Ask university IT whether their CMS can push a webhook on publish — determines whether the watcher stays permanent or gets replaced.
3. Decide widget hosting: GCP-native (Firebase Hosting, one ecosystem, requires card on file) vs. Vercel/Netlify (separate from GCP, no card required) for just the static widget.
4. Use Kiro to generate the formal spec artifacts (requirements → design → tasks) from this handoff before splitting implementation tasks across Copilot/Codex/Antigravity.

---

### Handoff Log
| Date | From tool | To tool | Reason for handoff |
|---|---|---|---|
| 2026-07-27 | AgenticCodingLab (scoping) | CUK AI Assistant (own Claude Project) | Project moved from meta-scoping to real implementation planning |
