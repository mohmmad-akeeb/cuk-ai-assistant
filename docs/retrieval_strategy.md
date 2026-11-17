# Retrieval Strategy

The retrieval strategy employs hybrid search (Dense + Sparse) to ensure high-quality, relevant context retrieval.

## Architectural Design
- Uses Dependency Injection (DI) through protocol-defined interfaces.
- `EmbeddingModelProtocol` provides dense vector embeddings.
- `VectorStoreProtocol` provides hybrid search (LanceDB + Tantivy BM25) and Reciprocal Rank Fusion.
- `RerankerProtocol` ensures top-k results are re-scored using a cross-encoder model.

## Key Components
- `cuk_assistant/core/protocols/storage.py`: Defines `EmbeddingModelProtocol` and `VectorStoreProtocol`.
- `cuk_assistant/core/protocols/reranker.py`: Defines `RerankerProtocol`.
- `cuk_assistant/retrieval/`: Contains concrete implementation adapters.
