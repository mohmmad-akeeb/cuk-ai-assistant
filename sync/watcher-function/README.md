# sync/watcher-function/

Polls the CUK site (Cloud Scheduler) for page changes (sitemap/hash diff).
On change, publishes a `page-changed` event to Pub/Sub. Failures retry
silently on the next scheduled run.

This is the swap point: if university IT later provides a real CMS webhook,
it should publish to the same Pub/Sub topic — nothing downstream changes.
