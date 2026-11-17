"""Guided starter menu endpoint.

Governed by docs/api_contracts.md Section 2.5 and FR-7.4.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

router = APIRouter(prefix="/api/v1/menu", tags=["Menu"])


class MenuItem(BaseModel):
    """Leaf node in guided starter menu."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    default_query: str
    suggested_slots: dict[str, Any] = Field(default_factory=dict)


class MenuCategory(BaseModel):
    """Top-level category grouping menu items."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str
    icon: str
    prompts: list[str] = Field(default_factory=list)
    items: list[MenuItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def _sync_prompts_and_items(self) -> MenuCategory:
        if self.prompts and not self.items:
            generated_items: list[MenuItem] = []
            for i, p in enumerate(self.prompts):
                clean_title = p.rstrip("?").strip()
                if len(clean_title) > 40:
                    clean_title = clean_title[:37] + "..."
                generated_items.append(
                    MenuItem(
                        id=f"{self.id}_{i + 1}",
                        title=clean_title,
                        default_query=p,
                        suggested_slots={"category": self.id},
                    )
                )
            self.items = generated_items
        elif self.items and not self.prompts:
            self.prompts = [item.default_query for item in self.items]
        return self


class StarterMenuResponse(BaseModel):
    """Hierarchical guided starter menu payload."""

    model_config = ConfigDict(extra="ignore")

    version: str = "1.0"
    categories: list[MenuCategory]


_DEFAULT_MENU: dict[str, Any] = {
    "version": "1.0",
    "categories": [
        {
            "id": "admissions",
            "title": "Admissions & Cut-Offs",
            "icon": "graduation-cap",
            "items": [
                {
                    "id": "cuet_ug_cutoffs",
                    "title": "CUET (UG) Cut-Offs & Merit Lists",
                    "default_query": "What are the latest CUET UG admission cut-offs and merit lists for CUK?",
                    "suggested_slots": {"doc_type": "admission", "stage": "cut_off"},
                },
                {
                    "id": "intake_capacity",
                    "title": "Approved Seat Intake Matrix",
                    "default_query": "What is the intake capacity for B.Tech, MBA, and PG programs at CUK?",
                    "suggested_slots": {"doc_type": "admission", "stage": "seat_matrix"},
                },
            ],
        },
        {
            "id": "examinations",
            "title": "Examinations & Results",
            "icon": "file-text",
            "items": [
                {
                    "id": "exam_datesheets",
                    "title": "Latest Date Sheets & Notifications",
                    "default_query": "Show me the latest exam date sheets and notifications.",
                    "suggested_slots": {"doc_type": "notice", "subject_tags": ["Exam"]},
                },
                {
                    "id": "semester_results",
                    "title": "Semester Examination Results",
                    "default_query": "How can I check semester results and re-evaluation notices?",
                    "suggested_slots": {"doc_type": "result"},
                },
            ],
        },
        {
            "id": "curriculum",
            "title": "Syllabus & Ordinances",
            "icon": "book-open",
            "items": [
                {
                    "id": "btech_syllabus",
                    "title": "B.Tech CSE Syllabus",
                    "default_query": "What is the detailed syllabus for B.Tech Computer Science & Engineering?",
                    "suggested_slots": {"doc_type": "syllabus", "program": "B.Tech CSE"},
                },
                {
                    "id": "academic_ordinances",
                    "title": "CBCS & Academic Regulations",
                    "default_query": "What are the passing criteria and attendance rules under CUK ordinances?",
                    "suggested_slots": {"doc_type": "ordinance"},
                },
            ],
        },
        {
            "id": "fees",
            "title": "Fees & Payment Schedules",
            "icon": "credit-card",
            "items": [
                {
                    "id": "tuition_fees",
                    "title": "Tuition & Exam Fee Schedules",
                    "default_query": "What is the tuition and examination fee structure for CUK courses?",
                    "suggested_slots": {"doc_type": "fee_structure"},
                },
                {
                    "id": "hostel_fees",
                    "title": "Hostel Fee Schedule",
                    "default_query": "What are the hostel admission and semester fees at CUK?",
                    "suggested_slots": {"doc_type": "fee_structure", "category": "hostel"},
                },
            ],
        },
        {
            "id": "facilities",
            "title": "Hostel & Transport Inquiries",
            "icon": "building",
            "items": [
                {
                    "id": "hostel_inquiry",
                    "title": "Hostel Accommodation Inquiries",
                    "default_query": "How can I apply for hostel accommodation at CUK?",
                    "suggested_slots": {
                        "doc_type": "general_official_document",
                        "category": "hostel",
                    },
                },
                {
                    "id": "transport_inquiry",
                    "title": "Transport & Bus Services",
                    "default_query": "What are the transport and bus route facilities at CUK?",
                    "suggested_slots": {
                        "doc_type": "general_official_document",
                        "category": "transport",
                    },
                },
            ],
        },
    ],
}


@router.get(
    "/starter",
    response_model=StarterMenuResponse,
    summary="Guided starter navigation menu",
)
def get_starter_menu(response: Response) -> StarterMenuResponse:
    """Serve 2-level guided starter menu with 1-hour public cache header."""
    response.headers["Cache-Control"] = "public, max-age=3600"

    # Attempt to load custom file if available
    menu_file = Path("configs/menu_hierarchy.json")
    if menu_file.is_file():
        try:
            with menu_file.open(encoding="utf-8") as f:
                data = json.load(f)
                return StarterMenuResponse(**data)
        except Exception:
            pass

    return StarterMenuResponse(**_DEFAULT_MENU)
