# backend/retrieval/

Self-hosted similarity search over scraped-and-chunked CUK content
(Chroma/FAISS in the Cloud Run container). Chunks are section/heading-based,
stored with embedding + source URL + last-updated timestamp in Firestore.

Known bottleneck: caps out around a few thousand chunks — fine for one
university's catalog, would need a real vector DB beyond that.
