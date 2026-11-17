"""Offline API record parser.

Formats raw API records (faculty, notices, tenders, results, circulars) into clean Markdown text
while enforcing PII privacy guards (scrubbing DOB and mobile numbers).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cuk_assistant.ingestion.normalize.sanitizer import scrub_pii
from cuk_assistant.ingestion.parsers.base import BaseParser, ParsedApiRecord
from cuk_assistant.ingestion.parsers.html_parser import parse_html

logger = logging.getLogger(__name__)


class OfflineApiParser(BaseParser):
    """Parses raw API JSON records into formatted text and metadata."""

    @staticmethod
    def _scrub_pii(text: str) -> str:
        """Strip mobile numbers, student roll numbers, and raw ISO DOBs from text."""
        return scrub_pii(text)

    def parse_file(
        self, file_path: Path, raw_meta: dict | None = None, **kwargs: Any
    ) -> ParsedApiRecord:
        """Parse raw API JSON file."""
        meta = raw_meta or {}
        if not file_path.exists():
            return ParsedApiRecord(text="", metadata=meta)

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read JSON %s: %s", file_path, exc)
            return ParsedApiRecord(text="", metadata=meta)

        records = (
            data.get("records")
            if isinstance(data, dict)
            else (data if isinstance(data, list) else None)
        )
        if isinstance(records, list) and records:
            formatted_parts = [self.format_record_text(r) for r in records if isinstance(r, dict)]
            extracted_text = "\n\n---\n\n".join(filter(None, formatted_parts))
            raw_record = data.get("raw_record") or meta
        else:
            raw_record = data.get("raw_record") or (data if isinstance(data, dict) else meta)
            extracted_text = self.format_record_text(raw_record)

        cleaned_text = self._scrub_pii(extracted_text)
        return ParsedApiRecord(text=cleaned_text, metadata=raw_record)

    def parse_records(self, file_path: Path, raw_meta: dict | None = None) -> list[ParsedApiRecord]:
        """Parse multi-record JSON file into individual ParsedApiRecord items."""
        meta = raw_meta or {}
        if not file_path.exists():
            return []

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read JSON %s: %s", file_path, exc)
            return []

        records = (
            data.get("records")
            if isinstance(data, dict)
            else (data if isinstance(data, list) else None)
        )
        if not isinstance(records, list) or not records:
            records = [data] if isinstance(data, dict) else []

        results: list[ParsedApiRecord] = []
        for rec in records:
            if not isinstance(rec, dict):
                continue
            text = self.format_record_text(rec)
            cleaned = self._scrub_pii(text)
            rec_meta = {**meta, **rec}
            results.append(ParsedApiRecord(text=cleaned, metadata=rec_meta))
        return results

    def format_record_text(self, record: dict) -> str:
        """Format an API dictionary record into clean markdown text."""
        if not record or not isinstance(record, dict):
            return ""

        parts: list[str] = []
        content_type = (record.get("content_type") or "").lower()

        # ── 1. Faculty Profiles ─────────────────────────────────────────────
        if content_type == "faculty" or "FirstName" in record or "Designation" in record:
            first = (record.get("FirstName") or "").strip()
            last = (record.get("LastName") or record.get("LasttName") or "").strip()
            name = (
                record.get("title")
                or record.get("Name")
                or (" ".join(filter(None, [first, last]))).strip()
            )
            if name:
                parts.append(f"# {name}")

            dept = (
                record.get("department_name")
                or record.get("DepartmentName")
                or record.get("Department")
            )
            if dept:
                parts.append(f"- **Department:** {dept}")

            school = record.get("school_name") or record.get("SchoolName") or record.get("School")
            if school:
                parts.append(f"- **School:** {school}")

            desig = record.get("designation") or record.get("Designation")
            if desig:
                parts.append(f"- **Designation:** {desig}")

            email = record.get("email") or record.get("Email")
            if email:
                parts.append(f"- **Email:** {email}")

            edu = (
                record.get("qualifications")
                or record.get("Education")
                or record.get("Qualification")
            )
            if edu:
                parts.append(f"- **Qualifications:** {edu}")

            res = record.get("research_areas") or record.get("Specialization")
            if res:
                res_str = ", ".join(res) if isinstance(res, list) else str(res)
                parts.append(f"- **Research / Specialization:** {res_str}")

            office = record.get("office_address") or record.get("OfficeAddress")
            if office:
                parts.append(f"- **Office Address:** {office}")

            desc = record.get("description") or record.get("Details")
            if desc:
                parts.append("")
                if "<" in str(desc):
                    parts.append(parse_html(str(desc)).text)
                else:
                    parts.append(str(desc).strip())

        # ── 2. Tenders ───────────────────────────────────────────────────────
        elif "TenderNo" in record or "TenderTitle" in record or "tender" in content_type:
            title = record.get("TenderTitle") or record.get("title") or record.get("Title")
            if title:
                parts.append(f"# {title}")

            t_no = record.get("tender_number") or record.get("TenderNo")
            if t_no:
                parts.append(f"- **Tender No:** {t_no}")

            nit = record.get("nit_date") or record.get("StartDate") or record.get("NITDate")
            if nit:
                parts.append(f"- **NIT Date:** {nit}")

            closing = record.get("closing_date") or record.get("EndDate")
            if closing:
                parts.append(f"- **Closing Date:** {closing}")

            desc = (
                record.get("description")
                or record.get("Description")
                or record.get("Details")
                or record.get("Content")
            )
            if desc:
                parts.append("")
                if "<" in str(desc):
                    parts.append(parse_html(str(desc)).text)
                else:
                    parts.append(str(desc).strip())

        # ── 3. Notices, Circulars, Admissions, Employments ───────────────────
        else:
            title = (
                record.get("title")
                or record.get("Title")
                or record.get("NoticeTitle")
                or record.get("NotificationTitle")
                or record.get("NewsTitle")
                or record.get("PressReleaseTitle")
                or record.get("HeaderCategoryName")
                or record.get("DepartmentName")
                or record.get("AdministrativeName")
            )
            if title:
                parts.append(f"# {title}")

            notif = (
                record.get("notification_number")
                or record.get("NotificationNo")
                or record.get("NoticeNo")
                or record.get("OrderNo")
                or record.get("CircularNo")
            )
            if notif:
                parts.append(f"- **Notification / Ref No:** {notif}")

            dt = (
                record.get("dated")
                or record.get("Dated")
                or record.get("StartDate")
                or record.get("PublishDate")
                or record.get("CreatedOn")
            )
            if dt:
                parts.append(f"- **Date:** {dt}")

            closing = record.get("closing_date") or record.get("EndDate")
            if closing:
                parts.append(f"- **Closing Date:** {closing}")

            desc = (
                record.get("description")
                or record.get("Description")
                or record.get("Details")
                or record.get("Content")
                or record.get("LongDescription")
                or record.get("DepartmentDescription")
                or record.get("AdministrativeDescription")
            )
            if desc:
                parts.append("")
                if "<" in str(desc):
                    parts.append(parse_html(str(desc)).text)
                else:
                    parts.append(str(desc).strip())

        return "\n".join(parts).strip()


__all__ = [
    "OfflineApiParser",
    "ParsedApiRecord",
]
