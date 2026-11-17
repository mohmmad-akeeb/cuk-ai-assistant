"""cuk_assistant/ingestion/chunking/hierarchical_chunker.py

Heading-aware hierarchical and parent-child Markdown chunking engine.
Preserves table atomicity (FR-1.3) and heading context breadcrumbs (FR-1.4).
"""

import re
from typing import Any

from cuk_assistant.schemas.chunks import (
    ChunkRecord,
    ChunkType,
    ParentChunkContainer,
)


def estimate_tokens(text: str) -> int:
    """Estimate token count based on whitespace word ratio.

    Approximates BAAI/bge-small-en-v1.5 and general subword tokenizers.
    """
    words = text.split()
    if not words:
        return 0
    return max(1, int(len(words) * 1.3))


def is_table_separator(line: str) -> bool:
    """Check if a line matches a GitHub Flavored Markdown table delimiter row."""
    s = line.strip()
    return bool(re.match(r"^\|?(\s*:?-+:?\s*\|)+\s*:?-+:?\s*\|?$", s))


def is_table_row(line: str) -> bool:
    """Check if a line is a markdown table row containing pipes."""
    return "|" in line


class _HeadingStack:
    """Maintains active heading hierarchy, breadcrumb paths, and parent pointer links."""

    def __init__(self) -> None:
        # Stack items: (level: int, title: str, chunk_id: str)
        self.levels: list[tuple[int, str, str]] = []

    def push(self, level: int, title: str, chunk_id: str) -> str | None:
        """Push a heading onto the stack, popping deeper or equal levels.

        Returns the parent heading chunk_id, or None if at top level.
        """
        while self.levels and self.levels[-1][0] >= level:
            self.levels.pop()
        parent_id = self.levels[-1][2] if self.levels else None
        self.levels.append((level, title, chunk_id))
        return parent_id

    @property
    def current_heading_path(self) -> list[str]:
        return [title for _, title, _ in self.levels]

    @property
    def current_section_heading(self) -> str | None:
        return self.levels[-1][1] if self.levels else None

    @property
    def current_parent_id(self) -> str | None:
        return self.levels[-1][2] if self.levels else None


class HierarchicalChunker:
    """Splits Markdown documents into structured ChunkRecord instances.

    Guarantees:
    - Tables are never sliced across chunks (atomic MARKDOWN_TABLE chunks).
    - Heading nesting is tracked via heading_path breadcrumbs.
    - Child chunks link to their parent section header via parent_chunk_id.
    - Bidirectional sibling navigation via prev_chunk_id and next_chunk_id.
    """

    def __init__(
        self,
        target_chunk_tokens: int = 400,
        max_chunk_tokens: int = 600,
        token_overlap: int = 50,
    ) -> None:
        if target_chunk_tokens <= 0:
            raise ValueError("target_chunk_tokens must be positive")
        if max_chunk_tokens < target_chunk_tokens:
            raise ValueError("max_chunk_tokens must be >= target_chunk_tokens")
        if token_overlap < 0:
            raise ValueError("token_overlap cannot be negative")
        if token_overlap >= target_chunk_tokens:
            raise ValueError("token_overlap must be less than target_chunk_tokens")

        self.target_chunk_tokens = target_chunk_tokens
        self.max_chunk_tokens = max_chunk_tokens
        self.token_overlap = token_overlap

    def chunk_markdown(
        self,
        doc_id: str,
        markdown_text: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> list[ChunkRecord]:
        """Split a Markdown string into an ordered list of ChunkRecords."""
        chunks, _ = self.chunk_markdown_with_containers(
            doc_id=doc_id,
            markdown_text=markdown_text,
            base_metadata=base_metadata,
        )
        return chunks

    def chunk_markdown_with_containers(
        self,
        doc_id: str,
        markdown_text: str,
        base_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[ChunkRecord], list[ParentChunkContainer]]:
        """Split Markdown text into ChunkRecords and ParentChunkContainers."""
        cleaned_markdown = markdown_text.strip()
        if not cleaned_markdown:
            return [], []

        meta = dict(base_metadata or {})
        lines = markdown_text.splitlines()

        # Phase 1: Parse lines into structural blocks (HEADING, TABLE, TEXT)
        blocks = self._parse_blocks(lines)

        # Phase 2: Convert blocks into chunk descriptors
        descriptors: list[dict[str, Any]] = []
        heading_stack = _HeadingStack()
        section_containers: list[dict[str, Any]] = []
        parent_container_index = 0

        for block in blocks:
            b_type = block["type"]

            if b_type == "HEADING":
                level = block["level"]
                title = block["title"]
                text = block["text"]
                idx = len(descriptors)
                chunk_id = f"{doc_id}::c{idx}"

                # Update heading hierarchy and get parent heading ID
                parent_heading_id = heading_stack.push(level, title, chunk_id)

                descriptors.append(
                    {
                        "chunk_type": ChunkType.HEADING,
                        "text_content": text,
                        "token_count": estimate_tokens(text),
                        "start_line": block["start_line"],
                        "end_line": block["end_line"],
                        "section_heading": title,
                        "heading_path": heading_stack.current_heading_path,
                        "parent_chunk_id": parent_heading_id,
                        "metadata": meta,
                    }
                )

                # Track for parent container
                section_containers.append(
                    {
                        "parent_chunk_id": f"{doc_id}::p{parent_container_index}",
                        "header_chunk_id": chunk_id,
                        "heading_title": title,
                        "heading_level": level,
                        "child_chunk_ids": [chunk_id],
                        "texts": [text],
                    }
                )
                parent_container_index += 1

            elif b_type == "TABLE":
                text = block["text"]
                idx = len(descriptors)
                chunk_id = f"{doc_id}::c{idx}"

                descriptors.append(
                    {
                        "chunk_type": ChunkType.MARKDOWN_TABLE,
                        "text_content": text,
                        "token_count": estimate_tokens(text),
                        "start_line": block["start_line"],
                        "end_line": block["end_line"],
                        "section_heading": heading_stack.current_section_heading,
                        "heading_path": list(heading_stack.current_heading_path),
                        "parent_chunk_id": heading_stack.current_parent_id,
                        "metadata": meta,
                    }
                )

                if section_containers:
                    section_containers[-1]["child_chunk_ids"].append(chunk_id)
                    section_containers[-1]["texts"].append(text)

            elif b_type == "TEXT":
                text = block["text"]
                line_offset = block["start_line"]
                text_splits = self._split_text_with_overlap(text)

                for piece in text_splits:
                    idx = len(descriptors)
                    chunk_id = f"{doc_id}::c{idx}"
                    piece_lines = piece.count("\n") + 1
                    piece_end = min(block["end_line"], line_offset + piece_lines - 1)

                    descriptors.append(
                        {
                            "chunk_type": ChunkType.PARAGRAPH,
                            "text_content": piece,
                            "token_count": estimate_tokens(piece),
                            "start_line": line_offset,
                            "end_line": piece_end,
                            "section_heading": heading_stack.current_section_heading,
                            "heading_path": list(heading_stack.current_heading_path),
                            "parent_chunk_id": heading_stack.current_parent_id,
                            "metadata": meta,
                        }
                    )

                    if section_containers:
                        section_containers[-1]["child_chunk_ids"].append(chunk_id)
                        section_containers[-1]["texts"].append(piece)

                    line_offset = piece_end + 1

        # Phase 3: Construct immutable ChunkRecord models with bidirectional chaining
        total_chunks = len(descriptors)
        chunk_records: list[ChunkRecord] = []

        for idx, desc in enumerate(descriptors):
            chunk_id = f"{doc_id}::c{idx}"
            prev_chunk_id = f"{doc_id}::c{idx - 1}" if idx > 0 else None
            next_chunk_id = f"{doc_id}::c{idx + 1}" if idx < total_chunks - 1 else None

            record = ChunkRecord(
                chunk_id=chunk_id,
                doc_id=doc_id,
                chunk_index=idx,
                chunk_type=desc["chunk_type"],
                text_content=desc["text_content"],
                token_count=desc["token_count"],
                page_number=desc.get("page_number", 1),
                start_line=desc.get("start_line"),
                end_line=desc.get("end_line"),
                table_bbox=desc.get("table_bbox"),
                section_heading=desc.get("section_heading"),
                heading_path=desc.get("heading_path", []),
                parent_chunk_id=desc.get("parent_chunk_id"),
                prev_chunk_id=prev_chunk_id,
                next_chunk_id=next_chunk_id,
                metadata=desc.get("metadata", {}),
            )
            chunk_records.append(record)

        # Phase 4: Construct ParentChunkContainer instances
        parent_containers: list[ParentChunkContainer] = []
        for sc in section_containers:
            full_text = "\n\n".join(sc["texts"])
            container = ParentChunkContainer(
                parent_chunk_id=sc["parent_chunk_id"],
                doc_id=doc_id,
                heading_title=sc["heading_title"],
                heading_level=sc["heading_level"],
                section_token_count=estimate_tokens(full_text),
                full_section_text=full_text,
                child_chunk_ids=sc["child_chunk_ids"],
            )
            parent_containers.append(container)

        return chunk_records, parent_containers

    def _parse_blocks(self, lines: list[str]) -> list[dict[str, Any]]:
        """Parse raw markdown lines into HEADING, TABLE, and TEXT blocks."""
        blocks: list[dict[str, Any]] = []
        pending_text_lines: list[str] = []
        text_start_line = 1

        in_code_fence = False
        i = 0
        total_lines = len(lines)

        while i < total_lines:
            line = lines[i]
            line_no = i + 1

            # Check code fences (``` or ~~~)
            stripped = line.strip()
            if stripped.startswith("```") or stripped.startswith("~~~"):
                in_code_fence = not in_code_fence
                pending_text_lines.append(line)
                i += 1
                continue

            if in_code_fence:
                pending_text_lines.append(line)
                i += 1
                continue

            # Check headings: # to ######
            heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
            if heading_match:
                if pending_text_lines and any(ln.strip() for ln in pending_text_lines):
                    blocks.append(
                        {
                            "type": "TEXT",
                            "text": "\n".join(pending_text_lines),
                            "start_line": text_start_line,
                            "end_line": line_no - 1,
                        }
                    )
                pending_text_lines = []
                text_start_line = line_no + 1

                level = len(heading_match.group(1))
                title = heading_match.group(2).strip()
                blocks.append(
                    {
                        "type": "HEADING",
                        "level": level,
                        "title": title,
                        "text": line.strip(),
                        "start_line": line_no,
                        "end_line": line_no,
                    }
                )
                i += 1
                continue

            # Check table start: current line has pipe, next line is separator
            if is_table_row(line) and (i + 1 < total_lines) and is_table_separator(lines[i + 1]):
                if pending_text_lines and any(ln.strip() for ln in pending_text_lines):
                    blocks.append(
                        {
                            "type": "TEXT",
                            "text": "\n".join(pending_text_lines),
                            "start_line": text_start_line,
                            "end_line": line_no - 1,
                        }
                    )
                pending_text_lines = []

                # Consume table rows
                table_lines = [line, lines[i + 1]]
                tbl_start = line_no
                i += 2
                while i < total_lines and is_table_row(lines[i]) and lines[i].strip():
                    table_lines.append(lines[i])
                    i += 1

                tbl_end = i
                blocks.append(
                    {
                        "type": "TABLE",
                        "text": "\n".join(table_lines),
                        "start_line": tbl_start,
                        "end_line": tbl_end,
                    }
                )
                text_start_line = i + 1
                continue

            # Standard body line
            if not pending_text_lines:
                text_start_line = line_no
            pending_text_lines.append(line)
            i += 1

        # Flush remaining body lines
        if pending_text_lines and any(ln.strip() for ln in pending_text_lines):
            blocks.append(
                {
                    "type": "TEXT",
                    "text": "\n".join(pending_text_lines),
                    "start_line": text_start_line,
                    "end_line": total_lines,
                }
            )

        return blocks

    def _split_text_with_overlap(self, text: str) -> list[str]:
        """Split text cleanly into pieces respecting target_chunk_tokens and token_overlap."""
        cleaned = text.strip()
        if not cleaned:
            return []

        # If already fits within max_chunk_tokens, keep as single chunk
        if estimate_tokens(cleaned) <= self.max_chunk_tokens:
            return [cleaned]

        paragraphs = [p.strip() for p in re.split(r"\n\s*\n", cleaned) if p.strip()]

        # Decompose into atomic units (sentences if paragraph is large)
        units: list[str] = []
        for p in paragraphs:
            if estimate_tokens(p) > self.target_chunk_tokens:
                sentences = re.split(r"(?<=[.!?])\s+", p)
                for s in sentences:
                    s_clean = s.strip()
                    if not s_clean:
                        continue
                    if estimate_tokens(s_clean) > self.max_chunk_tokens:
                        # Fallback for unusually long sentence without terminal punctuation
                        words = s_clean.split()
                        step = max(1, int(self.target_chunk_tokens / 1.3))
                        for w_idx in range(0, len(words), step):
                            w_slice = " ".join(words[w_idx : w_idx + step])
                            if w_slice:
                                units.append(w_slice)
                    else:
                        units.append(s_clean)
            else:
                units.append(p)

        chunks: list[str] = []
        current_units: list[str] = []
        current_tokens = 0

        for unit in units:
            unit_tokens = estimate_tokens(unit)
            if current_units and (current_tokens + unit_tokens > self.target_chunk_tokens):
                chunk_str = "\n\n".join(current_units)
                chunks.append(chunk_str)

                # Compute trailing overlap
                if self.token_overlap > 0:
                    overlap_prefix = self._get_overlap_prefix(chunk_str, self.token_overlap)
                    current_units = [overlap_prefix, unit]
                    current_tokens = estimate_tokens(overlap_prefix) + unit_tokens
                else:
                    current_units = [unit]
                    current_tokens = unit_tokens
            else:
                current_units.append(unit)
                current_tokens += unit_tokens

        if current_units:
            chunk_str = "\n\n".join(current_units)
            chunks.append(chunk_str)

        return chunks

    def _get_overlap_prefix(self, text: str, target_tokens: int) -> str:
        """Extract a trailing slice of text approximately target_tokens in length."""
        words = text.split()
        target_words = max(1, int(target_tokens / 1.3))
        if len(words) <= target_words:
            return text

        # Prefer sentence boundary if available in tail
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
        overlap_sentences: list[str] = []
        accum = 0

        for s in reversed(sentences):
            s_tok = estimate_tokens(s)
            if accum + s_tok <= int(target_tokens * 1.5) or not overlap_sentences:
                overlap_sentences.insert(0, s)
                accum += s_tok
            else:
                break

        if overlap_sentences and accum <= int(target_tokens * 1.8):
            return " ".join(overlap_sentences)

        return " ".join(words[-target_words:])


__all__ = [
    "HierarchicalChunker",
    "estimate_tokens",
    "is_table_row",
    "is_table_separator",
]
