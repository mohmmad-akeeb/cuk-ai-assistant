"""cuk_assistant/evals/query_miner.py

Dynamic starter menu hierarchy miner and conversational query synthesizer.
Analyzes extracted document and chunk metadata to cluster administrative topics
and synthesize clickable starter prompt chips for the UI.

Governed by docs/requirements.md (FR-9.1, FR-9.2), docs/api_contracts.md Section 2.5,
and Task 6.4.
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cuk_assistant.api.routes.menu import MenuCategory, MenuItem, StarterMenuResponse
from cuk_assistant.schemas.chunks import ChunkRecord
from cuk_assistant.schemas.document import Document

logger = logging.getLogger(__name__)


class MenuHierarchyMiner:
    """Mines document and chunk metadata to generate dynamic starter menu hierarchies."""

    DEFAULT_CATEGORIES: list[dict[str, Any]] = [
        {
            "id": "admissions",
            "title": "Admissions & Intake",
            "icon": "graduation-cap",
            "prompts": [
                "What is the admission procedure for PG programmes via CUET?",
                "What are the hostel fee details for first-semester students?",
                "What is the approved seat intake matrix for B.Tech, MBA, and PG courses?",
                "Where can I find the admission prospectus and eligibility criteria?",
                "What are the latest CUET UG admission cut-offs and selection lists?",
            ],
            "items": [
                {
                    "id": "admissions_cuet_pg",
                    "title": "PG Programmes via CUET",
                    "default_query": "What is the admission procedure for PG programmes via CUET?",
                    "suggested_slots": {"doc_type": "admission", "stage": "counselling"},
                },
                {
                    "id": "admissions_hostel_fee",
                    "title": "Hostel Fee Details",
                    "default_query": "What are the hostel fee details for first-semester students?",
                    "suggested_slots": {"category": "hostel", "doc_type": "fee_structure"},
                },
                {
                    "id": "admissions_seat_matrix",
                    "title": "Seat Intake Matrix",
                    "default_query": "What is the approved seat intake matrix for B.Tech, MBA, and PG courses?",
                    "suggested_slots": {"doc_type": "admission", "stage": "seat_matrix"},
                },
                {
                    "id": "admissions_prospectus",
                    "title": "Prospectus & Eligibility",
                    "default_query": "Where can I find the admission prospectus and eligibility criteria?",
                    "suggested_slots": {"doc_type": "admission", "stage": "general"},
                },
                {
                    "id": "admissions_cuet_cutoffs",
                    "title": "CUET UG Cut-Offs",
                    "default_query": "What are the latest CUET UG admission cut-offs and selection lists?",
                    "suggested_slots": {"doc_type": "admission", "stage": "cut_off"},
                },
            ],
        },
        {
            "id": "examinations",
            "title": "Examinations & Results",
            "icon": "file-text",
            "prompts": [
                "Show me the latest exam date sheets and notifications.",
                "How can I check semester results and re-evaluation notices?",
                "What is the procedure to apply for re-evaluation or answer script scrutiny?",
                "When and where can students download examination admit cards?",
            ],
            "items": [
                {
                    "id": "exam_datesheets",
                    "title": "Date Sheets & Notifications",
                    "default_query": "Show me the latest exam date sheets and notifications.",
                    "suggested_slots": {"doc_type": "notice", "subject_tags": ["Exam"]},
                },
                {
                    "id": "exam_results",
                    "title": "Semester Examination Results",
                    "default_query": "How can I check semester results and re-evaluation notices?",
                    "suggested_slots": {"doc_type": "result"},
                },
                {
                    "id": "exam_reevaluation",
                    "title": "Re-Evaluation Procedure",
                    "default_query": "What is the procedure to apply for re-evaluation or answer script scrutiny?",
                    "suggested_slots": {"doc_type": "result", "result_type": "re_evaluation"},
                },
                {
                    "id": "exam_admit_cards",
                    "title": "Admit Card Downloads",
                    "default_query": "When and where can students download examination admit cards?",
                    "suggested_slots": {"doc_type": "notice", "subject_tags": ["Admit Card"]},
                },
            ],
        },
        {
            "id": "academics",
            "title": "Academics & Syllabi",
            "icon": "book-open",
            "prompts": [
                "What is the detailed syllabus for B.Tech Computer Science & Engineering?",
                "Where can I find course lists and curriculum details by department?",
                "What are the passing criteria and attendance rules under CUK ordinances?",
                "What programmes and course structures are offered under CBCS?",
            ],
            "items": [
                {
                    "id": "academic_btech_syllabus",
                    "title": "B.Tech CSE Syllabus",
                    "default_query": "What is the detailed syllabus for B.Tech Computer Science & Engineering?",
                    "suggested_slots": {"doc_type": "syllabus", "program": "B.Tech CSE"},
                },
                {
                    "id": "academic_dept_courses",
                    "title": "Department Course Lists",
                    "default_query": "Where can I find course lists and curriculum details by department?",
                    "suggested_slots": {"doc_type": "syllabus"},
                },
                {
                    "id": "academic_ordinances",
                    "title": "Academic Ordinances & Rules",
                    "default_query": "What are the passing criteria and attendance rules under CUK ordinances?",
                    "suggested_slots": {"doc_type": "ordinance"},
                },
                {
                    "id": "academic_cbcs_structure",
                    "title": "CBCS Course Structure",
                    "default_query": "What programmes and course structures are offered under CBCS?",
                    "suggested_slots": {"doc_type": "ordinance"},
                },
            ],
        },
        {
            "id": "campus",
            "title": "Campus & Student Services",
            "icon": "building",
            "prompts": [
                "What are the hostel fee details and accommodation facilities for students?",
                "What are the transport and bus route facilities for Central University of Kashmir?",
                "How do I access Central Library facilities and digital catalog resources?",
                "What scholarships and financial assistance schemes are available for students?",
            ],
            "items": [
                {
                    "id": "campus_hostel_facilities",
                    "title": "Hostel Facilities & Fees",
                    "default_query": "What are the hostel fee details and accommodation facilities for students?",
                    "suggested_slots": {"doc_type": "general", "category": "hostel"},
                },
                {
                    "id": "campus_transport_routes",
                    "title": "Transport & Bus Routes",
                    "default_query": "What are the transport and bus route facilities for Central University of Kashmir?",
                    "suggested_slots": {"doc_type": "general", "category": "transport"},
                },
                {
                    "id": "campus_library_access",
                    "title": "Central Library Access",
                    "default_query": "How do I access Central Library facilities and digital catalog resources?",
                    "suggested_slots": {"doc_type": "general", "category": "library"},
                },
                {
                    "id": "campus_scholarships",
                    "title": "Scholarships & Financial Aid",
                    "default_query": "What scholarships and financial assistance schemes are available for students?",
                    "suggested_slots": {"doc_type": "notice", "subject_tags": ["Scholarship"]},
                },
            ],
        },
    ]

    def __init__(self, initial_categories: list[dict[str, Any]] | None = None) -> None:
        self.categories_config = initial_categories or self.DEFAULT_CATEGORIES
        self._doc_titles: list[str] = []
        self._schools: Counter[str] = Counter()
        self._departments: Counter[str] = Counter()
        self._circular_types: Counter[str] = Counter()
        self._heading_tags: list[str] = []
        self._programs: Counter[str] = Counter()
        self._custom_topics: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_document(self, doc: Document | dict[str, Any]) -> None:
        """Ingest document metadata for clustering."""
        if isinstance(doc, Document):
            title = doc.metadata.get("title") or ""
            metadata = doc.metadata
        elif isinstance(doc, dict):
            metadata = doc.get("metadata", doc)
            title = metadata.get("title", doc.get("title", ""))
        else:
            return

        if title:
            self._doc_titles.append(str(title).strip())

        school = metadata.get("school")
        if school and isinstance(school, str) and school.strip():
            self._schools[school.strip()] += 1

        dept = metadata.get("department")
        if dept and isinstance(dept, str) and dept.strip():
            self._departments[dept.strip()] += 1

        circ_type = metadata.get("circular_type") or metadata.get("doc_type")
        if circ_type and isinstance(circ_type, str) and circ_type.strip():
            self._circular_types[circ_type.strip().lower()] += 1

        prog = metadata.get("program")
        if prog and isinstance(prog, str) and prog.strip():
            self._programs[prog.strip()] += 1

        self._analyze_text_for_topics(title, metadata)

    def add_documents(self, docs: Iterable[Document | dict[str, Any]]) -> None:
        """Ingest multiple documents."""
        for doc in docs:
            self.add_document(doc)

    def add_chunk(self, chunk: ChunkRecord | dict[str, Any]) -> None:
        """Ingest chunk metadata and AST heading tags for topic clustering."""
        if isinstance(chunk, ChunkRecord):
            section_heading = chunk.section_heading or ""
            heading_path = chunk.heading_path or []
            metadata = chunk.metadata or {}
            text_content = chunk.text_content
        elif isinstance(chunk, dict):
            section_heading = chunk.get("section_heading", "")
            heading_path = chunk.get("heading_path", [])
            metadata = chunk.get("metadata", {})
            text_content = chunk.get("text_content", chunk.get("text", ""))
        else:
            return

        for h in heading_path:
            if h and isinstance(h, str) and h.strip():
                self._heading_tags.append(h.strip())
                self._analyze_text_for_topics(h, metadata)

        if section_heading and isinstance(section_heading, str) and section_heading.strip():
            self._heading_tags.append(section_heading.strip())
            self._analyze_text_for_topics(section_heading, metadata)

        # Track department/school from chunk metadata if available
        if metadata.get("department"):
            self._departments[str(metadata["department"]).strip()] += 1
        if metadata.get("school"):
            self._schools[str(metadata["school"]).strip()] += 1

        # Also inspect leading text content if heading was empty
        if not heading_path and text_content:
            first_line = text_content.strip().split("\n")[0][:100]
            self._analyze_text_for_topics(first_line, metadata)

    def add_chunks(self, chunks: Iterable[ChunkRecord | dict[str, Any]]) -> None:
        """Ingest multiple chunks."""
        for chunk in chunks:
            self.add_chunk(chunk)

    def load_from_files(
        self,
        documents_path: Path | str | None = None,
        chunks_path: Path | str | None = None,
    ) -> None:
        """Safely load documents or chunks from JSONL files if they exist."""
        if documents_path:
            p = Path(documents_path)
            if p.is_file():
                try:
                    with p.open(encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    self.add_document(json.loads(line))
                                except Exception:
                                    continue
                except Exception as exc:
                    logger.warning("Error reading documents from %s: %s", p, exc)

        if chunks_path:
            p = Path(chunks_path)
            if p.is_file():
                try:
                    with p.open(encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line:
                                try:
                                    self.add_chunk(json.loads(line))
                                except Exception:
                                    continue
                except Exception as exc:
                    logger.warning("Error reading chunks from %s: %s", p, exc)

    def _analyze_text_for_topics(self, text: str, metadata: dict[str, Any]) -> None:
        """Match text and metadata against topic clusters."""
        text_lower = text.lower()
        dept = metadata.get("department", "")
        prog = metadata.get("program", "")

        # 1. Admissions Cluster
        if any(k in text_lower for k in ("cuet", "entrance", "samarth")):
            self._custom_topics["admissions"].append(
                {
                    "subtopic": "cuet",
                    "label": "CUET Procedure",
                    "query": f"What is the admission procedure for {prog or 'PG programmes'} via CUET?",
                    "slots": {"doc_type": "admission", "stage": "counselling"},
                }
            )
        elif any(k in text_lower for k in ("seat intake", "intake capacity", "seat matrix")):
            self._custom_topics["admissions"].append(
                {
                    "subtopic": "seat_intake",
                    "label": "Approved Seat Intake",
                    "query": f"What is the approved seat intake matrix for {prog or 'B.Tech and PG courses'}?",
                    "slots": {"doc_type": "admission", "stage": "seat_matrix"},
                }
            )
        elif any(k in text_lower for k in ("cut-off", "cutoff", "merit list", "selection list")):
            self._custom_topics["admissions"].append(
                {
                    "subtopic": "cutoffs",
                    "label": "Cut-Offs & Merit Lists",
                    "query": f"What are the latest admission cut-offs and selection lists for {prog or 'CUK'}?",
                    "slots": {"doc_type": "admission", "stage": "cut_off"},
                }
            )
        elif any(
            k in text_lower for k in ("prospectus", "eligibility criteria", "admission notice")
        ):
            self._custom_topics["admissions"].append(
                {
                    "subtopic": "prospectus",
                    "label": "Prospectus & Eligibility",
                    "query": "Where can I find the admission prospectus and eligibility criteria?",
                    "slots": {"doc_type": "admission", "stage": "general"},
                }
            )

        # 2. Examinations Cluster
        if any(k in text_lower for k in ("date sheet", "datesheet", "time table", "exam schedule")):
            self._custom_topics["examinations"].append(
                {
                    "subtopic": "datesheets",
                    "label": "Date Sheets & Schedule",
                    "query": f"Show me the latest exam date sheets and notifications for {prog or 'end-semester exams'}.",
                    "slots": {"doc_type": "notice", "subject_tags": ["Exam"]},
                }
            )
        elif any(
            k in text_lower for k in ("re-evaluation", "reevaluation", "scrutiny", "answer script")
        ):
            self._custom_topics["examinations"].append(
                {
                    "subtopic": "reevaluation",
                    "label": "Re-Evaluation Procedure",
                    "query": "What is the procedure and deadline to apply for re-evaluation or answer script scrutiny?",
                    "slots": {"doc_type": "result", "result_type": "re_evaluation"},
                }
            )
        elif any(k in text_lower for k in ("admit card", "hall ticket")):
            self._custom_topics["examinations"].append(
                {
                    "subtopic": "admit_cards",
                    "label": "Admit Cards Download",
                    "query": "When and where can students download examination admit cards?",
                    "slots": {"doc_type": "notice", "subject_tags": ["Admit Card"]},
                }
            )
        elif any(k in text_lower for k in ("result", "marksheet", "grade card", "gazette")):
            self._custom_topics["examinations"].append(
                {
                    "subtopic": "results",
                    "label": "Semester Results",
                    "query": f"How can I check semester results and re-evaluation notices for {prog or 'CUK'}?",
                    "slots": {"doc_type": "result"},
                }
            )

        # 3. Academics Cluster
        if any(
            k in text_lower
            for k in ("syllabus", "syllabi", "curriculum", "course structure", "credits")
        ):
            dept_name = dept or "B.Tech Computer Science & Engineering"
            self._custom_topics["academics"].append(
                {
                    "subtopic": "syllabus",
                    "label": f"Syllabus for {dept_name}",
                    "query": f"What is the detailed syllabus and course structure for {dept_name}?",
                    "slots": {"doc_type": "syllabus", "department": dept_name},
                }
            )
        elif any(
            k in text_lower for k in ("ordinance", "cbcs", "academic regulation", "attendance rule")
        ):
            self._custom_topics["academics"].append(
                {
                    "subtopic": "ordinances",
                    "label": "CBCS & Academic Ordinances",
                    "query": "What are the passing criteria and attendance rules under CUK ordinances?",
                    "slots": {"doc_type": "ordinance"},
                }
            )

        # 4. Campus Cluster
        if any(k in text_lower for k in ("hostel", "mess", "allotment")):
            self._custom_topics["campus"].append(
                {
                    "subtopic": "hostel",
                    "label": "Hostel Facilities & Fees",
                    "query": "What are the hostel fee details and accommodation facilities for students?",
                    "slots": {"doc_type": "general", "category": "hostel"},
                }
            )
        elif any(k in text_lower for k in ("transport", "bus route", "bus timing")):
            self._custom_topics["campus"].append(
                {
                    "subtopic": "transport",
                    "label": "Transport & Bus Routes",
                    "query": "What are the transport and bus route facilities for Central University of Kashmir?",
                    "slots": {"doc_type": "general", "category": "transport"},
                }
            )
        elif any(k in text_lower for k in ("library", "opac", "inflibnet")):
            self._custom_topics["campus"].append(
                {
                    "subtopic": "library",
                    "label": "Central Library Services",
                    "query": "How do I access Central Library facilities and digital catalog resources?",
                    "slots": {"doc_type": "general", "category": "library"},
                }
            )
        elif any(k in text_lower for k in ("scholarship", "fellowship", "financial aid", "nsp")):
            self._custom_topics["campus"].append(
                {
                    "subtopic": "scholarships",
                    "label": "Scholarships & Financial Aid",
                    "query": "What scholarships and financial assistance schemes are available for students?",
                    "slots": {"doc_type": "notice", "subject_tags": ["Scholarship"]},
                }
            )

    def synthesize_category_prompts(
        self,
        category_id: str,
        default_prompts: list[str],
        default_items: list[dict[str, Any]],
    ) -> tuple[list[str], list[MenuItem]]:
        """Synthesize conversational prompt chips and MenuItem objects for a category."""
        prompts: list[str] = []
        items: list[MenuItem] = []
        seen_prompts: set[str] = set()

        def _add_item(prompt_str: str, title_str: str, slots_dict: dict[str, Any]) -> None:
            norm = prompt_str.strip().lower()
            if norm in seen_prompts:
                return
            seen_prompts.add(norm)
            prompts.append(prompt_str.strip())
            slug = re.sub(r"[^a-zA-Z0-9]+", "_", title_str.lower()).strip("_")
            items.append(
                MenuItem(
                    id=f"{category_id}_{slug[:24]}",
                    title=title_str.strip(),
                    default_query=prompt_str.strip(),
                    suggested_slots=slots_dict,
                )
            )

        # Dynamic topics mined from metadata
        mined = self._custom_topics.get(category_id, [])
        for m in mined:
            _add_item(m["query"], m["label"], m["slots"])

        # Dynamically inject high-frequency departments into Academics
        if category_id == "academics" and self._departments:
            for dept_name, _count in self._departments.most_common(3):
                _add_item(
                    f"What is the detailed syllabus for {dept_name}?",
                    f"Syllabus: {dept_name[:20]}",
                    {"doc_type": "syllabus", "department": dept_name},
                )

        # Merge with default items/prompts to guarantee rich baseline coverage
        for item in default_items:
            _add_item(
                item["default_query"],
                item["title"],
                item.get("suggested_slots", {}),
            )

        for p in default_prompts:
            clean_title = p.rstrip("?").strip()
            if len(clean_title) > 35:
                clean_title = clean_title[:32] + "..."
            _add_item(p, clean_title, {"category": category_id})

        return prompts, items

    def mine(self) -> StarterMenuResponse:
        """Produce final StarterMenuResponse containing mined categories and prompts."""
        categories: list[MenuCategory] = []

        for cat_def in self.categories_config:
            cat_id = cat_def["id"]
            title = cat_def["title"]
            icon = cat_def["icon"]
            default_prompts = cat_def.get("prompts", [])
            default_items = cat_def.get("items", [])

            prompts, items = self.synthesize_category_prompts(
                cat_id, default_prompts, default_items
            )

            category = MenuCategory(
                id=cat_id,
                title=title,
                icon=icon,
                prompts=prompts,
                items=items,
            )
            categories.append(category)

        return StarterMenuResponse(version="1.0", categories=categories)

    def to_dict(self) -> dict[str, Any]:
        """Produce dictionary payload suitable for JSON export."""
        return self.mine().model_dump()

    def export_json(self, output_path: Path | str = Path("data/menu_hierarchy.json")) -> Path:
        """Serialize mined menu hierarchy to disk."""
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = self.to_dict()
        with target.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return target
