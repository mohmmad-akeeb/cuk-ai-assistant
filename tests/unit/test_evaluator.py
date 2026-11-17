"""tests/unit/test_evaluator.py

Unit tests for RAGEvaluator, benchmark metrics, dataset curation, and cuk-eval CLI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from cuk_assistant.core.protocols.telemetry import FailureDiagnosticCode
from cuk_assistant.evals.cli import app
from cuk_assistant.evals.evaluator import RAGEvaluator, is_chunk_relevant
from cuk_assistant.evals.schemas import GoldenTestCase
from cuk_assistant.observability.in_memory_sink import InMemoryTelemetrySink
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.llm import AnswerWithCitations
from cuk_assistant.schemas.retrieval import ScoredChunk


def _make_dummy_chunk(
    chunk_id: str,
    text: str,
    title: str = "Notification",
    source_url: str = "https://www.cukashmir.ac.in/admission/notice.pdf",
    page_url: str = "https://www.cukashmir.ac.in/admissions",
    doc_type: str = "admission",
    score: float = 0.85,
) -> ScoredChunk:
    """Helper to create ScoredChunk for evaluation tests."""
    record = ChunkRecord(
        chunk_id=chunk_id,
        doc_id="doc_001",
        chunk_type=ChunkType.PARAGRAPH,
        text_content=text,
        token_count=len(text.split()),
        chunk_index=0,
        metadata={
            "title": title,
            "source_url": source_url,
            "page_url": page_url,
            "doc_type": doc_type,
            "file_name": Path(source_url).name,
        },
    )
    return ScoredChunk(chunk=record, score=score)


class MockRetrievalCoordinator:
    """Mock HybridRetrievalCoordinator conforming to coordinator interface."""

    def __init__(self, candidates: list[ScoredChunk] | None = None) -> None:
        self.candidates = candidates or []
        self.retrieve_calls: list[dict[str, Any]] = []

    def retrieve(
        self,
        query: str,
        filters: dict[str, Any] | str | None = None,
        top_k: int = 5,
        expand_parent_context: bool = True,
        trace_id: str | None = None,
    ) -> list[ScoredChunk]:
        self.retrieve_calls.append(
            {
                "query": query,
                "filters": filters,
                "top_k": top_k,
                "trace_id": trace_id,
            }
        )
        return self.candidates[:top_k]


# ==============================================================================
# 1. Golden Dataset Quality & Schema Invariants
# ==============================================================================


def test_golden_dataset_file_and_schema() -> None:
    """Ensure evals/golden_dataset.jsonl contains 50+ valid, diverse test cases."""
    dataset_path = Path("evals/golden_dataset.jsonl")
    assert dataset_path.exists(), "evals/golden_dataset.jsonl must exist"

    test_cases: list[GoldenTestCase] = []
    with open(dataset_path, encoding="utf-8") as f:
        for _line_num, line in enumerate(f, start=1):
            line_str = line.strip()
            if not line_str:
                continue
            data = json.loads(line_str)
            tc = GoldenTestCase(**data)
            test_cases.append(tc)

    # 1. Count must be 50+
    assert len(test_cases) >= 50, f"Expected 50+ test cases, found {len(test_cases)}"

    # 2. Check completeness of fields
    eval_ids = set()
    for tc in test_cases:
        assert tc.eval_id not in eval_ids, f"Duplicate eval_id: {tc.eval_id}"
        eval_ids.add(tc.eval_id)

        assert len(tc.query.strip()) > 10, f"Query too short in {tc.eval_id}"
        assert len(tc.expected_keywords) >= 2, f"Expected at least 2 keywords in {tc.eval_id}"
        assert len(tc.ground_truth_answer.strip()) > 20, (
            f"Answer missing or too short in {tc.eval_id}"
        )
        assert len(tc.acceptable_source_patterns) >= 1, f"Patterns missing in {tc.eval_id}"
        assert isinstance(tc.expected_slots, dict), f"expected_slots must be a dict in {tc.eval_id}"


# ==============================================================================
# 2. Relevance Judgment & Pattern Matching Tests
# ==============================================================================


def test_is_chunk_relevant_by_source_pattern() -> None:
    chunk = _make_dummy_chunk(
        chunk_id="c1",
        text="Random unrelated text content.",
        source_url="https://www.cukashmir.ac.in/admission/refund_rules.pdf",
    )
    # Glob pattern match against source_url
    assert is_chunk_relevant(
        chunk=chunk,
        acceptable_patterns=["*refund*", "*fee*"],
        expected_keywords=["something", "else"],
    )


def test_is_chunk_relevant_by_title_pattern() -> None:
    chunk = _make_dummy_chunk(
        chunk_id="c1",
        text="General notification content.",
        title="Notice Regarding Admission Cancellation and Fee Refund",
        source_url="https://www.cukashmir.ac.in/notice_123.pdf",
    )
    assert is_chunk_relevant(
        chunk=chunk,
        acceptable_patterns=["*admission*", "*refund*"],
        expected_keywords=["xyz"],
    )


def test_is_chunk_relevant_by_keywords() -> None:
    chunk = _make_dummy_chunk(
        chunk_id="c1",
        text="The fee refund policy stipulates full reimbursement minus administrative deduction before admission closure.",
        title="General Circular",
        source_url="https://www.cukashmir.ac.in/gen.pdf",
    )
    # Content has 'refund', 'cancellation', 'deduction', 'fee'
    assert is_chunk_relevant(
        chunk=chunk,
        acceptable_patterns=["*specific_pattern_not_matching*"],
        expected_keywords=["refund", "deduction", "fee"],
    )


def test_is_chunk_relevant_irrelevant() -> None:
    chunk = _make_dummy_chunk(
        chunk_id="c1",
        text="Tender notification for supply of laboratory equipment for physics lab.",
        title="Procurement Tender Notice",
        source_url="https://www.cukashmir.ac.in/tenders/tender1.pdf",
        page_url="https://www.cukashmir.ac.in/tenders",
        doc_type="tender",
    )
    assert not is_chunk_relevant(
        chunk=chunk,
        acceptable_patterns=["*admission*", "*hostel*"],
        expected_keywords=["refund", "cancellation", "hostel"],
    )


# ==============================================================================
# 3. Slot Accuracy Evaluation Tests
# ==============================================================================


def test_evaluate_slots_accuracy() -> None:
    evaluator = RAGEvaluator(
        retrieval_coordinator=MockRetrievalCoordinator(),
        telemetry_sink=InMemoryTelemetrySink(),
    )

    query = "What is the syllabus for B.Tech CSE Semester 3?"
    expected = {
        "intent": "syllabus",
        "program": "B.Tech CSE",
        "semester": "Semester 3",
        "department": None,
    }

    accuracy, extracted = evaluator.evaluate_slots(query=query, expected_slots=expected)
    assert accuracy == 1.0
    assert extracted.get("intent") == "syllabus"
    assert extracted.get("program") == "B.Tech CSE"
    assert "3" in str(extracted.get("semester"))


def test_evaluate_slots_partial_accuracy() -> None:
    evaluator = RAGEvaluator(
        retrieval_coordinator=MockRetrievalCoordinator(),
        telemetry_sink=InMemoryTelemetrySink(),
    )

    query = "Tell me the admission rules."
    # Query has intent admission, but no program
    expected = {
        "intent": "admission",
        "program": "B.Tech CSE",  # Absent in query
    }

    accuracy, extracted = evaluator.evaluate_slots(query=query, expected_slots=expected)
    assert accuracy == 0.5  # 1 out of 2 matched
    assert extracted.get("intent") == "admission"


# ==============================================================================
# 4. Citation Precision and Recall Tests
# ==============================================================================


def test_compute_citation_metrics_grounded() -> None:
    evaluator = RAGEvaluator(
        retrieval_coordinator=MockRetrievalCoordinator(),
        telemetry_sink=InMemoryTelemetrySink(),
    )

    context = "Students must secure at least 40% marks in Continuous Internal Assessment and 40% in End Semester Examination."
    quoted = [
        "secure at least 40% marks in Continuous Internal Assessment",
        "40% in End Semester Examination",
    ]
    keywords = ["internal assessment", "end semester", "passing marks", "40%"]

    precision, recall = evaluator.compute_citation_metrics(
        quoted_snippets=quoted,
        retrieved_contexts=[context],
        expected_keywords=keywords,
    )

    assert precision == 1.0  # All quotes are verbatim
    assert recall >= 0.5  # Key terms covered in quotes


def test_compute_citation_metrics_hallucinated() -> None:
    evaluator = RAGEvaluator(
        retrieval_coordinator=MockRetrievalCoordinator(),
        telemetry_sink=InMemoryTelemetrySink(),
    )

    context = "Students must secure at least 40% marks."
    quoted = [
        "Students must secure 95% marks to pass any examination without exception",
    ]

    precision, recall = evaluator.compute_citation_metrics(
        quoted_snippets=quoted,
        retrieved_contexts=[context],
        expected_keywords=["passing marks"],
    )

    assert precision == 0.0  # Ungrounded quote


# ==============================================================================
# 5. RAGEvaluator Single Test Case & Diagnostics
# ==============================================================================


def test_evaluate_test_case_hit_rank_1() -> None:
    chunk1 = _make_dummy_chunk(
        chunk_id="c1",
        text="The fee refund policy allows refund upon cancellation minus processing fee.",
        source_url="https://www.cukashmir.ac.in/admission/fee_refund.pdf",
    )
    sink = InMemoryTelemetrySink()
    coordinator = MockRetrievalCoordinator(candidates=[chunk1])
    evaluator = RAGEvaluator(retrieval_coordinator=coordinator, telemetry_sink=sink)

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the fee refund policy after admission cancellation?",
        expected_slots={"intent": "admission", "department": None},
        expected_keywords=["fee", "refund", "cancellation"],
        ground_truth_answer="Full refund minus processing charge.",
        acceptable_source_patterns=["*admission*", "*refund*"],
    )

    result = evaluator.evaluate_test_case(test_case=test_case, top_k=5)

    assert result.hit_at_k is True
    assert result.reciprocal_rank == 1.0
    assert result.first_relevant_rank == 1
    assert result.keyword_recall == 1.0
    assert result.diagnostic_code is None
    # No failure emitted to sink
    assert len(sink._failures) == 0
    # Span logged
    assert len(sink._spans) == 1
    assert sink._spans[0].attributes["eval_id"] == "eval_001"


def test_evaluate_test_case_hit_rank_3() -> None:
    irrelevant1 = _make_dummy_chunk("c1", "Tender for laboratory glass beakers.")
    irrelevant2 = _make_dummy_chunk("c2", "University sports day football tournament fixtures.")
    relevant = _make_dummy_chunk(
        "c3",
        "Fee refund policy upon cancellation allows refund.",
        source_url="https://www.cukashmir.ac.in/admission/refund.pdf",
    )

    sink = InMemoryTelemetrySink()
    coordinator = MockRetrievalCoordinator(candidates=[irrelevant1, irrelevant2, relevant])
    evaluator = RAGEvaluator(retrieval_coordinator=coordinator, telemetry_sink=sink)

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the fee refund policy?",
        expected_slots={"intent": "admission"},
        expected_keywords=["refund", "fee"],
        ground_truth_answer="Refund is available.",
        acceptable_source_patterns=["*refund*"],
    )

    result = evaluator.evaluate_test_case(test_case=test_case, top_k=5)

    assert result.hit_at_k is True
    assert result.first_relevant_rank == 3
    assert pytest.approx(result.reciprocal_rank, 0.01) == 1.0 / 3.0
    assert result.diagnostic_code is None


def test_evaluate_test_case_retrieval_empty_diagnostic() -> None:
    sink = InMemoryTelemetrySink()
    coordinator = MockRetrievalCoordinator(candidates=[])  # Empty retrieval
    evaluator = RAGEvaluator(retrieval_coordinator=coordinator, telemetry_sink=sink)

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the fee refund policy?",
        expected_slots={},
        expected_keywords=["refund", "fee"],
        ground_truth_answer="...",
        acceptable_source_patterns=["*refund*"],
    )

    result = evaluator.evaluate_test_case(test_case=test_case, top_k=5)

    assert result.hit_at_k is False
    assert result.reciprocal_rank == 0.0
    assert result.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_EMPTY
    # Failure tagged on telemetry sink
    assert len(sink._failures) == 1
    assert sink._failures[0].diagnostic_code == FailureDiagnosticCode.RETRIEVAL_EMPTY
    assert sink._failures[0].trace_id == "eval-eval_001"


def test_evaluate_test_case_missed_top_ranked_diagnostic() -> None:
    # 5 irrelevant chunks in top 5, followed by relevant chunk at rank 6
    top_5_irrelevant = [
        _make_dummy_chunk(f"c{i}", f"Unrelated text number {i}") for i in range(1, 6)
    ]
    relevant_rank_6 = _make_dummy_chunk(
        "c6",
        "The fee refund policy allows reimbursement upon admission cancellation.",
        source_url="https://www.cukashmir.ac.in/admission/refund.pdf",
    )

    sink = InMemoryTelemetrySink()
    # Mock coordinator returns up to top_k requested
    # evaluator requests wide_k (max 30), so candidates list has 6 items
    candidates = top_5_irrelevant + [relevant_rank_6]

    class MockWideRetrievalCoordinator:
        def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[ScoredChunk]:
            return candidates[:top_k]

    evaluator = RAGEvaluator(
        retrieval_coordinator=MockWideRetrievalCoordinator(),  # type: ignore[arg-type]
        telemetry_sink=sink,
    )

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the fee refund policy?",
        expected_slots={},
        expected_keywords=["refund", "fee", "cancellation"],
        ground_truth_answer="...",
        acceptable_source_patterns=["*refund*"],
    )

    result = evaluator.evaluate_test_case(test_case=test_case, top_k=5)

    assert result.hit_at_k is False
    assert result.diagnostic_code == FailureDiagnosticCode.MISSED_TOP_RANKED
    assert result.diagnostic_details["found_at_rank"] == 6
    assert len(sink._failures) == 1
    assert sink._failures[0].diagnostic_code == FailureDiagnosticCode.MISSED_TOP_RANKED


def test_evaluate_test_case_retrieval_recall_miss_diagnostic() -> None:
    # 10 irrelevant chunks everywhere
    irrelevant_all = [
        _make_dummy_chunk(f"c{i}", f"Unrelated text number {i}") for i in range(1, 10)
    ]

    sink = InMemoryTelemetrySink()

    class MockAllIrrelevantCoordinator:
        def retrieve(self, query: str, top_k: int = 5, **kwargs: Any) -> list[ScoredChunk]:
            return irrelevant_all[:top_k]

    evaluator = RAGEvaluator(
        retrieval_coordinator=MockAllIrrelevantCoordinator(),  # type: ignore[arg-type]
        telemetry_sink=sink,
    )

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the fee refund policy?",
        expected_slots={},
        expected_keywords=["refund", "fee"],
        ground_truth_answer="...",
        acceptable_source_patterns=["*refund*"],
    )

    result = evaluator.evaluate_test_case(test_case=test_case, top_k=5)

    assert result.hit_at_k is False
    assert result.diagnostic_code == FailureDiagnosticCode.RETRIEVAL_RECALL_MISS
    assert len(sink._failures) == 1
    assert sink._failures[0].diagnostic_code == FailureDiagnosticCode.RETRIEVAL_RECALL_MISS


def test_evaluate_test_case_with_answer_citations() -> None:
    chunk = _make_dummy_chunk(
        "c1",
        "A nominal deduction of Rs 1000 is made for cancellation before closure.",
        source_url="https://www.cukashmir.ac.in/admission/refund.pdf",
    )
    sink = InMemoryTelemetrySink()
    coordinator = MockRetrievalCoordinator(candidates=[chunk])
    evaluator = RAGEvaluator(retrieval_coordinator=coordinator, telemetry_sink=sink)

    test_case = GoldenTestCase(
        eval_id="eval_001",
        query="What is the deduction for admission cancellation?",
        expected_slots={"intent": "admission"},
        expected_keywords=["deduction", "cancellation"],
        ground_truth_answer="A nominal deduction of Rs 1000 is made.",
        acceptable_source_patterns=["*refund*"],
    )

    answer = AnswerWithCitations(
        direct_answer="Rs 1000 is deducted.",
        quoted_snippets=["A nominal deduction of Rs 1000 is made for cancellation"],
        citation_chunk_ids=["c1"],
        confidence_score=0.95,
    )

    result = evaluator.evaluate_test_case(
        test_case=test_case, top_k=5, answer_with_citations=answer
    )

    assert result.hit_at_k is True
    assert result.citation_precision == 1.0
    assert result.citation_recall is not None
    assert result.citation_recall > 0.0


# ==============================================================================
# 6. evaluate_dataset Aggregation Tests
# ==============================================================================


def test_evaluate_dataset_summary() -> None:
    chunk1 = _make_dummy_chunk(
        "c1", "Fee refund notice", source_url="https://site.ac.in/refund.pdf"
    )
    coordinator = MockRetrievalCoordinator(candidates=[chunk1])
    evaluator = RAGEvaluator(
        retrieval_coordinator=coordinator, telemetry_sink=InMemoryTelemetrySink()
    )

    test_cases = [
        GoldenTestCase(
            eval_id="eval_001",
            query="Fee refund policy?",
            expected_slots={"intent": "admission"},
            expected_keywords=["refund"],
            acceptable_source_patterns=["*refund*"],
        ),
        GoldenTestCase(
            eval_id="eval_002",
            query="Hostel mess rules?",
            expected_slots={"intent": "general"},
            expected_keywords=["hostel", "mess"],
            acceptable_source_patterns=["*hostel*"],  # chunk1 is refund, so this will miss
        ),
    ]

    summary = evaluator.evaluate_dataset(test_cases, top_k=5)

    assert summary.total_cases == 2
    assert summary.hit_rate_at_k == 0.5  # 1 hit, 1 miss
    assert summary.mrr == 0.5  # 1.0 / 2
    assert len(summary.results) == 2
    assert FailureDiagnosticCode.RETRIEVAL_RECALL_MISS.value in summary.failure_attribution_counts


def test_evaluate_empty_dataset() -> None:
    evaluator = RAGEvaluator(
        retrieval_coordinator=MockRetrievalCoordinator(),
        telemetry_sink=InMemoryTelemetrySink(),
    )
    summary = evaluator.evaluate_dataset([], top_k=5)
    assert summary.total_cases == 0
    assert summary.hit_rate_at_k == 0.0
    assert summary.mrr == 0.0


# ==============================================================================
# 7. CLI Typer App Tests
# ==============================================================================


def test_cli_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Central University of Kashmir RAG Regression Benchmark Evaluator" in result.output


def test_cli_run_help() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--dataset" in result.output
    assert "--top-k" in result.output
    assert "--output" in result.output


def test_cli_run_missing_dataset() -> None:
    runner = CliRunner()
    result = runner.invoke(app, ["run", "--dataset", "non_existent_dataset.jsonl"])
    assert result.exit_code == 1
    assert "not found" in result.output.lower()
