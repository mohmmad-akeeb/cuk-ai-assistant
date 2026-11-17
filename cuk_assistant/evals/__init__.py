"""cuk_assistant/evals/__init__.py

Regression evaluation benchmark suite and CLI evaluator pipeline.
"""

from cuk_assistant.evals.evaluator import RAGEvaluator, is_chunk_relevant
from cuk_assistant.evals.query_miner import MenuHierarchyMiner
from cuk_assistant.evals.schemas import (
    EvaluationSummary,
    GoldenTestCase,
    TestCaseEvalResult,
)

__all__ = [
    "EvaluationSummary",
    "GoldenTestCase",
    "MenuHierarchyMiner",
    "RAGEvaluator",
    "TestCaseEvalResult",
    "is_chunk_relevant",
]
