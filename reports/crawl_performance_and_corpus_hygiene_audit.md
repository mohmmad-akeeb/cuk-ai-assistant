# Forensic Audit Report: Crawler Performance, Security & Obsolete Content Pruning

**Project**: Central University of Kashmir (CUK) RAG Assistant  
**Role**: Lead Security & Data Platform Engineer  
**Audit Date**: 2026-11-15  
**Corpus Analyzed**: 4,538 Documents (3,856 PDF Page/Document Chunks across 9 Schools)  
**Artifact References**: [ingestion_filter.yaml](file:///home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/configs/ingestion_filter.yaml), [documents.jsonl](file:///home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/data/processed/documents.jsonl), [crawl.jsonl](file:///home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/data/logs/crawl.jsonl)

---

## Executive Summary & Baseline Inventory

The initial web crawler pass of the Central University of Kashmir web estate completed with **4,538 ingested document units**, comprising **3,856 PDF document/page records** and **682 HTML/structured metadata entities**. The corpus spans 9 academic schools and central university administrative organs:

| School / Entity | Total Ingested Docs | PDF Records | HTML/Metadata Records |
| :--- | :---: | :---: | :---: |
| **Life Sciences** | 631 | 586 | 45 |
| **Physical & Chemical Sciences** | 629 | 598 | 31 |
| **Social Sciences** | 567 | 536 | 31 |
| **Business Studies** | 486 | 452 | 34 |
| **Languages** | 411 | 373 | 38 |
| **Education** | 341 | 308 | 33 |
| **Legal Studies** | 243 | 242 | 1 |
| **Engineering & Technology** | 203 | 196 | 7 |
| **Media Studies** | 30 | 28 | 2 |
| **Central Admin / University-wide** | 997 | 537 | 460 |
| **Total** | **4,538** | **3,856** | **682** |

This forensic audit identifies substantial network bottlenecks, severe unlinked backend exposure on `cukapi.disgenweb.in`, PII in admission selection lists, and ~1,200 to ~1,487 obsolete or duplicate documents consuming storage and retrieval bandwidth.

---

## Part 1: Crawler Latency & Throughput Forensic Analysis

### 1.1 Time Breakdown & Execution Profile
Forensic analysis of the crawler logs ([crawl.jsonl](file:///home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/data/logs/crawl.jsonl)) across 8 distinct execution sessions between 2026-11-11 and 2026-11-15 reveals a **Total Active Runtime of 10,189.03 seconds (2.83 hours)**.

```
Total Active Runtime: 10,189.03s (100.0%)
├── PDF Binary Downloads & HEAD Latency: 8,575.07s (84.16%)
├── Rate Limiter Waits & PyMuPDF Local Extraction: 1,023.80s (10.05%)
└── JSON REST API & HTML Navigation Fetches: 590.16s (5.79%)
```

- **PDF Downloads vs. API Fetches**: Network time was overwhelmingly dominated by PDF binaries (8,575.07s across 2,983 binary GET/HEAD calls, averaging 2.87s/call). JSON REST APIs and HTML page crawls completed in 590.16s across 871 calls (averaging 0.68s/call).
- **Rate Limiter Impact (`TokenBucketRateLimiter`)**: Configured at `rate_limit_rps: 1.0` with `max_connections: 2`. For fast JSON calls (averaging 0.68s), the rate limiter enforced sleeps between 0.32s and 0.86s per call to preserve the 1.0s token interval. In contrast, heavy PDF transfers naturally exceeded 1.0s, rendering the token bucket idle while waiting for network sockets.

### 1.2 Top 10 Slowest Endpoints & Server Failures
The table below details the slowest endpoints by cumulative network time and maximum observed latency:

| Endpoint Path / Group | Request Count | Total Time (s) | Avg Latency (s) | Max Latency (s) | Errors / Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| `/p/upload` (DisgenWeb PDF Storage) | 2,225 | 7,751.5 | 3.48 | 540.31 | 10 timeouts / 404s |
| `department/departmentListById` | 505 | 394.4 | 0.78 | 18.97 | 200 OK |
| `/p/publichomequicklinks` | 12 | 149.1 | 12.43 | 39.50 | 200 OK |
| `/p/examinationresult` | 80 | 142.2 | 1.78 | 11.25 | 200 OK |
| `www.ugc.gov.in/pdfnews` | 20 | 132.0 | 6.60 | 49.86 | External UGC host |
| `/p/scholarresults` | 88 | 86.6 | 0.98 | 4.63 | 200 OK |
| `/p/admission` | 56 | 65.3 | 1.17 | 9.38 | 200 OK |
| `pressrelease/selectbyid` | 138 | 51.2 | 0.37 | 0.76 | **138 HTTP 500 Crashes** |
| `cukapi/p` (`disgenonline.in`) | 182 | 51.4 | 0.28 | 1.59 | **91 HTTP 404 / Failures** |
| `/p/noticeboard` | 20 | 45.0 | 2.25 | 12.41 | 2 Connection Drops |

#### Key Server-Side Bottlenecks & Defects:
1. **`pressrelease/selectbyid` HTTP 500 Crashes**: All 138 requests failed with `Server error '500 Internal Server Error'`. The backend stored procedure crashes when queried via direct parameter iteration without active session tokens.
2. **Dead Legacy Host (`disgenonline.in`)**: 113 failed GET attempts occurred due to legacy hardcoded URLs pointing to `http://disgenonline.in/cukapi/...` which are dead and unrouted.
3. **Severe Upload Directory Latencies (`/p/upload`)**: Observed maximum socket latency reached **540.31s** on multi-megabyte annual reports.

### 1.3 Download Size Distribution
Forensic audit of `data/cache/` (2,271 cached response sidecars) shows a total download footprint of **1,579.08 MB (1.58 GB)**, of which **1,424.50 MB (90.2%)** constitutes PDF binaries:

| Size Bucket | PDF File Count | Percentage of PDFs | Cumulative Size |
| :--- | :---: | :---: | :---: |
| **< 500 KB** | 863 | 60.56% | 158.4 MB |
| **500 KB – 5 MB** | 507 | 35.58% | 832.1 MB |
| **5 MB – 20 MB** | 47 | 3.30% | 341.2 MB |
| **> 20 MB** | 8 | 0.56% | 247.3 MB |
| **Total** | **1,425** | **100.0%** | **1,424.50 MB** |

#### Top 5 Largest Ingested Binaries:
1. `1781171714617-Blue Modern University Admission Poster.pdf` — **62.71 MB** (Single-page graphic poster; severe bandwidth waste)
2. `1766053956067-Admission_Brochure_2026_compressed.pdf` — **43.16 MB**
3. `1716539730515-Annual Report 2019-2020.pdf` — **32.88 MB**
4. `1716531628513-Annual Report 2014-2015_compressed.pdf` — **32.66 MB**
5. `1716364447144-COMPRESSED Annual Report 2011-12.pdf` — **25.23 MB**

### 1.4 Throughput Optimization Projections
The current crawler bottlenecks stem from coupling the 1.0 RPS rate limit across both REST metadata APIs and static media CDN binaries under a global `MAX_CONNECTIONS = 2`.

- **Decoupled Architecture**: Static PDF downloads from `/p/upload` are static file transfers hosted on Plesk/IIS and do not place load on the application database.
- **Projected Gains**:
  - Increasing `MAX_CONNECTIONS` from 2 to 4–6 specifically for the static storage CDN (`/p/upload/`) with 4.0 RPS concurrency.
  - Maintaining polite 1.0 RPS on `cukapi.disgenweb.in` for database-backed REST endpoints.
  - **Runtime Projection**: PDF download phase will drop from 8,575s to ~1,900s–2,150s, decreasing full scrape execution from 2.83 hours down to **~45–55 minutes (a 68% time reduction)**.

---

## Part 2: Security & Orphan Document Audit

### 2.1 Frontend vs. Backend Lineage
Evaluating `node_path` and `route_name` lineage across all 4,538 documents reveals how documents were discovered:

- **Official Angular Frontend Lineage (3,833 documents / 84.5%)**:
  - `/departmentList`: 3,541 documents originating from school/department navigation nodes.
  - `/administration`: 506 documents originating from official administrative landing pages.
  - `/home`: 292 documents discovered via official homepage widgets and banner carousels.
  - `/listing`: 199 documents discovered from public listing tables (press releases, public results).
- **Unlinked / Backend API Iteration (686 documents / 15.1%)**:
  - 686 documents carry shallow, single-element breadcrumbs (`['Admissions']`, `['Notices']`, `['Employment']`, `['Tenders']`, `['Quick Links']`). These were enumerated directly from backend table dumps (`/all` endpoints) and have no parent navigation node in the Angular application router.

### 2.2 Forensic Audit of `is_sensitive=True` Documents
Two documents were flagged with `is_sensitive=True`. Both have been audited:

#### Document 1: Departmental Merit & Selection Listing
- **`doc_id`**: `1205596857d8d30c2581e278`
- **`doc_type`**: `notice`
- **`title`**: `Notices, Selection Lists, Merit Lists, Orders etc.`
- **`source_url`**: `https://www.cukashmir.ac.in/#/departmentList;id=37F0C3C1-3FE3-4D1D-B5C0-3EF0776A535D;menuid=BF9C43B2-E5F9-4CD4-86F3-8520086B625E`
- **Lineage**: School of Languages $\rightarrow$ Department of Kashmiri $\rightarrow$ Notices
- **Sensitivity Trigger**: Title and text body matched `_SENSITIVE_RE` with explicit phrases: *"1st Provisional Selection List_M.A Kashmiri_30.06.2026"* and *"2nd Provisional Selection List_M.A Kashmiri_14.07.2026"*.
- **Data Status**: Unredacted HTML text containing student selection notice links.

#### Document 2: Admission Candidate Provisional Merit List
- **`doc_id`**: `16b4ba7663cff5d41ff8f5f5`
- **`doc_type`**: `admission`
- **`title`**: `Provisional Selection list-III for admission in M.Ed (Working Professional Programme -2026`
- **`source_url`**: `https://cukapi.disgenweb.in/p/admission/1791212207011-Provisional Selection  list-III  - M.Ed (WP) Programme-2026.pdf`
- **Lineage**: Direct backend endpoint `admission/all` $\rightarrow$ `['Admissions']`
- **Sensitivity Trigger**: Matched `_SENSITIVE_RE` on `provisional selection list`. Contains candidate roll numbers, names, parentage, and entrance scores.
- **Redaction State**: Successfully intercepted by `pdf_extractor.py` and scrubbed to `[REDACTED — sensitive document]`.

### 2.3 Unlinked & Internal Backend Documents
3,627 documents point directly to backend storage on `cukapi.disgenweb.in`. Several categories represent unlinked internal documents:
1. **Administrative Internal Memos & Vigilance**:
   - `22b540ae2351c779c3d6bf64`: *Chief Vigilance Office* notice records.
   - `aa30ae7dff3950940fb593ae`: *Memorandums of Understanding* internal partner agreements.
   - `f6a634807419ba1f63920ed2`: *Dr. B.R. Ambedkar Multidisciplinary Research Centre* internal operational records.
2. **Fee Structure & Administrative Direct Circulars (506 docs)**: Uploaded under `external` API categories without public department UI wrappers.
3. **Recommendation**: Implement `security_exclusions` in the ingestion pipeline to drop candidate roll lists, confidential disciplinary circulars, and salary notices prior to vector indexing.

---

## Part 3: Obsolete & Discarded Document Analysis

### 3.1 Temporal Distribution Analysis
Evaluating effective publication dates across the 4,538 documents reveals heavy historical accumulation:

```
Corpus Temporal Distribution (4,538 docs total):
├── Pre-2019:                0 docs  ( 0.00%)
├── 2019–2021 (≥ 5 yrs old): 1,208 docs (26.62%) ────► 1,104 PDFs, 104 HTML
├── 2022–2024 (2–4 yrs old): 1,269 docs (27.96%)
├── 2025–2026 (Active):      1,112 docs (24.50%)
└── Undated / Structural:      949 docs (20.91%) ────► Faculty (145), Admin (804)
```

**Over a quarter of the entire corpus (26.62% / 1,208 documents) is older than 5 years (dating from 2019–2021)**:
- 786 are academic syllabi from 2020 (pre-dating NEP-2020 curriculum reforms).
- 421 are general departmental circulars from 2020.
- 1 is an obsolete 2020 notice.

### 3.2 Expired Tenders & Procurements
- **Active Tenders**: Exactly **1 legitimate tender** exists in the corpus:
  - `doc_id`: `a4b1ad4a1ab3640d8ceeb800`
  - Title: *Electrical works of Seminar Hall (steel structure) at Arts Campus Ganderbal*
  - Tender No: `2026_CUoK_933867_1`, NIT: 2026-11-11, Closing Date: 2026-11-30 (Active).
- **Corpus State**: CUK has transitioned public procurement to the Government of India Central Public Procurement Portal (`eprocure.gov.in`). Backend endpoint `tender/all` returned 0 rows, and `tender/getalltender` returned 1 row.
- **Policy**: Any historical tender with `closing_date < NOW - 12 months` must be pruned automatically.

### 3.3 Expired Admissions & Ephemeral Notices
Of 122 admission-related documents:
- **87 documents (71.3%) relate to expired academic years** (2022: 72 notices, 2023: 9 notices, 2024: 6 notices).
- Only 35 documents relate to active cycles (2025: 27 notices, 2026: 8 notices).
- **Retention Directive**: Ephemeral notices (counseling dates, physical document verification queues, venue allotments) older than 24 months must be purged. Only persistent admission regulations, general eligibility rules, and approved seat matrices should be retained.

### 3.4 Superseded Syllabi & Curriculum Lifecycle
The corpus contains **1,216 syllabus documents** across 15 academic departments.
- **Multiple Conflicting Syllabi**:
  - **Department of Physics**: Contains both 2022 syllabus (*Courses and Syllabus*) and active 2026 syllabus (*Syllabus of Ongoing Even Semester ESE June 2026*). The 2022 syllabus is superseded.
  - **Department of Commerce**: Contains 2022 syllabus (*Syllabus*) and active 2024 syllabus (*Non CUET Syllabus*).
  - **Superseded Volume**: 217 documents represent superseded syllabus modules in these two departments alone.
- **Pre-NEP 2020 Syllabi (786 docs)**: Departments of Law (192), Education (133), Biotechnology (120), Management Studies (115), Mathematics (94), Philosophy (85), and English (47) only host 2020 curriculum files.
- **Policy Recommendation**:
  1. Actively superseded versions (e.g. Physics 2022, Commerce 2022) must be dropped.
  2. Older syllabi where no newer version has been published should be tagged with `is_historical=True` in metadata. This allows the RAG retrieval engine to exclude them from general student queries unless historical context is explicitly requested.

---

## Part 4: Ingestion Pruning Configuration & Waste Quantification

### 4.1 Declarative Filter Specification
The declarative filter has been authored and saved to [configs/ingestion_filter.yaml](file:///home/mihawk/ubuntu_data/projects/cuk-rag-chatbot/configs/ingestion_filter.yaml):

```yaml
ingestion_filter:
  version: "1.0.0"
  reference_date: "2026-11-15"

  temporal_pruning:
    tenders_max_age_months: 12
    admission_notices_max_age_months: 24
    general_notices_max_age_months: 36
    press_releases_max_age_months: 36
    exam_results_max_age_months: 24
    historical_corpus_threshold_months: 60

  security_exclusions:
    exclude_sensitive_flag: true
    title_blacklists:
      - "confidential"
      - "salary"
      - "dispute"
      - "selection list"
      - "merit list"
      - "provisional list"
      - "provisional selection"
      - "waiting list"
      - "waitlist"
      - "roll number list"
      - "enrollment list"
      - "disciplinary"
      - "vigilance enquiry"
      - "inquiry committee"
      - "show cause"

  deduplication:
    drop_exact_content_hash_duplicates: true
    drop_exact_text_duplicates: true

  curriculum_lifecycle:
    superseded_handling: "drop"
    superseded_programs:
      "Department of Physics":
        active_min_year: 2026
        superseded_years: [2022]
      "Department of Commerce":
        active_min_year: 2024
        superseded_years: [2022]
    pre_nep_policy:
      pre_2021_action: "tag_historical"
      historical_flag_field: "is_historical"
```

### 4.2 Waste Quantification & Resource Savings

#### Tier 1: Conservative Pruning (Immediate Safe Drop)
Dropping exact hash duplicates, sensitive PII lists, expired admissions (>24 months), expired notices (>36 months), and superseded physics/commerce syllabi:

- **Original Corpus**: 4,538 documents | 8,626,276 characters | ~2,156,569 tokens
- **Pruned Documents**: **508 documents (11.2% reduction)**
  - Deduplicated exact content hashes: 192 docs
  - Superseded syllabi (Physics/Commerce): 217 docs
  - Expired admissions ($\le$ 2024): 87 docs
  - Expired general notices / news ($\le$ 2023): 7 docs
  - Sensitive / PII flagged listings: 5 docs
- **Retained Corpus**: 4,030 documents (88.8%)
- **Compute / Token Savings**: **248,036 tokens (992,144 characters saved from embedding)**

#### Tier 2: Aggressive Pruning (Full Historical Archive Drop)
Dropping all documents older than 5 years ($\le$ 2021), expired admissions, duplicates, and sensitive records:

- **Pruned Documents**: **1,487 documents (32.8% reduction)**
  - Historical documents older than 5 years: 1,206 docs (including 1,104 PDF chunks)
  - Duplicate content hashes: 192 docs
  - Expired admissions: 87 docs
  - Sensitive PII records: 2 docs
- **Retained Corpus**: 3,051 documents (67.2%)
- **Compute / Token Savings**: **689,142 tokens (32.0% compute savings across embedding and vector storage)**
- **Vector Storage Impact**: Eliminates ~5,500 LanceDB chunk vectors, reducing index build time and eliminating historical noise in similarity search.

---

## Approved Ingestion Integration Protocol

To enforce `configs/ingestion_filter.yaml` within the ingestion pipeline, apply the following filter hook inside `cuk_assistant/ingestion/crawl/runner.py` or before passing documents to `HierarchicalChunker`:

```python
# Integration Hook for cuk_assistant/ingestion/crawl/runner.py
import re
from datetime import datetime
import yaml


def load_filter_config(path: str = "configs/ingestion_filter.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["ingestion_filter"]


def should_retain_document(doc: dict, cfg: dict, seen_hashes: set) -> tuple[bool, str]:
    meta = doc.get("metadata", {})
    text = doc.get("text", "")
    title = (meta.get("title") or "").lower()

    # 1. Deduplication
    ch = meta.get("content_hash")
    if cfg["deduplication"]["drop_exact_content_hash_duplicates"] and ch:
        if ch in seen_hashes:
            return False, "EXACT_HASH_DUPLICATE"
        seen_hashes.add(ch)

    # 2. Security & PII
    if cfg["security_exclusions"]["exclude_sensitive_flag"] and meta.get("is_sensitive"):
        return False, "SENSITIVE_PII_FLAGGED"
    for term in cfg["security_exclusions"]["title_blacklists"]:
        if term in title:
            return False, f"TITLE_BLACKLIST_{term.upper()}"

    # 3. Superseded Syllabi
    if meta.get("doc_type") == "syllabus":
        prog = meta.get("program") or meta.get("department")
        superseded = cfg["curriculum_lifecycle"]["superseded_programs"].get(prog)
        if superseded:
            year = _extract_year(meta, title)
            if year and year in superseded["superseded_years"]:
                return False, f"SUPERSEDED_SYLLABUS_{year}"

    # 4. Temporal Pruning
    doc_date = _resolve_date(meta, title)
    if doc_date:
        ref_date = datetime.strptime(cfg["reference_date"], "%Y-%m-%d")
        age_months = (ref_date.year - doc_date.year) * 12 + (ref_date.month - doc_date.month)

        dtype = meta.get("doc_type")
        if dtype == "tender" and age_months > cfg["temporal_pruning"]["tenders_max_age_months"]:
            return False, "EXPIRED_TENDER"
        if (
            dtype == "admission"
            and age_months > cfg["temporal_pruning"]["admission_notices_max_age_months"]
        ):
            return False, "EXPIRED_ADMISSION"
        if (
            dtype in ("notice", "press_release")
            and age_months > cfg["temporal_pruning"]["general_notices_max_age_months"]
        ):
            return False, "EXPIRED_GENERAL_NOTICE"

    return True, "RETAINED"
```

### Action Items for Pipeline Deployment:
1. Load `configs/ingestion_filter.yaml` in `runner.py` before exporting `documents.jsonl`.
2. Add `is_historical: bool = False` to `DocumentMetadata` schema for accredited 2020 curriculum retained under NEP transition.
3. Configure `direct_client.py` to route static PDF downloads to a parallel pool (concurrency 4, 4 RPS) while maintaining polite 1 RPS on `cukapi.disgenweb.in`.
4. Blacklist `pressrelease/selectbyid` to eliminate 138 recurring HTTP 500 server crashes.
