"""tests/unit/test_fastembed_adapter.py

Unit tests for FastEmbedAdapter local ONNX dense embedding adapter.
"""

from cuk_assistant.core.protocols.storage import EmbeddingModelProtocol
from cuk_assistant.core.registry import get_embedding_model_cls
from cuk_assistant.ingestion.embedding.fastembed_adapter import FastEmbedAdapter


class TestFastEmbedAdapter:
    """Validate FastEmbedAdapter implementation and protocol conformance."""

    def test_protocol_conformance(self) -> None:
        adapter = FastEmbedAdapter()
        assert isinstance(adapter, EmbeddingModelProtocol)
        assert adapter.dimension == 384

    def test_registered_in_component_registry(self) -> None:
        cls = get_embedding_model_cls("fastembed")
        assert cls is FastEmbedAdapter

    def test_embed_query(self) -> None:
        adapter = FastEmbedAdapter()
        query = "Central University of Kashmir admissions 2024"
        vec = adapter.embed_query(query)
        assert isinstance(vec, list)
        assert len(vec) == 384
        assert all(isinstance(x, float) for x in vec)

    def test_embed_empty_query(self) -> None:
        adapter = FastEmbedAdapter()
        vec = adapter.embed_query("")
        assert len(vec) == 384
        assert all(x == 0.0 for x in vec)

    def test_embed_documents_batching(self) -> None:
        adapter = FastEmbedAdapter()
        texts = [
            "Department of Computer Science and Engineering syllabus",
            "M.Tech admission criteria and eligibility guidelines",
            "Tender notification for campus cafeteria equipment",
        ]
        embeddings = adapter.embed_documents(texts, batch_size=2)
        assert len(embeddings) == len(texts)
        for emb in embeddings:
            assert len(emb) == 384
            assert all(isinstance(x, float) for x in emb)

    def test_embed_texts_alias(self) -> None:
        adapter = FastEmbedAdapter()
        texts = ["Single text test"]
        embeddings = adapter.embed_texts(texts)
        assert len(embeddings) == 1
        assert len(embeddings[0]) == 384

    def test_embed_empty_documents(self) -> None:
        adapter = FastEmbedAdapter()
        assert adapter.embed_documents([]) == []
