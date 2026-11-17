"""tests/unit/test_flashrank_reranker.py

Unit tests for FlashRankReranker local ONNX cross-encoder reranker adapter.
"""

from unittest.mock import patch

import pytest

from cuk_assistant.core.protocols.reranker import RerankerProtocol
from cuk_assistant.core.registry import get_reranker_cls
from cuk_assistant.retrieval.flashrank_reranker import FlashRankReranker
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.retrieval import ScoredChunk


class TestFlashRankReranker:
    """Validate FlashRankReranker implementation and protocol conformance."""

    def test_protocol_conformance(self) -> None:
        reranker = FlashRankReranker()
        assert isinstance(reranker, RerankerProtocol)

    def test_registered_in_component_registry(self) -> None:
        cls = get_reranker_cls("flashrank")
        assert cls is FlashRankReranker

    def test_rerank_candidates_reordering(self) -> None:
        reranker = FlashRankReranker()
        c1 = ScoredChunk(
            chunk={
                "chunk_id": "c1",
                "text_content": "Notice regarding annual sports day and basketball tournament.",
            },
            score=0.9,  # artifically high prior score
        )
        c2 = ScoredChunk(
            chunk={
                "chunk_id": "c2",
                "text_content": "Detailed syllabus and credit matrix for Biotechnology semester 3.",
            },
            score=0.4,  # lower prior score
        )

        query = "Biotechnology curriculum and syllabus"
        results = reranker.rerank(query=query, candidates=[c1, c2], top_k=2)

        assert len(results) == 2
        # c2 should be boosted to the top because it's directly about Biotechnology syllabus
        assert results[0].chunk_id == "c2"
        assert results[1].chunk_id == "c1"
        assert results[0].score > results[1].score

    def test_rerank_top_k_limiting(self) -> None:
        reranker = FlashRankReranker()
        candidates = [
            ScoredChunk(
                chunk={"chunk_id": f"c_{i}", "text_content": f"University document paragraph {i}"},
                score=0.5,
            )
            for i in range(10)
        ]
        results = reranker.rerank(query="University", candidates=candidates, top_k=3)
        assert len(results) == 3

    def test_rerank_empty_candidates(self) -> None:
        reranker = FlashRankReranker()
        assert reranker.rerank(query="query", candidates=[], top_k=5) == []

    def test_rerank_with_chunk_record(self) -> None:
        reranker = FlashRankReranker()
        record = ChunkRecord(
            chunk_id="doc1::c0",
            doc_id="doc1",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Fee structure for B.Tech admission at CUK.",
            token_count=10,
        )
        cand = ScoredChunk(chunk=record, score=0.3)
        results = reranker.rerank(query="fee structure", candidates=[cand], top_k=1)
        assert len(results) == 1
        assert results[0].chunk_id == "doc1::c0"
        assert results[0].score > 0.5

    def test_flashrank_cache_dir_precedence_explicit(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLASHRANK_CACHE_PATH", "/env/cache")
        with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
            reranker = FlashRankReranker(cache_dir="/explicit/cache")
            assert reranker._cache_dir == "/explicit/cache"
            assert mock_ranker.call_args.kwargs["cache_dir"] == "/explicit/cache"

    def test_flashrank_cache_dir_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("FLASHRANK_CACHE_PATH", "/env/model_cache/flashrank")
        with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
            reranker = FlashRankReranker()
            assert reranker._cache_dir == "/env/model_cache/flashrank"
            assert mock_ranker.call_args.kwargs["cache_dir"] == "/env/model_cache/flashrank"

    def test_flashrank_cache_dir_fallback_opt_cache(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLASHRANK_CACHE_PATH", raising=False)
        monkeypatch.delenv("FLASHRANK_CACHE_DIR", raising=False)
        with patch("cuk_assistant.retrieval.flashrank_reranker.DEFAULT_OPT_CACHE") as mock_opt:
            mock_opt.is_dir.return_value = True
            mock_opt.__str__.return_value = "/opt/model_cache/flashrank"
            with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
                reranker = FlashRankReranker()
                assert reranker._cache_dir == "/opt/model_cache/flashrank"
                assert mock_ranker.call_args.kwargs["cache_dir"] == "/opt/model_cache/flashrank"

    def test_flashrank_cache_dir_fallback_tmp(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("FLASHRANK_CACHE_PATH", raising=False)
        monkeypatch.delenv("FLASHRANK_CACHE_DIR", raising=False)
        with patch("cuk_assistant.retrieval.flashrank_reranker.DEFAULT_OPT_CACHE") as mock_opt:
            mock_opt.is_dir.return_value = False
            with patch("cuk_assistant.retrieval.flashrank_reranker.Ranker") as mock_ranker:
                reranker = FlashRankReranker()
                assert reranker._cache_dir == "/tmp"
                assert mock_ranker.call_args.kwargs["cache_dir"] == "/tmp"
