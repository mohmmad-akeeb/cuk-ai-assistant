"""Verbatim citation and grounding verifier for CUK Assistant.

Ensures that every factual quotation or cited snippet in generated answers
is an exact verbatim substring of the retrieved context chunks (FR-6.3).
"""

from __future__ import annotations

import re
from typing import Any


def _normalize_text(text: str) -> str:
    """Normalize text by collapsing whitespace and lowercasing."""
    if not text:
        return ""
    # Collapse multiple whitespace characters (including newlines, tabs) into single space
    collapsed = re.sub(r"\s+", " ", text)
    return collapsed.strip().lower()


def verify_citations(
    quoted_snippets: list[str],
    retrieved_contexts: list[str],
    min_snippet_chars: int = 15,
) -> tuple[bool, list[str]]:
    """Verify that quoted snippets exist verbatim in retrieved contexts.

    Args:
        quoted_snippets: List of quoted text segments or citations from the generated answer.
        retrieved_contexts: List of context text strings retrieved from corpus.
        min_snippet_chars: Minimum character length of a snippet to be subject to
                           strict verbatim verification. Snippets shorter than this
                           threshold are skipped.

    Returns:
        tuple[bool, list[str]]: (is_grounded, offending_ungrounded_snippets)
    """
    if not quoted_snippets:
        return True, []

    normalized_contexts = [_normalize_text(ctx) for ctx in retrieved_contexts if ctx]
    ungrounded: list[str] = []

    for snippet in quoted_snippets:
        if not snippet:
            continue
        norm_snippet = _normalize_text(snippet)
        if len(norm_snippet) < min_snippet_chars:
            continue

        if not normalized_contexts:
            ungrounded.append(snippet)
            continue

        matched = any(norm_snippet in ctx for ctx in normalized_contexts)
        if not matched:
            ungrounded.append(snippet)

    return len(ungrounded) == 0, ungrounded


class VerbatimCitationVerifier:
    """Deterministic verbatim citation verifier component."""

    def __init__(self, min_snippet_chars: int = 15) -> None:
        self.min_snippet_chars = min_snippet_chars

    def verify(
        self,
        quoted_snippets: list[str] | Any,
        retrieved_contexts: list[str] | list[Any],
        min_snippet_chars: int | None = None,
    ) -> tuple[bool, list[str]]:
        """Verify quoted snippets against retrieved contexts.

        Supports both raw strings and AnswerWithCitations/Chunk objects.
        """
        # If quoted_snippets is an AnswerWithCitations model or object with quoted_snippets
        if hasattr(quoted_snippets, "quoted_snippets"):
            snippets = list(quoted_snippets.quoted_snippets)
        elif isinstance(quoted_snippets, list):
            snippets = quoted_snippets
        elif isinstance(quoted_snippets, str):
            snippets = [quoted_snippets]
        else:
            snippets = []

        # Extract text strings from retrieved contexts if they are objects
        contexts: list[str] = []
        for ctx in retrieved_contexts:
            if hasattr(ctx, "text"):
                contexts.append(str(ctx.text))
            elif isinstance(ctx, dict) and "text" in ctx:
                contexts.append(str(ctx["text"]))
            elif isinstance(ctx, str):
                contexts.append(ctx)
            else:
                contexts.append(str(ctx))

        threshold = self.min_snippet_chars if min_snippet_chars is None else min_snippet_chars
        return verify_citations(
            quoted_snippets=snippets,
            retrieved_contexts=contexts,
            min_snippet_chars=threshold,
        )
