"""CUK Assistant Pydantic Metadata Schemas."""

from cuk_assistant.schemas.chat import (
    ChatRequest,
    ChatResponse,
    CitationCard,
    FeedbackRequest,
    TurnResult,
)
from cuk_assistant.schemas.document import Document
from cuk_assistant.schemas.metadata import (
    AdmissionDocMetadata,
    DocumentMetadataUnion,
    FacultyDocMetadata,
    GeneralDocMetadata,
    NoticeDocMetadata,
    OrdinanceDocMetadata,
    ResultDocMetadata,
    SyllabusDocMetadata,
    TenderDocMetadata,
    UniversalDocMetadata,
    parse_document_metadata,
)

__all__ = [
    "AdmissionDocMetadata",
    "ChatRequest",
    "ChatResponse",
    "CitationCard",
    "Document",
    "DocumentMetadataUnion",
    "FacultyDocMetadata",
    "FeedbackRequest",
    "GeneralDocMetadata",
    "NoticeDocMetadata",
    "OrdinanceDocMetadata",
    "ResultDocMetadata",
    "SyllabusDocMetadata",
    "TenderDocMetadata",
    "TurnResult",
    "UniversalDocMetadata",
    "parse_document_metadata",
]
