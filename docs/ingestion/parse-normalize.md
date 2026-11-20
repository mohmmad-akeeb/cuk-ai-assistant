# Parse + Normalize

> **Stages 2–3 of the ingestion pipeline.** Converts raw assets into canonical documents with reconciled metadata and PII scrubbing.
>
> Related: [Ingestion Overview](./overview.md) · [Crawl](./crawl.md) · [Chunk + Index](./chunk-index.md)

---

## 1. Purpose

The parse pipeline reads `manifest.jsonl` (produced by the crawler), dispatches each raw asset to the appropriate parser (HTML, PDF, API JSON), extracts clean text, scrubs PII, reconciles metadata, and validates against the `Document` schema. Output is `documents.jsonl` — one JSONL record per canonical document.

---

## 2. Parse Pipeline Flow

```mermaid
flowchart TD
    MANIFEST["manifest.jsonl<br/>Read line by line"]
    CLASSIFY{"asset_type?"}

    subgraph HTML_PARSE["HTML Parsing"]
        HTML_FILE["data/raw/html/*.html"]
        HTML_PARSER["OfflineHtmlParser<br/>BS4 + lxml"]
        HTML_TEXT["Extracted text + links_out"]
        HTML_SCRUB["scrub_pii(text)"]
        HTML_META["Merge provenance + raw_meta"]
        HTML_DOC["Document model validated"]
    end

    subgraph API_PARSE["API JSON Parsing"]
        API_FILE["data/raw/api/*.json"]
        API_READ["Parse JSON records array"]
        API_LOOP["For each record:"]
        API_FORMAT["OfflineApiParser.format_record_text()"]
        API_INFER["_infer_doc_type()<br/>faculty / tender / admission / notice / press_release"]
        API_SCRUB["scrub_pii(text)"]
        API_META["Merge provenance + record fields"]
        API_DOC["Document model validated"]
    end

    subgraph PDF_PARSE["PDF Parsing"]
        PDF_FILE["data/raw/pdf/*.pdf"]
        PDF_GROUP["Group by filename key<br/>(multi-route dedup)"]
        PDF_AGG["aggregate_asset_references()<br/>Merge provenance from all routes<br/>that link the same PDF"]
        PDF_SENSITIVE{"is_sensitive?"}
        PDF_REDACT["text = [REDACTED]<br/>Skip content extraction"]
        PDF_PARSER["OfflinePdfParser<br/>PyMuPDF (fitz)"]
        PDF_EXTRACT["Extract text + page count<br/>+ tables + scanned pages<br/>+ embedded dates"]
        PDF_SCRUB["scrub_pii(text)"]
        PDF_META["Merged metadata + PDF facts"]
        PDF_DOC["Document model validated"]
    end

    DEDUP["Deduplicate by doc_id"]
    WRITE["documents.jsonl<br/>One line per document"]

    MANIFEST --> CLASSIFY
    CLASSIFY -->|"html"| HTML_PARSE
    CLASSIFY -->|"api_json"| API_PARSE
    CLASSIFY -->|"pdf"| PDF_PARSE

    HTML_FILE --> HTML_PARSER --> HTML_TEXT --> HTML_SCRUB --> HTML_META --> HTML_DOC
    API_FILE --> API_READ --> API_LOOP --> API_FORMAT --> API_INFER --> API_SCRUB --> API_META --> API_DOC
    PDF_FILE --> PDF_GROUP --> PDF_AGG --> PDF_SENSITIVE
    PDF_SENSITIVE -->|"Yes"| PDF_REDACT --> PDF_META
    PDF_SENSITIVE -->|"No"| PDF_PARSER --> PDF_EXTRACT --> PDF_SCRUB --> PDF_META
    PDF_META --> PDF_DOC

    HTML_DOC --> DEDUP
    API_DOC --> DEDUP
    PDF_DOC --> DEDUP
    DEDUP --> WRITE

    style HTML_PARSE fill:#1a3a1a,color:#fff
    style API_PARSE fill:#1a2a3a,color:#fff
    style PDF_PARSE fill:#3a2a1a,color:#fff
```

---

## 3. HTML Parsing

HTML assets are pages from the CUK website that contain rich HTML content (department descriptions, administrative details, content pages). The parser uses BeautifulSoup4 with lxml.

```mermaid
flowchart LR
    INPUT["HTML file from disk<br/>data/raw/html/*.html"]
    BS4["OfflineHtmlParser.parse_file()"]
    BS4_CLEAN["BeautifulSoup(html, lxml)<br/>Extract text content"]
    LINKS["Extract links_out<br/>External URLs + PDF links"]
    SCRUB["scrub_pii(text)<br/>Phone, DOB, roll numbers"]
    META["Build metadata dict:<br/>• source_url, page_url<br/>• school, department, node_path<br/>• api_endpoint, content_type<br/>• doc_id (SHA-256 of asset_id+filename)<br/>• content_hash (SHA-256 of text)"]
    VALIDATE["Document(text, metadata)<br/>Pydantic validation"]
    OUTPUT["Document.model_dump()"]

    INPUT --> BS4 --> BS4_CLEAN --> LINKS --> SCRUB --> META --> VALIDATE --> OUTPUT

    style BS4_CLEAN fill:#1a3a1a,color:#fff
    style SCRUB fill:#3a1a2a,color:#fff
    style VALIDATE fill:#1a2a3a,color:#fff
```

### `content_type` classification for HTML

| Route name contains | `content_type` |
|---------------------|---------------|
| `department` or `depart` | `department_page` |
| Otherwise | `administrative_page` |

---

## 4. API JSON Parsing

API JSON assets contain structured records (notices, tenders, admissions, faculty, press releases). Each JSON file may contain multiple records. The parser formats each record into text and infers its document type.

```mermaid
flowchart TD
    FILE["data/raw/api/*.json<br/>{endpoint, payload, records: [...]}"]
    READ["json.loads(file)<br/>Extract records array"]
    LOOP["For each record in records"]
    FORMAT["OfflineApiParser.format_record_text()<br/>Key-value text formatting"]
    EMPTY{"Text empty?"}
    SKIP["Skip record"]
    INFER["_infer_doc_type(record, entry)<br/>Check endpoint + record fields"]
    SCRUB["scrub_pii(text)"]
    META_BUILD["Build metadata:<br/>• Merge provenance from entry<br/>• Copy record fields (< 500 chars)<br/>• Set doc_type, content_type<br/>• Set doc_id (SHA-256 of asset_id+idx+text)<br/>• Set title (Title/NoticeTitle/FirstName)"]
    FACULTY{"doc_type == faculty?"}
    FAC_CHECK["Record faculty_dept_mismatch<br/>(compare DepartmentId vs page dept)"]
    VALIDATE["Document(text, metadata)"]
    OUTPUT["Add to results list"]

    FILE --> READ --> LOOP --> FORMAT --> EMPTY
    EMPTY -->|"Yes"| SKIP
    EMPTY -->|"No"| INFER --> SCRUB --> META_BUILD
    META_BUILD --> FACULTY
    FACULTY -->|"Yes"| FAC_CHECK --> VALIDATE
    FACULTY -->|"No"| VALIDATE
    VALIDATE --> OUTPUT

    style SKIP fill:#3a1a1a,color:#fff
    style FAC_CHECK fill:#3a2a1a,color:#fff
```

### Document type inference

The `_infer_doc_type()` function checks endpoint names and record fields:

| Signal | Inferred `doc_type` |
|--------|-------------------|
| Endpoint contains `faculty` or record has `FirstName`/`Designation` | `faculty` |
| Endpoint contains `tender` or record has `TenderNo`/`TenderTitle` | `tender` |
| Endpoint contains `admission` | `admission` |
| Endpoint contains `employment` | `employment` |
| Endpoint contains `notice` or record has `NoticeTitle` | `notice` |
| Endpoint contains `pressrelease` | `press_release` |
| Otherwise | `api_record` |

---

## 5. PDF Parsing

PDFs are grouped by filename key to handle multi-route references (the same PDF linked from multiple department pages). The `aggregate_asset_references()` function merges provenance from all routes, building `associated_departments` and `associated_schools` lists.

```mermaid
flowchart TD
    START["PDF files from manifest"]
    GROUP["Group by file_name key<br/>Same PDF may appear from<br/>multiple routes/departments"]
    AGG["aggregate_asset_references()<br/>Merge all provenance entries:<br/>• associated_departments (union)<br/>• associated_schools (union)<br/>• associated_routes (unique node_paths)<br/>• is_university_wide (≥3 depts or ≥2 schools)"]
    SENSITIVE{"is_sensitive flag<br/>set in raw_meta?"}
    YES_SENS["text = '[REDACTED — sensitive document]'<br/>Skip content extraction"]
    NO_SENS["OfflinePdfParser.parse_file()<br/>PyMuPDF (fitz) extraction"]
    EXTRACT["Extract:<br/>• Full text (all pages)<br/>• page_count<br/>• text_pages (per-page text)<br/>• scanned_pages count<br/>• table_count<br/>• embedded_date<br/>• needs_ocr flag"]
    SCRUB["scrub_pii(text)"]
    META["Build metadata:<br/>• doc_id (SHA-256 of 'pdf::filename')<br/>• content_hash (SHA-256 of text)<br/>• pdf_pages, page_count<br/>• file_name, file_url<br/>• found_on_page<br/>• associated_departments/schools"]
    VALIDATE["Document(text, metadata)"]

    START --> GROUP --> AGG --> SENSITIVE
    SENSITIVE -->|"Yes"| YES_SENS --> META
    SENSITIVE -->|"No"| NO_SENS --> EXTRACT --> SCRUB --> META
    META --> VALIDATE

    style YES_SENS fill:#3a1a1a,color:#fff
    style EXTRACT fill:#1a3a1a,color:#fff
    style AGG fill:#1a2a3a,color:#fff
```

### Multi-route aggregation example

A syllabus PDF for "B.Tech CSE Database Management Systems" might be linked from:
- School of Engineering → Department of CSE → Syllabus page
- School of Engineering → Department of IT → Course Outlines page

The aggregator merges both into one canonical document:

```json
{
  "associated_departments": ["Computer Science & Engineering", "Information Technology"],
  "associated_schools": ["School of Engineering & Technology"],
  "associated_routes": [["Home", "Academics", "CSE", "Syllabus"], ["Home", "Academics", "IT", "Course Outlines"]],
  "is_university_wide": false,
  "primary_department": "Computer Science & Engineering"
}
```

---

## 6. PII Sanitization

The `scrub_pii()` function applies regex-based redaction to all extracted text:

```mermaid
flowchart LR
    INPUT["Raw extracted text"]
    PHONE["scrub_phone_numbers()<br/>Replace +91-XXXXXXXXXX<br/>and 10-digit mobile numbers<br/>with [REDACTED-PHONE]"]
    DOB["scrub_dob()<br/>Replace DOB patterns<br/>(ISO format and text format)<br/>with [REDACTED-DOB]"]
    ROLL["scrub_roll_numbers()<br/>Replace Roll No / Registration No<br/>with [REDACTED-ROLL-NO]"]
    OUTPUT["Sanitized text"]

    INPUT --> PHONE --> DOB --> ROLL --> OUTPUT

    style PHONE fill:#3a1a2a,color:#fff
    style DOB fill:#3a1a2a,color:#fff
    style ROLL fill:#3a1a2a,color:#fff
```

### Regex patterns

| Pattern | Regex | Replacement |
|---------|-------|-------------|
| Mobile/phone | `\b(?:\+91[- ]?)?[6-9]\d{9}\b` | `[REDACTED-PHONE]` |
| Date of birth (ISO) | `\b(19\|20)\d{2}-\d{2}-\d{2}T00:00:00\b` | `[REDACTED-DOB]` |
| Date of birth (text) | `\b(?:DOB\|Date\s*of\s*Birth)[\s:]*([0-9]{1,2}[-/][0-9]{1,2}[-/][0-9]{2,4})\b` | `DOB: [REDACTED-DOB]` |
| Roll/Registration | `\b(?:Roll\s*(?:No\|Number)\|Registration\s*(?:No\|Number))[\s:]*([A-Za-z0-9\-_/]{4,16})\b` | `Roll No: [REDACTED-ROLL-NO]` |

Additionally, `sanitize_record_dict()` strips known sensitive keys from record dictionaries: `dob`, `mobileno`, `phone`, `aadhar`, `pan`, `bankaccount`, `ifsc`, `salary`, etc.

---

## 7. Delta Detection

The `DeltaDetector` tracks document content hashes between crawl runs to support incremental updates:

```mermaid
stateDiagram-v2
    [*] --> NEW: doc_id not in registry
    NEW --> [*]: Register hash + headers

    [*] --> UNCHANGED: doc_id exists, hash matches
    UNCHANGED --> [*]: Skip (no change needed)
    note right of UNCHANGED: HTTP headers may update<br/>if ETag/Last-Modified changed

    [*] --> MODIFIED: doc_id exists, hash differs
    MODIFIED --> [*]: Re-parse + re-chunk + re-index
    note right of MODIFIED: Content hash changed<br/>from prev_hash to new_hash

    [*] --> TOMBSTONED: doc_id in registry but not in active crawl set
    TOMBSTONED --> [*]: Mark as deleted
    note right of TOMBSTONED: Document was removed<br/>from CUK website
```

### DeltaStatus values

| Status | Condition | Action |
|--------|-----------|--------|
| `NEW` | `doc_id` not in registry | Register, parse, chunk, index |
| `UNCHANGED` | `doc_id` exists, `content_hash` matches | Skip re-processing |
| `MODIFIED` | `doc_id` exists, `content_hash` differs | Re-parse, re-chunk, re-index |
| `TOMBSTONED` | `doc_id` in registry but absent from active crawl set | Mark as deleted in LanceDB |

---

## 8. Metadata Reconciliation (TwoTierReconciler)

The `TwoTierReconciler` harmonizes two tiers of metadata:

```mermaid
flowchart TD
    T1["Tier 1: Web Provenance<br/>(from crawler)<br/>• school, department<br/>• node_path (breadcrumb)<br/>• source_url, page_url<br/>• scraped_at, etag<br/>• is_university_wide"]
    T2["Tier 2: Intrinsic Facts<br/>(from document text)<br/>• published_date<br/>• academic_year<br/>• circular_reference<br/>• course_code, batch_year<br/>• semester, program"]
    RAW["Raw document text"]

    RECONCILE["TwoTierReconciler.reconcile()<br/>t1, t2, raw_text"]

    subgraph RESOLUTION["Resolution precedence"]
        TITLE["Title: t1.title → t2.title → 'Untitled Document'"]
        HASH["Content hash: t1 → t2 → SHA-256(text)"]
        DOC_ID["Doc ID: t1 → t2 → SHA-256(source_url::page_url::title)[:16]"]
        DATE["Published date: t2 (precedence) → t1 → text extraction"]
        YEAR["Academic year: t2 → t1 → text extraction"]
    end

    CLASSIFY["_classify_and_harvest()<br/>Regex-based domain detection:<br/>syllabus, result, admission,<br/>notice, tender, ordinance, faculty"]

    subgraph DOMAINS["7 Polymorphic domain types"]
        D1["SyllabusDocMetadata<br/>program, batch_year, semester,<br/>course_code, course_title, credits"]
        D2["ResultDocMetadata<br/>exam_session, notification_number,<br/>result_type, program"]
        D3["AdmissionDocMetadata<br/>admission_year, program, stage"]
        D4["NoticeDocMetadata<br/>reference_number, issuing_office"]
        D5["TenderDocMetadata<br/>tender_number, nit_date, emd_amount"]
        D6["OrdinanceDocMetadata<br/>ordinance_number, subject"]
        D7["FacultyDocMetadata<br/>employee_name, designation, email"]
        D8["GeneralDocMetadata<br/>(fallback)"]
    end

    VALIDATE["Pydantic validation<br/>+ FR-1.5 universal fallback"]
    OUTPUT["DocumentMetadataUnion<br/>(typed polymorphic metadata)"]

    T1 --> RECONCILE
    T2 --> RECONCILE
    RAW --> RECONCILE
    RECONCILE --> RESOLUTION
    RESOLUTION --> CLASSIFY
    CLASSIFY --> DOMAINS
    DOMAINS --> VALIDATE --> OUTPUT

    style T1 fill:#1a2a3a,color:#fff
    style T2 fill:#1a3a1a,color:#fff
    style CLASSIFY fill:#3a2a1a,color:#fff
    style DOMAINS fill:#3a1a2a,color:#fff
```

### Domain-specific field harvesting

The reconciler uses regex patterns to extract domain-specific fields from document text:

| Domain | Regex-extracted fields |
|--------|----------------------|
| Syllabus | `program` (B.Tech/M.Tech/MCA/MBA...), `batch_year`, `semester` (Roman/Arabic), `course_code` (BT-101, CS-C402), `credits` |
| Result | `exam_session`, `notification_number`, `result_type` (regular/re_evaluation/backlog) |
| Admission | `admission_year`, `stage` (cut_off/selection_list/counselling), `intake_capacity` |
| Notice | `reference_number` (CUK/Acad/2023/123), `issuing_office`, `is_urgent` |
| Tender | `tender_number` (NIT No), `nit_date`, `closing_date`, `emd_amount` |
| Ordinance | `ordinance_number`, `subject`, `governing_body`, `effective_date` |
| Faculty | `employee_name`, `designation`, `email` (masked), `qualifications`, `research_areas` |

---

## 9. Output Format

Each line in `documents.jsonl` is a serialized `Document` model:

```json
{
  "text": "The Central University of Kashmir offers a 4-semester B.Tech program...",
  "metadata": {
    "doc_id": "a1b2c3d4e5f6a1b2c3d4e5f6",
    "doc_type": "syllabus",
    "title": "B.Tech CSE Syllabus 2022",
    "normalized_title": "b.tech cse syllabus 2022",
    "source_url": "https://cukashmir.ac.in/docs/btech_cse_2022.pdf",
    "page_url": "https://cukashmir.ac.in/#/departmentList;id=...",
    "school": "School of Engineering & Technology",
    "department": "Department of Computer Science & Engineering",
    "node_path": ["Home", "Academics", "Engineering", "CSE"],
    "published_date": "2022-06-15",
    "academic_year": "2022-2023",
    "is_university_wide": false,
    "content_hash": "sha256...",
    "scraped_at": "2024-11-21T10:30:00+00:00",
    "program": "B.Tech Computer Science & Engineering",
    "batch_year": "2022",
    "semester": "Semester 4",
    "course_code": "BT-CSE-401",
    "course_title": "Database Management Systems",
    "credits": 4,
    "associated_departments": ["Computer Science & Engineering"],
    "associated_routes": [["Home", "Academics", "CSE", "Syllabus"]],
    "pdf_pages": 12,
    "page_count": 12
  }
}
```

---

## 10. Concurrency

The parse pipeline uses a `ThreadPoolExecutor` to parse assets in parallel:

| Asset type | Concurrency | Parser |
|-----------|-------------|--------|
| HTML | Up to `min(32, CPU+4)` threads | `OfflineHtmlParser` (BS4) |
| API JSON | Same pool | `OfflineApiParser` (JSON) |
| PDF | Same pool | `OfflinePdfParser` (PyMuPDF) |

PDFs are grouped first (by filename key), then each group is parsed as a unit.

---

## 11. Key Files

| File | Responsibility |
|------|---------------|
| `ingestion/cli/parse.py` | CLI entry point (`cuk-parse`) |
| `ingestion/normalization/subsystems/pipeline.py` | Parse orchestrator (`parse_manifest`) |
| `ingestion/parsers/html_parser.py` | HTML parsing (BS4 + lxml) |
| `ingestion/parsers/pdf_parser.py` | PDF parsing (PyMuPDF) |
| `ingestion/parsers/api_parser.py` | API JSON record formatting |
| `ingestion/normalization/subsystems/sanitizer.py` | PII scrubbing (phone, DOB, roll, email) |
| `ingestion/normalization/subsystems/aggregator.py` | Multi-route reference aggregation |
| `ingestion/normalization/subsystems/reconciler.py` | Two-tier metadata reconciliation |
| `ingestion/normalization/subsystems/delta_detector.py` | Incremental delta detection |
| `ingestion/normalization/subsystems/metadata_normalizer.py` | Regex extractors (batch year, semester, etc.) |
| `schemas/document.py` | `Document` Pydantic model |
| `schemas/metadata.py` | Polymorphic metadata schemas (7 domain types) |
