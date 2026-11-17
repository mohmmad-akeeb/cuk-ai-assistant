"""tests/unit/test_hierarchical_chunker.py

Unit tests for HierarchicalChunker:
- Heading-aware nesting and breadcrumb paths (FR-1.4)
- GFM Markdown table atomicity (FR-1.3)
- Parent-child linking and bidirectional chaining
- Token budgeting and overlap splitting
"""

import pytest

from cuk_assistant.ingestion.chunking.hierarchical_chunker import (
    HierarchicalChunker,
    estimate_tokens,
    is_table_row,
    is_table_separator,
)
from cuk_assistant.schemas.chunks import ChunkType


class TestHierarchicalChunkerBasics:
    """Validate initialization, edge inputs, and helper functions."""

    def test_init_validation(self) -> None:
        chunker = HierarchicalChunker(
            target_chunk_tokens=300, max_chunk_tokens=500, token_overlap=40
        )
        assert chunker.target_chunk_tokens == 300
        assert chunker.max_chunk_tokens == 500
        assert chunker.token_overlap == 40

        with pytest.raises(ValueError):
            HierarchicalChunker(target_chunk_tokens=0)

        with pytest.raises(ValueError):
            HierarchicalChunker(target_chunk_tokens=500, max_chunk_tokens=300)

        with pytest.raises(ValueError):
            HierarchicalChunker(token_overlap=-1)

        with pytest.raises(ValueError):
            HierarchicalChunker(target_chunk_tokens=100, token_overlap=100)

    def test_empty_or_whitespace_markdown(self) -> None:
        chunker = HierarchicalChunker()
        assert chunker.chunk_markdown("doc_empty", "") == []
        assert chunker.chunk_markdown("doc_space", "   \n\n\t  ") == []

    def test_estimate_tokens_word_ratio(self) -> None:
        assert estimate_tokens("") == 0
        assert estimate_tokens("hello") == 1
        assert estimate_tokens("one two three four five") == int(5 * 1.3)

    def test_table_detection_helpers(self) -> None:
        assert is_table_row("| Col 1 | Col 2 |") is True
        assert is_table_row("Regular paragraph text.") is False
        assert is_table_separator("|---|---|") is True
        assert is_table_separator("| :--- | ---: |") is True
        assert is_table_separator("Col 1 | Col 2") is False


class TestHeadingHierarchyAndBreadcrumbs:
    """Validate FR-1.4: Heading-aware AST chunking with breadcrumb paths."""

    def test_three_level_heading_nesting(self) -> None:
        markdown_text = """# School of Engineering & Technology
The School of Engineering was established to provide excellence in technical education.

## Department of Computer Science & Engineering
The department offers undergraduate and postgraduate curricula in computing.

### BT-CSE-401 Database Management Systems
This course provides foundational concepts in database systems and relational calculus.

### BT-CSE-402 Operating Systems
This course covers process synchronization, memory management, and file systems.

## Department of Electrical Engineering
The department offers core engineering disciplines.
"""
        chunker = HierarchicalChunker()
        chunks = chunker.chunk_markdown(doc_id="cuk_eng_01", markdown_text=markdown_text)

        assert len(chunks) > 0

        # Chunk 0: # School of Engineering & Technology
        h1 = chunks[0]
        assert h1.chunk_type == ChunkType.HEADING
        assert h1.chunk_id == "cuk_eng_01::c0"
        assert h1.section_heading == "School of Engineering & Technology"
        assert h1.heading_path == ["School of Engineering & Technology"]
        assert h1.parent_chunk_id is None

        # Chunk 1: School intro paragraph
        p1 = chunks[1]
        assert p1.chunk_type == ChunkType.PARAGRAPH
        assert p1.parent_chunk_id == h1.chunk_id
        assert p1.heading_path == ["School of Engineering & Technology"]

        # Chunk 2: ## Department of Computer Science & Engineering
        h2_cse = chunks[2]
        assert h2_cse.chunk_type == ChunkType.HEADING
        assert h2_cse.section_heading == "Department of Computer Science & Engineering"
        assert h2_cse.heading_path == [
            "School of Engineering & Technology",
            "Department of Computer Science & Engineering",
        ]
        assert h2_cse.parent_chunk_id == h1.chunk_id

        # Chunk 3: Dept intro paragraph
        p2 = chunks[3]
        assert p2.parent_chunk_id == h2_cse.chunk_id
        assert p2.heading_path == [
            "School of Engineering & Technology",
            "Department of Computer Science & Engineering",
        ]

        # Chunk 4: ### BT-CSE-401 Database Management Systems
        h3_dbms = chunks[4]
        assert h3_dbms.chunk_type == ChunkType.HEADING
        assert h3_dbms.section_heading == "BT-CSE-401 Database Management Systems"
        assert h3_dbms.heading_path == [
            "School of Engineering & Technology",
            "Department of Computer Science & Engineering",
            "BT-CSE-401 Database Management Systems",
        ]
        assert h3_dbms.parent_chunk_id == h2_cse.chunk_id

        # Chunk 5: DBMS intro paragraph
        p3 = chunks[5]
        assert p3.parent_chunk_id == h3_dbms.chunk_id
        assert p3.heading_path == [
            "School of Engineering & Technology",
            "Department of Computer Science & Engineering",
            "BT-CSE-401 Database Management Systems",
        ]

        # Chunk 6: ### BT-CSE-402 Operating Systems (sibling heading level 3)
        h3_os = chunks[6]
        assert h3_os.chunk_type == ChunkType.HEADING
        assert h3_os.section_heading == "BT-CSE-402 Operating Systems"
        assert h3_os.heading_path == [
            "School of Engineering & Technology",
            "Department of Computer Science & Engineering",
            "BT-CSE-402 Operating Systems",
        ]
        assert h3_os.parent_chunk_id == h2_cse.chunk_id

        # Chunk 8: ## Department of Electrical Engineering (sibling heading level 2)
        h2_ee = chunks[8]
        assert h2_ee.chunk_type == ChunkType.HEADING
        assert h2_ee.section_heading == "Department of Electrical Engineering"
        # Notice: level 2 pops level 2 and level 3 from previous branch!
        assert h2_ee.heading_path == [
            "School of Engineering & Technology",
            "Department of Electrical Engineering",
        ]
        assert h2_ee.parent_chunk_id == h1.chunk_id


class TestMarkdownTableAtomicity:
    """Validate FR-1.3: Markdown tables must NEVER be sliced across chunks."""

    def test_fifteen_row_table_atomic_retention(self) -> None:
        table_rows = [
            "| Semester | Course Code | Course Name | Credits | Lab |",
            "| :---: | :--- | :--- | :---: | :---: |",
        ]
        for i in range(1, 16):
            table_rows.append(
                f"| Sem {i % 8 + 1} | BT-CSE-{400 + i} | Advanced Computing Module {i} with Extended Specifications and Curriculum | 4.0 | Yes |"
            )
        table_markdown = "\n".join(table_rows)

        full_doc = f"""# B.Tech CSE Curriculum 2024
The following table outlines the complete course matrix for the 4-year degree program:

{table_markdown}

All students must earn minimum 160 credits to be eligible for degree award.
"""

        # Set small max_chunk_tokens (e.g. 100) to ensure the table by token count exceeds max_chunk_tokens
        chunker = HierarchicalChunker(
            target_chunk_tokens=80, max_chunk_tokens=100, token_overlap=10
        )
        chunks = chunker.chunk_markdown(doc_id="cuk_table_doc", markdown_text=full_doc)

        # Locate the table chunk(s)
        table_chunks = [c for c in chunks if c.chunk_type == ChunkType.MARKDOWN_TABLE]

        # Invariant 1: Exactly ONE table chunk for the entire 15-row table
        assert len(table_chunks) == 1, (
            "The 15-row table was incorrectly sliced across multiple chunks!"
        )

        table_chunk = table_chunks[0]
        # Invariant 2: Chunk type is MARKDOWN_TABLE
        assert table_chunk.chunk_type == ChunkType.MARKDOWN_TABLE

        # Invariant 3: Contains all 15 data rows plus header and separator
        assert "Advanced Computing Module 1 " in table_chunk.text_content
        assert "Advanced Computing Module 15 " in table_chunk.text_content
        assert (
            table_chunk.text_content.count("\n") == 16
        )  # 1 header + 1 separator + 15 rows = 17 lines = 16 newlines

        # Invariant 4: Token count exceeds max_chunk_tokens (100) but table remained intact
        assert table_chunk.token_count > 100

        # Invariant 5: Context links
        assert table_chunk.section_heading == "B.Tech CSE Curriculum 2024"
        assert table_chunk.heading_path == ["B.Tech CSE Curriculum 2024"]
        assert table_chunk.parent_chunk_id == "cuk_table_doc::c0"


class TestParentChildAndBidirectionalChaining:
    """Validate deterministic IDs, parent links, and bidirectional traversal."""

    def test_bidirectional_chaining_and_parent_links(self) -> None:
        doc = """# Unit 1: Relational Algebra
Introductory overview of relational algebra operators.

Detailed discussion on projection, selection, and cartesian product.

# Unit 2: SQL Query Optimization
Overview of query execution trees.
"""
        chunker = HierarchicalChunker(target_chunk_tokens=300, max_chunk_tokens=500)
        chunks = chunker.chunk_markdown(doc_id="dbms_syllabus", markdown_text=doc)

        total = len(chunks)
        assert total >= 4

        # Validate sequential chunk_index and chunk_id format
        for idx, c in enumerate(chunks):
            assert c.chunk_index == idx
            assert c.chunk_id == f"dbms_syllabus::c{idx}"

        # Validate bidirectional navigation
        assert chunks[0].prev_chunk_id is None
        assert chunks[0].next_chunk_id == chunks[1].chunk_id
        assert chunks[-1].next_chunk_id is None
        assert chunks[-1].prev_chunk_id == chunks[-2].chunk_id

        for i in range(1, total - 1):
            assert chunks[i].prev_chunk_id == chunks[i - 1].chunk_id
            assert chunks[i].next_chunk_id == chunks[i + 1].chunk_id

        # Validate parent-child links
        unit1_header = chunks[0]
        assert unit1_header.chunk_type == ChunkType.HEADING
        assert unit1_header.parent_chunk_id is None

        # Child chunks under Unit 1 link to Unit 1's header chunk ID
        unit1_child1 = chunks[1]
        assert unit1_child1.chunk_type == ChunkType.PARAGRAPH
        assert unit1_child1.parent_chunk_id == unit1_header.chunk_id


class TestBodyTextSplittingWithOverlap:
    """Validate splitting large text subsections with token overlap."""

    def test_large_section_split_cleanly_with_overlap(self) -> None:
        # Create a document with ~30 distinct sentences in one subsection
        sentences = [
            f"Regulation rule number {i} stipulates that every student must register before commencement."
            for i in range(1, 40)
        ]
        body = " ".join(sentences)
        markdown_text = f"# Academic Regulations\n\n{body}\n"

        chunker = HierarchicalChunker(
            target_chunk_tokens=80, max_chunk_tokens=120, token_overlap=25
        )
        chunks = chunker.chunk_markdown(doc_id="reg_doc", markdown_text=markdown_text)

        # Header chunk + multiple paragraph chunks
        assert len(chunks) >= 3

        paragraph_chunks = [c for c in chunks if c.chunk_type == ChunkType.PARAGRAPH]
        for p in paragraph_chunks:
            assert p.parent_chunk_id == "reg_doc::c0"
            assert p.heading_path == ["Academic Regulations"]

        # Validate overlap between successive paragraph chunks
        for i in range(len(paragraph_chunks) - 1):
            curr_text = paragraph_chunks[i].text_content
            next_text = paragraph_chunks[i + 1].text_content

            # The next chunk starts with trailing content from the current chunk
            curr_words = curr_text.split()
            overlap_probe = " ".join(curr_words[-3:])
            assert overlap_probe in next_text, (
                f"Expected trailing words '{overlap_probe}' from chunk {i} to appear in chunk {i + 1} as overlap."
            )


class TestCodeFenceAndContainers:
    """Validate code fence immunity and ParentChunkContainer output."""

    def test_code_fence_does_not_trigger_heading_or_table(self) -> None:
        markdown_text = """# Developer Guide
Here is sample code:

```python
# This is a Python comment, not a heading!
| this | is | not | a | table |
|---|---|---|---|---|
```

End of developer guide.
"""
        chunker = HierarchicalChunker()
        chunks = chunker.chunk_markdown(doc_id="dev_doc", markdown_text=markdown_text)

        headings = [c for c in chunks if c.chunk_type == ChunkType.HEADING]
        tables = [c for c in chunks if c.chunk_type == ChunkType.MARKDOWN_TABLE]

        # Only one heading (the true # Developer Guide)
        assert len(headings) == 1
        assert headings[0].section_heading == "Developer Guide"

        # Zero false tables
        assert len(tables) == 0

    def test_chunk_markdown_with_containers(self) -> None:
        doc = """# Admissions 2024
Overview of the admissions criteria.

## Counseling Schedule
Counseling dates for B.Tech CSE.
"""
        chunker = HierarchicalChunker()
        chunks, containers = chunker.chunk_markdown_with_containers(
            doc_id="cuk_adm",
            markdown_text=doc,
            base_metadata={"academic_year": 2024},
        )

        assert len(chunks) == 4
        assert len(containers) == 2

        c0 = containers[0]
        assert c0.parent_chunk_id == "cuk_adm::p0"
        assert c0.heading_title == "Admissions 2024"
        assert c0.heading_level == 1
        assert "cuk_adm::c0" in c0.child_chunk_ids
        assert "cuk_adm::c1" in c0.child_chunk_ids

        c1 = containers[1]
        assert c1.parent_chunk_id == "cuk_adm::p1"
        assert c1.heading_title == "Counseling Schedule"
        assert c1.heading_level == 2
        assert "cuk_adm::c2" in c1.child_chunk_ids
        assert "cuk_adm::c3" in c1.child_chunk_ids
