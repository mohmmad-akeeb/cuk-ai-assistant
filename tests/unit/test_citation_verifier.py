"""Unit tests for VerbatimCitationVerifier (Task 4.5)."""

from cuk_assistant.guardrails.subsystems.citation_verifier import (
    VerbatimCitationVerifier,
    verify_citations,
)


class TestVerbatimCitationVerifier:
    """Test deterministic exact substring citation verification."""

    def setup_method(self) -> None:
        self.verifier = VerbatimCitationVerifier(min_snippet_chars=15)
        self.context = [
            (
                "The Central University of Kashmir announces the commencement of admission "
                "for postgraduate programmes for the academic session 2026. The last date "
                "for submission of online application forms is July 31, 2026."
            ),
            (
                "Candidates applying for MBA must have secured at least 50 percent marks in "
                "graduation or equivalent CGPA from a recognized university. Valid CUET-PG "
                "score is mandatory for shortlisting."
            ),
            (
                "Hostel accommodation is provided at Tulmulla campus subject to availability. "
                "Bus transport facility operates on designated routes connecting Srinagar and Ganderbal."
            ),
        ]

    def test_verbatim_exact_match_passes(self) -> None:
        quotes = [
            "The last date for submission of online application forms is July 31, 2026.",
            "Valid CUET-PG score is mandatory for shortlisting.",
        ]
        is_grounded, ungrounded = self.verifier.verify(quotes, self.context)
        assert is_grounded is True
        assert ungrounded == []

    def test_whitespace_and_case_insensitivity(self) -> None:
        quotes = [
            "  the LAST date for   submission of online application forms is july 31, 2026. \n",
            "HOSTEL ACCOMMODATION IS PROVIDED AT TULMULLA CAMPUS SUBJECT TO AVAILABILITY.",
        ]
        is_grounded, ungrounded = self.verifier.verify(quotes, self.context)
        assert is_grounded is True
        assert ungrounded == []

    def test_slightly_hallucinated_quote_fails(self) -> None:
        # Changed "July 31, 2026" to "August 15, 2026" (one word/date altered)
        hallucinated_quote = (
            "The last date for submission of online application forms is August 15, 2026."
        )
        is_grounded, ungrounded = self.verifier.verify(
            [hallucinated_quote],
            self.context,
        )
        assert is_grounded is False
        assert ungrounded == [hallucinated_quote]

    def test_single_word_addition_fails(self) -> None:
        # Added extra word "strictly" which is not in context
        hallucinated_quote = "Valid CUET-PG score is strictly mandatory for shortlisting."
        is_grounded, ungrounded = self.verifier.verify(
            [hallucinated_quote],
            self.context,
        )
        assert is_grounded is False
        assert ungrounded == [hallucinated_quote]

    def test_partially_valid_and_partially_hallucinated(self) -> None:
        valid_quote = "Valid CUET-PG score is mandatory for shortlisting."
        invalid_quote = "All students will receive free laptop and monthly stipend of 5000."
        is_grounded, ungrounded = self.verifier.verify(
            [valid_quote, invalid_quote],
            self.context,
        )
        assert is_grounded is False
        assert ungrounded == [invalid_quote]

    def test_empty_quotes_passes(self) -> None:
        is_grounded, ungrounded = self.verifier.verify([], self.context)
        assert is_grounded is True
        assert ungrounded == []

    def test_empty_contexts_with_quotes_fails(self) -> None:
        quote = "The last date for submission of online application forms is July 31, 2026."
        is_grounded, ungrounded = self.verifier.verify([quote], [])
        assert is_grounded is False
        assert ungrounded == [quote]

    def test_min_snippet_chars_filters_short_phrases(self) -> None:
        # Snippets shorter than 15 chars should be skipped by default
        short_hallucinated = "Random note"
        is_grounded, ungrounded = verify_citations(
            [short_hallucinated],
            self.context,
            min_snippet_chars=15,
        )
        assert is_grounded is True
        assert ungrounded == []

        # If min_snippet_chars is reduced to 5, it should be verified and caught
        is_grounded_strict, ungrounded_strict = verify_citations(
            [short_hallucinated],
            self.context,
            min_snippet_chars=5,
        )
        assert is_grounded_strict is False
        assert ungrounded_strict == [short_hallucinated]
