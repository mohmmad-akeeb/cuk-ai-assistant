# Design Log — CUK AI Assistant

Copied from `design-log-template.md` in AgenticCodingLab. Purely technical:
code/architecture-level choices and their consequences. Project-level calls
(which tool to use, quota tradeoffs) belong in a separate decision log, not here.

---

## Low-Level Design Decisions
*One entry per non-obvious implementation choice.*

| Date | Component/File | Choice made | Why | Alternatives considered |
|---|---|---|---|---|
| 2026-07-27 | Widget delivery | Single `widget.js`, CDN-served, embedded via one `<script>` tag, Shadow DOM for style isolation | One-tag install for the university now; theme-safe if embedded directly into their site later | Full iframe app — heavier, harder to theme-match |
| 2026-07-27 | LLM integration | Provider-adapter interface (`LLMProvider.generate()`), Gemini as first implementation, selected via env var | Swapping to a paid model later is a config change + one adapter class, not a rewrite | Hardcoding Gemini calls directly |
| 2026-07-27 | Retrieval | Section/heading-based chunking (not fixed-length), chunk + embedding + source URL + last-updated stored together; self-hosted similarity search | Directly improves relevance; corpus is small enough for free-tier compute | Managed vector DB (Pinecone, Vertex Vector Search) — both paid |
| 2026-07-27 | Sync trigger | Watcher (Cloud Scheduler, polls for change) → Pub/Sub event → Processor (reprocesses only changed page) | Decouples "detect change" from "act on change" — swap in a real CMS webhook later without touching the processor or anything downstream | Full weekly re-scrape of everything |

## High-Level Architecture Notes

**Current architecture summary:**
Three loosely-coupled pieces: (1) an embeddable widget that talks to (2) a
Cloud Run backend exposing a chat endpoint, which retrieves relevant chunks
from a self-hosted similarity index and calls an LLM through a
provider-adapter, and (3) a separate sync pipeline — a watcher function that
polls for site changes and publishes events, and a processor function that
re-scrapes/re-chunks/re-embeds only the changed pages.

**Scaling considerations:**
Sync cost scales with how much changed, not corpus size. Self-hosted
similarity search is fine for one university's catalog but won't scale past
a few thousand chunks.

## Error Handling Strategy
- Watcher failures: fail silently, retry on next scheduled run (low stakes).
- Processor failures (scrape/embed errors): dead-letter to Pub/Sub DLQ + alert
  (a missed deadline update is real-world harm, not just a bug).

## Known Bottlenecks / Technical Debt
- Self-hosted similarity search caps out around a few thousand chunks.
- Watcher is polling-based, not a true webhook, until university IT confirms
  whether their CMS can push change events.
- No auth/rate-limiting on the widget yet — fine for a pilot, needed before
  real public launch.

---

## Change Log
| Date | What changed | Related task |
|---|---|---|
| 2026-08-05 | Repo initialized, seeded from AgenticCodingLab handoff doc | Repo setup |
