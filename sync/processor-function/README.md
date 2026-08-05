# sync/processor-function/

Subscribes to `page-changed` events. Re-scrapes, re-chunks, and re-embeds
only the changed page, then updates Firestore. Failures dead-letter to a
Pub/Sub DLQ and alert — a missed deadline update is real-world harm, not
just a bug.
