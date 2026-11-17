# Ingestion Parsers

The parser subsystem is responsible for transforming raw extracted files into a standardized `ParsedDocument` representation.

## Architectural Design
- Strictly follows Separation of Concerns (SoC) by adhering to `DocumentParserProtocol`.
- Enables OCP by allowing new parser adapters (e.g., Docling, PDF fact extractors) without changing the pipeline.
- Standardizes output in the `ParsedDocument` Pydantic model.

## Key Components
- `cuk_assistant/core/protocols/document_parser.py`: Defines the `DocumentParserProtocol`.
- `cuk_assistant/ingestion/parsers/base.py`: Base parser class.
- `cuk_assistant/ingestion/parsers/pdf_parser.py`, `html_parser.py`, `api_parser.py`: Concrete parser implementations.
- `cuk_assistant/ingestion/parsers/subsystems/docling_adapter.py`: Specialized adapter for Docling-based parsing.
