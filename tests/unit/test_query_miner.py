"""tests/unit/test_query_miner.py

Unit tests for MenuHierarchyMiner, dynamic starter menu generation, and CLI.
Governed by docs/requirements.md (FR-9.1, FR-9.2), docs/api_contracts.md Section 2.5,
and Task 6.4.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cuk_assistant.api.routes.menu import MenuCategory, StarterMenuResponse
from cuk_assistant.evals.cli import app
from cuk_assistant.evals.query_miner import MenuHierarchyMiner
from cuk_assistant.schemas.chunks import ChunkRecord, ChunkType
from cuk_assistant.schemas.document import Document


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def test_miner_default_hierarchy() -> None:
    """Validate MenuHierarchyMiner produces valid baseline schema without data."""
    miner = MenuHierarchyMiner()
    response = miner.mine()

    assert response.version == "1.0"
    cat_ids = [c.id for c in response.categories]
    assert "admissions" in cat_ids
    assert "examinations" in cat_ids
    assert "academics" in cat_ids
    assert "campus" in cat_ids

    # Validate admissions category
    admissions = next(c for c in response.categories if c.id == "admissions")
    assert admissions.title == "Admissions & Intake"
    assert admissions.icon == "graduation-cap"
    assert len(admissions.prompts) >= 4
    assert len(admissions.items) == len(admissions.prompts)

    # Check key prompts
    prompts_text = " ".join(admissions.prompts)
    assert "CUET" in prompts_text
    assert "seat intake" in prompts_text.lower() or "hostel fee" in prompts_text.lower()


def test_miner_with_admissions_metadata() -> None:
    """Validate admissions document clustering for CUET, seat intake, and prospectus."""
    miner = MenuHierarchyMiner()
    miner.add_document(
        Document(
            text="CUET PG 2026 admission notification for M.Tech programs.",
            metadata={
                "title": "CUET PG 2026 Admissions",
                "doc_type": "admission",
                "program": "M.Tech CSE",
            },
        )
    )
    miner.add_document(
        Document(
            text="Approved seat intake capacity matrix for 2025-2026.",
            metadata={
                "title": "Approved Seat Intake Matrix 2026",
                "doc_type": "admission",
                "program": "B.Tech CSE",
            },
        )
    )

    response = miner.mine()
    admissions = next(c for c in response.categories if c.id == "admissions")
    prompts = admissions.prompts

    assert any("CUET" in p for p in prompts)
    assert any("seat intake" in p.lower() for p in prompts)


def test_miner_with_examinations_metadata() -> None:
    """Validate examination chunk clustering for date sheets, results, and re-evaluation."""
    miner = MenuHierarchyMiner()
    miner.add_chunk(
        ChunkRecord(
            chunk_id="chk::exam::1",
            doc_id="doc::exam::1",
            chunk_index=0,
            chunk_type=ChunkType.HEADING,
            text_content="End Semester Examination Date Sheet for Autumn 2025",
            token_count=10,
            heading_path=["Examinations", "Date Sheet"],
            metadata={"circular_type": "notice", "program": "Integrated B.Sc-M.Sc"},
        )
    )
    miner.add_chunk(
        ChunkRecord(
            chunk_id="chk::exam::2",
            doc_id="doc::exam::2",
            chunk_index=1,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Students can apply for re-evaluation and answer script scrutiny within 15 days.",
            token_count=15,
            section_heading="Re-evaluation Notice and Guidelines",
            metadata={"circular_type": "result"},
        )
    )

    response = miner.mine()
    exams = next(c for c in response.categories if c.id == "examinations")

    assert any("date sheet" in p.lower() for p in exams.prompts)
    assert any("re-evaluation" in p.lower() for p in exams.prompts)


def test_miner_with_academics_departments() -> None:
    """Validate academic metadata extraction synthesizes department syllabus questions."""
    miner = MenuHierarchyMiner()
    miner.add_document(
        Document(
            text="Department of Biotechnology syllabus for postgraduate courses.",
            metadata={
                "title": "Biotechnology Syllabus",
                "department": "Department of Biotechnology",
                "doc_type": "syllabus",
            },
        )
    )
    miner.add_document(
        Document(
            text="Department of Physics course outlines and credit matrix.",
            metadata={
                "title": "Physics Curriculum",
                "department": "Department of Physics",
                "doc_type": "syllabus",
            },
        )
    )

    response = miner.mine()
    academics = next(c for c in response.categories if c.id == "academics")

    prompts_joined = " ".join(academics.prompts)
    assert "Biotechnology" in prompts_joined or "Physics" in prompts_joined
    assert any("ordinances" in p.lower() for p in academics.prompts)


def test_miner_with_campus_services() -> None:
    """Validate campus cluster includes hostel, library, transport, and scholarships."""
    miner = MenuHierarchyMiner()
    miner.add_chunk(
        ChunkRecord(
            chunk_id="chk::campus::1",
            doc_id="doc::campus::1",
            chunk_index=0,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Hostel allotment notice and hostel fee details for newly admitted students.",
            token_count=15,
            section_heading="Hostel Accommodation & Fee Schedule",
            metadata={"doc_type": "general"},
        )
    )
    miner.add_chunk(
        ChunkRecord(
            chunk_id="chk::campus::2",
            doc_id="doc::campus::2",
            chunk_index=1,
            chunk_type=ChunkType.PARAGRAPH,
            text_content="Central Library digital resources and OPAC catalog access guide.",
            token_count=12,
            section_heading="Central Library E-Resources",
            metadata={"doc_type": "general"},
        )
    )

    response = miner.mine()
    campus = next(c for c in response.categories if c.id == "campus")

    prompts_joined = " ".join(campus.prompts).lower()
    assert "hostel" in prompts_joined
    assert "library" in prompts_joined
    assert "transport" in prompts_joined
    assert "scholarship" in prompts_joined


def test_miner_load_from_jsonl_files(tmp_path: Path) -> None:
    """Validate loading documents and chunks from external JSONL files."""
    docs_file = tmp_path / "mock_docs.jsonl"
    chunks_file = tmp_path / "mock_chunks.jsonl"

    docs_file.write_text(
        json.dumps(
            {
                "text": "Admission selection list for MBA 2026.",
                "metadata": {
                    "title": "MBA Selection List",
                    "doc_type": "admission",
                    "program": "MBA",
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    chunks_file.write_text(
        json.dumps(
            {
                "chunk_id": "c1",
                "doc_id": "d1",
                "chunk_index": 0,
                "chunk_type": "heading",
                "text_content": "Bus Route Timetable for Tulmulla Campus",
                "token_count": 8,
                "heading_path": ["Transport", "Bus Routes"],
                "metadata": {"doc_type": "general"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    miner = MenuHierarchyMiner()
    miner.load_from_files(documents_path=docs_file, chunks_path=chunks_file)
    response = miner.mine()

    assert response.version == "1.0"
    admissions = next(c for c in response.categories if c.id == "admissions")
    campus = next(c for c in response.categories if c.id == "campus")

    assert len(admissions.prompts) > 0
    assert any("transport" in p.lower() or "bus" in p.lower() for p in campus.prompts)


def test_export_json_validates_against_api_schema(tmp_path: Path) -> None:
    """Verify exported JSON file validates against StarterMenuResponse schema."""
    miner = MenuHierarchyMiner()
    out_file = tmp_path / "menu_hierarchy.json"
    saved = miner.export_json(out_file)

    assert saved.is_file()
    with saved.open(encoding="utf-8") as f:
        data = json.load(f)

    # Validates with Pydantic model
    validated = StarterMenuResponse.model_validate(data)
    assert validated.version == "1.0"
    assert len(validated.categories) == 4

    for cat in validated.categories:
        assert cat.id
        assert cat.title
        assert cat.icon
        assert len(cat.prompts) > 0
        assert len(cat.items) == len(cat.prompts)
        for item in cat.items:
            assert item.id
            assert item.title
            assert item.default_query
            assert isinstance(item.suggested_slots, dict)


def test_menu_category_validator_syncs_prompts_and_items() -> None:
    """Verify MenuCategory auto-syncs when only prompts or only items provided."""
    # When only prompts provided (as shown in user specification)
    cat1 = MenuCategory(
        id="admissions",
        title="Admissions & Intake",
        icon="graduation-cap",
        prompts=[
            "What is the admission procedure for PG programmes via CUET?",
            "What are the hostel fee details for first-semester students?",
        ],
    )
    assert len(cat1.items) == 2
    assert (
        cat1.items[0].default_query == "What is the admission procedure for PG programmes via CUET?"
    )
    assert (
        cat1.items[1].default_query
        == "What are the hostel fee details for first-semester students?"
    )

    # When only items provided
    from cuk_assistant.api.routes.menu import MenuItem

    cat2 = MenuCategory(
        id="exams",
        title="Examinations",
        icon="file-text",
        items=[
            MenuItem(
                id="ex1",
                title="Date Sheets",
                default_query="Show me the latest exam date sheets.",
            )
        ],
    )
    assert len(cat2.prompts) == 1
    assert cat2.prompts[0] == "Show me the latest exam date sheets."


def test_cli_mine_queries(runner: CliRunner, tmp_path: Path) -> None:
    """Validate `cuk-eval mine-queries` CLI invocation."""
    out_file = tmp_path / "mined_menu.json"
    result = runner.invoke(app, ["mine-queries", "--output", str(out_file)])

    assert result.exit_code == 0
    assert "Successfully generated menu hierarchy" in result.stdout
    assert out_file.is_file()

    with out_file.open(encoding="utf-8") as f:
        data = json.load(f)

    validated = StarterMenuResponse.model_validate(data)
    assert len(validated.categories) == 4
