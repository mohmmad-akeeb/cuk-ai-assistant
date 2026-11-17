"""cuk_assistant/ingestion/extract/pdf_fact_extractor.py

Tier 2 intrinsic document fact extractor.
Pulls reference numbers, circular IDs, notification dates, issuing authorities, and signatories
from document text and layout headers, and enriches document and chunk metadata.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from cuk_assistant.ingestion.normalize.metadata_normalizer import (
    extract_circular_reference,
    normalize_academic_year,
    normalize_iso_date,
)
from cuk_assistant.schemas.chunks import ChunkRecord

# ---------------------------------------------------------------------------
# Heuristic Patterns
# ---------------------------------------------------------------------------

_DATE_PREFIX_RE = re.compile(
    r"(?:Dated|Date|Notification\s+Date|Notification\s+Dated|Published\s+On)\s*[:\-–]?\s*([0-9A-Za-z\s,\.\/\-]+)",
    re.IGNORECASE,
)

_SUBJECT_RE = re.compile(
    r"(?:Subject|Sub)\s*[:\-–]\s*([^\n\r]+)",
    re.IGNORECASE,
)

_AUTHORITY_PATTERNS = [
    (
        re.compile(
            r"\b(Assistant\s+Registrar|Deputy\s+Registrar|In-?[Cc]harge\s+Registrar|Registrar)\b",
            re.IGNORECASE,
        ),
        "Registrar",
    ),
    (
        re.compile(r"\b(Controller\s+of\s+Examinations|COE)\b", re.IGNORECASE),
        "Controller of Examinations",
    ),
    (re.compile(r"\b(Dean\s+Academic\s+Affairs)\b", re.IGNORECASE), "Dean Academic Affairs"),
    (re.compile(r"\b(Dean\s+Students\s+Welfare|DSW)\b", re.IGNORECASE), "Dean Students Welfare"),
    (re.compile(r"\b(Dean[,\s]+School\s+of\s+[A-Za-z\s&]+)\b", re.IGNORECASE), "Dean"),
    (re.compile(r"\b(Vice-?Chancellor|VC)\b", re.IGNORECASE), "Vice-Chancellor"),
    (re.compile(r"\b(Finance\s+Officer)\b", re.IGNORECASE), "Finance Officer"),
    (re.compile(r"\b(Executive\s+Engineer)\b", re.IGNORECASE), "Executive Engineer"),
    (
        re.compile(
            r"\b(Head[,\s]+Department\s+of\s+[A-Za-z\s&]+|Head\s+of\s+the\s+Department|HOD|HoD)\b",
            re.IGNORECASE,
        ),
        "Head of Department",
    ),
]

_SIGNATORY_BLOCK_RE = re.compile(
    r"(?:Sd/[-–—]?|\(Sd/[-–—]?\)|\(Signed\)|By\s+Order)\s*\n+(?:(?:\(([^\)\n]+)\)|([A-Z][a-zA-Z\.\s]{2,40}))\n+)?\s*([A-Za-z\s,–—\-]{3,60})",
    re.IGNORECASE,
)


class PdfIntrinsicFacts(BaseModel):
    """Extracted intrinsic facts container."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reference_number: str | None = Field(
        default=None, description="Circular, F.No., or NIT reference"
    )
    notification_date: str | None = Field(
        default=None, description="Normalized ISO date (YYYY-MM-DD)"
    )
    issuing_authority: str | None = Field(
        default=None, description="Primary issuing body or officer"
    )
    signatories: list[str] = Field(
        default_factory=list, description="Extracted signatories and titles"
    )
    subject: str | None = Field(default=None, description="Extracted document subject")
    academic_year: str | None = Field(default=None, description="Academic year (e.g. 2023-2024)")
    raw_facts: dict[str, Any] = Field(
        default_factory=dict, description="Raw unnormalized extracted facts"
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert facts to dictionary, excluding None values."""
        res: dict[str, Any] = {}
        if self.reference_number:
            res["reference_number"] = self.reference_number
            res["circular_number"] = self.reference_number
        if self.notification_date:
            res["notification_date"] = self.notification_date
            res["published_date"] = self.notification_date
        if self.issuing_authority:
            res["issuing_authority"] = self.issuing_authority
        if self.signatories:
            res["signatories"] = list(self.signatories)
        if self.subject:
            res["subject"] = self.subject
        if self.academic_year:
            res["academic_year"] = self.academic_year
        if self.raw_facts:
            res["raw_facts"] = dict(self.raw_facts)
        return res


class PdfFactExtractor:
    """Extracts intrinsic metadata from PDF text and layout."""

    def extract_facts(self, text: str, title: str = "") -> PdfIntrinsicFacts:
        """Extract intrinsic facts from text content and optional title."""
        if not text and not title:
            return PdfIntrinsicFacts()

        header_text = text[:3000] if text else ""
        tail_text = text[-3000:] if len(text) > 3000 else text

        raw_facts: dict[str, Any] = {}

        # 1. Reference / Circular Number
        ref_no = extract_circular_reference(title) or extract_circular_reference(header_text)
        if not ref_no and text:
            ref_no = extract_circular_reference(text)
        if ref_no:
            raw_facts["reference_number"] = ref_no

        # 2. Notification Date
        notif_date: str | None = None
        date_match = _DATE_PREFIX_RE.search(header_text)
        if date_match:
            candidate = date_match.group(1).strip()
            # Clean trailing words/punctuation
            candidate = re.split(r"[\n\r;]", candidate)[0].strip()
            candidate = re.sub(
                r"^(dated|date|on)\s*[:\-–]?\s*", "", candidate, flags=re.IGNORECASE
            ).strip()
            notif_date = normalize_iso_date(candidate)
            if notif_date:
                raw_facts["date_raw"] = candidate

        # Fallback date search in header if date_prefix not matched
        if not notif_date:
            lines = [ln.strip() for ln in header_text.splitlines() if ln.strip()]
            for line in lines[:15]:
                if any(w in line.lower() for w in ("date", "dated", "202", "201")):
                    parsed = normalize_iso_date(line)
                    if parsed:
                        notif_date = parsed
                        raw_facts["date_raw"] = line
                        break

        # 3. Subject extraction
        subj: str | None = None
        subj_match = _SUBJECT_RE.search(header_text)
        if subj_match:
            subj = subj_match.group(1).strip()
            raw_facts["subject"] = subj

        # 4. Academic Year
        acad_year = normalize_academic_year(header_text) or normalize_academic_year(title)
        if acad_year:
            raw_facts["academic_year"] = acad_year

        # 5. Issuing Authority & Signatories
        signatories: list[str] = []
        issuing_authority: str | None = None

        # Look in tail text first for signatories
        for m in _SIGNATORY_BLOCK_RE.finditer(tail_text):
            name = m.group(1) or m.group(2)
            designation = m.group(3).strip() if m.group(3) else ""
            cleaned_desig = designation.strip(" -–—,.")
            entry = f"{name.strip()} ({cleaned_desig})" if name and name.strip() else cleaned_desig
            if entry and entry not in signatories and len(entry) < 80:
                signatories.append(entry)

        # Detect canonical authority designations across header and tail
        for pattern, canonical_name in _AUTHORITY_PATTERNS:
            if pattern.search(tail_text) or pattern.search(header_text):
                if not issuing_authority:
                    issuing_authority = canonical_name
                matched_str = pattern.search(tail_text) or pattern.search(header_text)
                if matched_str:
                    val = matched_str.group(0).strip()
                    if val not in signatories:
                        signatories.append(val)

        return PdfIntrinsicFacts(
            reference_number=ref_no,
            notification_date=notif_date,
            issuing_authority=issuing_authority,
            signatories=signatories,
            subject=subj,
            academic_year=acad_year,
            raw_facts=raw_facts,
        )

    def enrich_document_metadata(
        self, metadata: dict[str, Any], text: str, title: str = ""
    ) -> dict[str, Any]:
        """Enrich document metadata dictionary with extracted facts."""
        doc_title = title or str(metadata.get("title", ""))
        facts = self.extract_facts(text, title=doc_title)
        facts_dict = facts.to_dict()

        enriched = dict(metadata)
        for key, value in facts_dict.items():
            if key not in enriched or not enriched[key]:
                enriched[key] = value

        # Ensure reference_number & circular_number are synced
        ref = enriched.get("reference_number") or enriched.get("circular_number")
        if ref:
            enriched["reference_number"] = ref
            enriched["circular_number"] = ref

        return enriched

    def enrich_chunks(
        self, chunks: list[ChunkRecord], facts: PdfIntrinsicFacts
    ) -> list[ChunkRecord]:
        """Enrich existing ChunkRecord instances with extracted facts in chunk.metadata."""
        facts_dict = facts.to_dict()
        if not facts_dict:
            return chunks

        enriched_chunks: list[ChunkRecord] = []
        for chunk in chunks:
            chunk_meta = dict(chunk.metadata)
            for k, v in facts_dict.items():
                if k not in chunk_meta or not chunk_meta[k]:
                    chunk_meta[k] = v

            enriched_chunk = chunk.model_copy(update={"metadata": chunk_meta})
            enriched_chunks.append(enriched_chunk)

        return enriched_chunks


__all__ = [
    "PdfFactExtractor",
    "PdfIntrinsicFacts",
]
