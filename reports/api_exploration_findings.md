# Central University of Kashmir (CUK) RAG Assistant
# Reverse-Engineering & API Exploration Report (Track 2)

**Document Identifier:** `CUK-REPORT-API-001`  
**Execution Track:** Track 2 — Angular SPA Reverse-Engineering & API Exploration  
**Status:** Completed & Ground-Truth Verified  
**Date:** 2026-11-15  
**Target Systems:**  
- Production Front-End: `https://cukashmir.ac.in` (Angular 14+ SPA)  
- Production Back-End REST API: `https://cukapi.disgenweb.in` (ASP.NET / MS SQL Server)  
**Governing Specifications:** `GEMINI.md`, `docs/desired_metadata.md`, `docs/scraping_documentation.md`, `docs/metadata_schemas.json`

---

## 1. Executive Summary & Exploration Objectives

The primary mission of Track 2 was to reverse-engineer the compiled production Angular SPA and probe the underlying REST API to discover unmapped endpoints, determine parameter filtering capabilities, and evaluate whether additional API fields can satisfy the target metadata specifications defined in `docs/desired_metadata.md` (`CUK-SPEC-META-002`).

### Key Discoveries & Breakthroughs:
1. **Full Bundle & Route De-obfuscation**:
   - Reconstructed the complete chunk topology of the Angular client, spanning the main application bundle, runtime loader, and **16 lazy-loaded chunk modules** (`139`, `143`, `193`, `199`, `247`, `306`, `384`, `592`, `623`, `707`, `716`, `738`, `785`, `833`, `873`, `943`).
   - Mapped all **22 client-side Angular routes** to their respective modules, components, and HTTP API consumers.
2. **Catalog Expansion (From 27 to 81 Endpoints)**:
   - Uncovered **54 unmapped API endpoints**, including dedicated single-record detail endpoints (`*/selectbyid`, `*/getEditDataById`, `*/*byId/:id`), administrative structure endpoints (`administrative/*`, `employeeprofile/*`), university news/press release endpoints (`pressrelease/*`, `moe/*`), and the university-wide search service (`mastersearch/getmasterdata`).
3. **`TenderNo` Metadata Breakthrough**:
   - Discovered endpoint `tender/getalltender` which exposes native CMS columns `TenderNo`, `StartDate`, `EndDate`, `UploadDate`, and `RefId`. In `docs/desired_metadata.md`, `tender_number` was previously designated as `DOCLING_PDF_EXTRACT`. This finding promotes `tender_number` to `CMS_API_DIRECT`.
4. **Server-Side Filter Behavior Verified**:
   - Proved that listing endpoints (`noticeboard/all`, `admission/all`, `examinationresult/*`) execute underlying SQL Server stored procedures that strictly type-check `DepartmentId` as `uniqueidentifier` (GUID), actively filtering records when supplied with a valid department GUID.
   - Confirmed that arbitrary filter parameters such as `year`, `session`, `batch`, `searchKeyword`, or `SearchText` are completely ignored by the listing stored procedures, proving that academic temporal filtering must be performed client-side or during downstream ingestion indexing.
5. **Universal Wildcard Omni-Search**:
   - Reverse-engineered `mastersearch/getmasterdata` (powering `/filter`), which accepts SQL LIKE patterns (`{"SearchText": "%keyword%"}`) across all major publication categories.

---

## 2. Angular SPA Client Architecture & Bundle Analysis

### 2.1 Production Bundle Decomposition
Inspection of the index HTML at `https://cukashmir.ac.in` identified the root script tags:
- `runtime.81e708c45502e351.js`: Webpack runtime and chunk loader manifest.
- `polyfills.f07fd5bb430539ca.js`: Core ES / Zone.js polyfills.
- `scripts.0e3f9c892f03bb62.js`: External global libraries (jQuery, Slick carousel, Froala editor helpers).
- `main.8c79b23023f907d7.js`: Application bootstrap, root routes, and shared providers.

The Webpack chunk mapping inside `runtime.81e708c45502e351.js` resolved the 16 lazy-loaded chunk bundles:
```javascript
r.u = e => (592 === e ? "common" : e) + "." + {
  139: "c4bea6702ccf31a9", 143: "149a5482120e6a85", 193: "670913b814aa94f3",
  199: "34795fd895acc4b1", 247: "a5e5c085166fe23e", 306: "376b7c419c22d954",
  384: "4e3e5fa660157e00", 592: "2a237c12e4bdfeae", 623: "02490edc35f85f5a",
  707: "d86bb5502458f0a4", 716: "7d0ead68e910b9bb", 738: "fa65d821c7d6fc1b",
  785: "48bd7f0f7bee37b5", 833: "404e287cd3f55a29", 873: "f4c5e0b8ab3eed3d",
  943: "331ba712722160bd"
}[e] + ".js";
```

### 2.2 Angular Route-to-Module Mapping

| Route Path | Module Name | Chunks Loaded | Functional Role |
| :--- | :--- | :--- | :--- |
| `/` & `/home` | `HomeModule` | `main` | Homepage banner widgets, quick links, statutory overview |
| `/school` | `SchoolModule` | `943` | Overview of all 9 academic schools (`schoolList`) |
| `/departmentList` | `DepartmentModule` | `247`, `592`, `785` | Multi-level departmental tree (levels 1-4: overview, syllabus, faculty) |
| `/departlist` | `DepartlistModule` | `592`, `833` | Navigation bridge for top header categories |
| `/administration` | `AdministrationModule` | `592`, `707` | University officers, administration sections |
| `/administrative-list` | `AdministrativeListModule`| `199` | Statutory bodies, executive committees, employee rosters |
| `/content` | `ContentModule` | `592`, `143` | Universal single-record detail page (`/content?type=...&id=...`) |
| `/notifications` | `ReadmoreModule` | `306`, `716` | Full listing for general notices and department notices |
| `/tenders` | `ReadmoreModule` | `306`, `716` | Full listing for procurement notices and RFPs |
| `/employment` | `ReadmoreModule` | `306`, `716` | Recruitment advertisements and CAS notices |
| `/upcoming-event` | `ReadmoreModule` | `306`, `716` | University events and academic conferences |
| `/message` | `ReadmoreModule` | `306`, `716` | Vice Chancellor and Registrar messages |
| `/filter` | `FilterModule` | `623` | Master search results page (`mastersearch/getmasterdata`) |
| `/studentzone` | `StudentzoneModule` | `247`, `592`, `873` | Student notices, date sheets, forms, syllabus links |
| `/publiczone` | `PubliczoneModule` | `247`, `592`, `193` | Public circulars, press releases, video/photo galleries |
| `/universitydoc` | `TwoPanelLayoutModule`| `384` | Statutory policies, ordinances, annual reports |
| `/universityini` | `TwoPanelLayoutModule`| `384` | University initiatives (NEP-2020 cell, DIA, Ek Bharat) |
| `/implink` | `TwoPanelLayoutModule`| `384` | Important links and student portals |
| `/event-gallery` | `ViewGalleryModule` | `306`, `592`, `139` | Photo and event media galleries |
| `/screenreaderaccess`| `ScreenreaderModule` | `738` | Accessibility statement and screen-reader assistance |
| `/**` | Fallback Component | `main` | Wildcard route fallback |

### 2.3 HTTP Client Architecture
Inside `main.8c79b23023f907d7.js`:
- Module `8398` exports the constant configuration:
  ```javascript
  const C = {
    urllist: { url: "https://cukapi.disgenweb.in/" },
    urllist1: { url: "https://cukapi.disgenweb.in/" }
  };
  ```
- Module `3526` exports the root `HttpService` class (`He`), implementing:
  - `post(body, endpoint)`: Appends `urllist.url + endpoint`, injecting headers `Content-Type: application/json`, `Accept: application/json`, and `langtype: localStorage.getItem("LangType") || "1"`.
  - `get(endpoint)`: Sends GET request to `urllist.url + endpoint`.
  - Token-authenticated variants (`postToken`, `putToken`, `getToken`) for CMS administrative panels.

---

## 3. Discovered API Endpoint Taxonomy

A total of **81 distinct REST endpoints** were extracted from the Angular production artifacts.

### 3.1 Global & Departmental Listing Endpoints

| Endpoint | Method | Typical Payload | Response Item Key Fields | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `noticeboard/all` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `VisibleToDate`, `FileUrl`, `FileName`, `DepartmentId`, `TotalRecords` | Main circulars; active `departmentId` filter. |
| `admission/all` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `VisibleToDate`, `FileUrl`, `FileName`, `DepartmentId`, `TotalRecords` | Admission selections, merit lists. |
| `tender/all` | POST | `{"langType": 1, "seen": 0, "next": 100}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `VisibleToDate`, `FileUrl`, `FileName`, `TotalRecords` | Standard tender list. |
| `tender/getalltender` | POST | `{"langType": 1}` | `TenderNo`, `StartDate`, `EndDate`, `UploadDate`, `Title`, `Description`, `RefId`, `Url`, `HttpPath`, `RowId`, `SNo`, `approved` | **Major finding**: Native `TenderNo` directly available. |
| `employments/all` | POST | `{"langType": 1, "seen": 0, "next": 100}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `VisibleToDate`, `FileUrl`, `FileName`, `TotalRecords` | Employment circulars. |
| `employments/allemploymentsforwebsite` | POST | `{"langType": 1}` | Same as `employments/all` | Unpaginated full list used by `StudentzoneModule`. |
| `examinationresult/ExaminationResultListForWebSite` | POST | `{"langType": 1, "departmentId": ""}` | `RowId`, `DepartmentName`, `DepartmentId`, `CourseId`, `CourseName`, `Result_title`, `Result_Description`, `filename`, `HttpPath`, `UploadDate` | Regular exam gazettes. |
| `scholarresults/ScholarExaminationResultListForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `RowId`, `DepartmentName`, `DepartmentId`, `UploadDate`, `filename`, `HttpPath`, `Result_title`, `Result_Description` | Ph.D. / Research results. |
| `examdatesheet/ExamDateSheetList` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `FileUrl`, `FileName`, `TotalRecords` | Examination timetables. |
| `examnotification/getAllNotificationForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `FileUrl`, `FileName`, `TotalRecords` | Examination circulars. |
| `itandservices/ItAndServicesNotificationListForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100, "departmentId": ""}` | `Id`, `RecordId`, `Title`, `ContentType`, `PublishedOn`, `VisibleFromDate`, `FileUrl`, `FileName`, `TotalRecords` | IT circulars and notices. |
| `whatnew/getAllWhatNewForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100}` | `Id`, `Title`, `ContentType`, `CreatedOn`, `VisibleFromDate`, `FileUrl`, `TotalRecords` | University news feed. |
| `pressrelease/getAllPressReleasesForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100}` | `Id`, `uniqueId`, `Name`, `ContentType`, `StartDate`, `EndDate`, `Url`, `HttpPath`, `DepartmentId`, `UserName`, `TotalRecords` | Official press releases. |
| `moe/getAllPressReleasesForWebSite` | POST | `{"langType": 1, "seen": 0, "next": 100}` | `Id`, `Name`, `ContentType`, `StartDate`, `EndDate`, `HttpPath`, `TotalRecords` | Ministry of Education updates. |
| `event/getall` | POST | `{"langType": 1, "TypeId": 4, "ContentType": "EventTitle"}` | `EventId`, `EventTitle`, `StartDate`, `EndDate`, `Venue`, `HttpPath` | All university events. |
| `event/getallupcomingeventsforwebsite` | POST | `{"langType": 1, "TypeId": 4, "ContentType": "EventTitle"}` | `EventId`, `EventTitle`, `StartDate`, `EndDate`, `Venue`, `HttpPath` | Upcoming events calendar. |

### 3.2 Single-Record Detail Endpoints (`/content` Route Consumers)
Discovered in `143.149a5482120e6a85.js`. These endpoints allow fetching complete rich HTML or document properties for a specific record without traversing full lists:

| Component Method | Target REST Endpoint | Parameter Signature | Notes |
| :--- | :--- | :--- | :--- |
| `getDateSheets(id)` | `examdatesheet/ExamDateSheetId/{id}` | POST `{}` with path ID | Fetches single date sheet record |
| `getExamResult(id)` | `examinationresult/ExaminationResultbyId/{id}` | POST `{"langType": 1}` with path ID | Fetches single exam result record |
| `getStudentNotice(id)`| `examnotification/ExamNotificationbyId/{id}` | POST `{"langType": 1}` with path ID | Fetches single exam notification |
| `getGeneralNotice(id)`| `noticeboard/selectbyid` | POST `{"langType": 1, "Id": id}` | Fetches single notice by GUID |
| `getPressRelease(id)` | `pressrelease/selectbyid` | POST `{"langType": 1, "Id": id}` | Fetches single press release |
| `getAdmission(id)` | `admission/getadmissionbyid` | POST `{"langType": 1, "Id": id}` | Fetches single admission notification |
| `getTenders(id)` | `tender/getbyidforwebsite` | POST `{"langType": 1, "RowId154": id}` | Fetches single tender by RowId |
| `getWhatNew(id)` | `whatnew/selectbyid` | POST `{"langType": 1, "RowId154": id}` | Fetches single what's new item |
| `getMoes(id)` | `moe/selectbyid` | POST `{"langType": 1, "Id": id}` | Fetches single MOE release |
| `getMainProgramms(id)`| `mainprogramms/selectbyid` | POST `{"langType": 1, "Id": id}` | Fetches degree program description |
| `getEmployment(id)` | `employments/getEditDataById` | POST `{"Id": id}` | Fetches employment posting details |
| `getAllMessages(id)` | `messages/getEditDataById` | POST `{"Id": id}` | Fetches VC / Registrar message details |
| `getUpcomingEvent(id)`| `event/getbyid` | POST `{"Id": id}` | Fetches event details |
| `getAdditionalCard(id)`| `additionalcard/getEditDataById`| POST `{"Id": id}` | Fetches homepage card details |
| `getQuickLink(id)` | `publichomequicklinks/getEditDataById`| POST `{"Id": id}` | Fetches quick link item details |

### 3.3 Search & Navigation Endpoints

| Endpoint | Method | Payload Structure | Discovery Source | Role & Capability |
| :--- | :--- | :--- | :--- | :--- |
| `mastersearch/getmasterdata` | POST | `{"SearchText": "%<query>%"}` | `623.02490edc35f85f5a.js` | University-wide omni-search across all notices, releases, and files. |
| `school/schoolList` | GET | None | `943.331ba712722160bd.js` | Top-level school list (9 schools). |
| `school/getSchoolBreadCrumb` | POST | `{"SchoolMasterId": "<GUID>"}`| `785.48bd7f0f7bee37b5.js` | Returns clean school breadcrumb record. |
| `department/getMappedDepartmentListBySchoolMasterId` | POST | `{"SchoolMasterId": "<GUID>"}`| `785.48bd7f0f7bee37b5.js` | Lists departments mapped under a school. |
| `department/departmentListById` | POST | `{"Id": "<GUID>"}` | `785.48bd7f0f7bee37b5.js` | Menus & submenus for departments (syllabus, BOS, courses). |
| `department/getbreadcum` | POST | `{"Id": "<GUID>"}` | `785.48bd7f0f7bee37b5.js` | Departmental breadcrumb path. |
| `administrative/administrativeListById` | POST | `{"Id": "<GUID>", "LangType": 1}` | `199.34795fd895acc4b1.js` | Menus & submenus for statutory administrative bodies. |
| `administrative/getbreadcum` | POST | `{"Id": "<GUID>", "LangType": 1}` | `199.34795fd895acc4b1.js` | Administrative section breadcrumb. |
| `employeeprofile/getallforwebsite` | POST | `{"langType": 1, "SectionId": "<GUID>"}` | `199`, `707` | Non-faculty administrative staff directory by section. |

---

## 4. API Payload & Filter Probe Findings

### 4.1 Filter Capabilities on Listing Endpoints

We systematically tested candidate filter parameters against `noticeboard/all`, `admission/all`, and `examinationresult/ExaminationResultListForWebSite`:

```
Tested Payload Parameters:
├── year / Year / session / batch / academic_year
├── searchKeyword / SearchText
└── departmentId / DepartmentId / SectionId
```

#### Empirical Observations:
1. **`departmentId` is Actively Enforced**:
   - Sending `{"departmentId": "some_non_guid"}` immediately produced an HTTP 500:  
     `"Error converting data type nvarchar to uniqueidentifier."`  
     This confirms that the backend SQL query directly parses `departmentId` as an explicit `uniqueidentifier` filter parameter.
   - Sending `{"departmentId": "25512ADA-2CAF-40D5-998B-B73F9D4619EA"}` (Department of Information Technology) against `noticeboard/all` returned `0` records (`TotalRecords: 0`), whereas the unfiltered call returned all 9 university-wide notices.
   - Sending `{"departmentId": "25512ADA-2CAF-40D5-998B-B73F9D4619EA"}` against `examinationresult/ExaminationResultListForWebSite` filtered results strictly to that department.
2. **Temporal & Keyword Filters are Inactive on Stored Procedures**:
   - Sending `{"year": 2024}`, `{"batch": 2022}`, `{"session": "Autumn"}`, or `{"searchKeyword": "examination"}` to `noticeboard/all` returned HTTP 200 with the exact same record set (`TotalRecords: 9`) and identical first record.
   - *Conclusion*: The backend stored procedures for listing endpoints do **not** provide SQL-level temporal filtering or keyword indexing.

### 4.2 Omni-Search Evaluation (`mastersearch/getmasterdata`)

The endpoint `mastersearch/getmasterdata` was probed to evaluate its utility as a potential alternative to full-site crawling:
- **Query Signature**: `{"SearchText": "%<term>%"}`.
- **Probe Results**:
  - `SearchText: "%CSE%"` $\rightarrow$ Returned 10 records in ~3 seconds (`NotificationType`, `Title`, `HttpPath`, `ContentType`, `CreatedDate`, `RecordId`).
  - Broad searches (`"%syllabus%"`, `"%examination%"`, `"%admission%"`) consistently timed out at 15–20 seconds on the backend.
- **Analysis**:
  The backend executes an unindexed wildcard SQL `LIKE '%term%'` scan across large text columns. While functional for narrow prefix lookups on the front-end, it is too high-latency and prone to timeouts to serve as a reliable ingestion pipeline source compared to structured BFS tree crawling.

---

## 5. Field Attribution & Gap Matrix Alignment

Below is the definitive matrix mapping the targets specified in `docs/desired_metadata.md` against our discovered API fields and reverse-engineered schemas.

### 5.1 Universal Base Metadata Matrix (`UniversalDocMetadata`)

| Target Field | Type | Desired Target State | Discovered API Field / Source | New Attribution Tier | Impact & Extraction Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `doc_id` | `str` | 24-char hex SHA-256 | `sha256(endpoint::(RecordId\|RowId\|Id)::chunk)` | `HYBRID_DERIVED` | Fully deterministic across all 81 endpoints. |
| `doc_type` | `str` | Polymorphic discriminator | Mapped from endpoint name / `NotificationType` | `HYBRID_DERIVED` | Clean mapping table established. |
| `title` | `str` | Required title | `Title` / `Result_title` / `EventTitle` / `Name` | `CMS_API_DIRECT` | Directly present in 100% of listing/detail endpoints. |
| `normalized_title` | `str` | Lowercase ASCII, noise-stripped | Derived from `title` | `HYBRID_DERIVED` | Computed in pipeline normalizer. |
| `source_url` | `str` | Download URL | `FileUrl` / `HttpPath` / `Url` | `CMS_API_DIRECT` | Direct attachment URL populated. |
| `page_url` | `str` | Front-end SPA hash route | Synthesized from route table + record ID | `CMS_API_DIRECT` | Reconstructed deterministically. |
| `school` | `str` | Human-readable school name | `SchoolName` from `school/schoolList` | `CMS_API_DIRECT` | Inherited via BFS site hierarchy. |
| `school_master_id` | `str` | School GUID | `SchoolMasterId` | `CMS_API_DIRECT` | Direct GUID from `schoolList` / `getSchoolBreadCrumb`. |
| `department` | `str` | Human-readable dept name | `DepartmentName` | `CMS_API_DIRECT` | Direct from `departmentListById` or `DepartmentName`. |
| `department_master_id`| `str` | Dept Master GUID | `DepartmentMasterId` | `CMS_API_DIRECT` | Direct from `getMappedDepartmentListBySchoolMasterId`. |
| `node_path` | `list[str]` | Breadcrumb list | Captured during recursive tree walk | `CMS_API_DIRECT` | Seeded via Phase 1 node crawler. |
| `published_date` | `str` | ISO-8601 date (`YYYY-MM-DD`) | `PublishedOn` / `UploadDate` / `CreatedDate` | `CMS_API_DIRECT` | Direct CMS ISO-8601 server timestamp. |
| `academic_year` | `str` | Session string (`"2023-2024"`) | Extracted via regex from `title` / text | `HYBRID_DERIVED` | Stored procedure does not supply dedicated column. |
| `language` | `str` | `"en"`, `"ur"`, `"hi"` | `LangType` / `langType` (1 $\rightarrow$ `"en"`, 2 $\rightarrow$ `"ur"`) | `CMS_API_DIRECT` | Direct integer enum translation. |
| `is_university_wide` | `bool` | Boolean flag | Evaluated if `DepartmentId` is null/empty | `HYBRID_DERIVED` | High reliability based on API payload presence. |
| `audience` | `str` | Readership category | Classified from endpoint & section | `HYBRID_DERIVED` | Inferred from endpoint taxonomy. |
| `reference_number` | `str` | Official reference ID | PDF text regex (`CUK/Acad/...`) | `DOCLING_PDF_EXTRACT` | Unpopulated in CMS; requires Tier 2 OCR. |
| `signatory` | `str` | Issuing authority | Extracted from PDF signature block | `DOCLING_PDF_EXTRACT` | CMS records only store internal `UserName` (`"Super Admin"`). |
| `is_sensitive` | `bool` | Student PII flag | Regex on title (`selection list`, `merit list`) | `HYBRID_DERIVED` | Deterministic guardrail rule. |
| `content_hash` | `str` | SHA-256 of text | SHA-256 of extracted markdown | `HYBRID_DERIVED` | Computed post-parsing. |
| `etag` / `last_modified`| `str` | HTTP cache headers | HTTP response headers | `CMS_API_DIRECT` | Captured by `CachedClient`. |

---

### 5.2 Polymorphic Domain Field Alignment

#### 1. Syllabus Domain (`SyllabusDocMetadata`)
- `program`: Available in Tier 1 via Department Menu title (`"B. Tech. CSE"`, `"M. Tech. CSE"` from `departmentListById`). Promoted to `CMS_API_DIRECT` when discovered in curriculum nodes.
- `batch_year`: **Not present in CMS API**. Must be parsed from PDF header (`DOCLING_PDF_EXTRACT`) or menu leaf title (e.g. `B2_8` $\rightarrow$ 2020).
- `semester`: Present in menu leaf titles (e.g. `"Semester 8 Syllabus"`). Promoted to `HYBRID_DERIVED`.
- `course_code` & `course_title` & `credits`: **Not present in CMS API**. Must be extracted via Docling TableFormer from course matrices (`DOCLING_PDF_EXTRACT`).
- `regulation_year`: Inferred from BOS resolution text (`DOCLING_PDF_EXTRACT`).

#### 2. Examination Result Domain (`ResultDocMetadata`)
- `exam_session`: Parsed from `Result_title` regex (e.g. `[SP (3) -2026]` $\rightarrow$ `"Special Examinations 2026"`). Tier: `HYBRID_DERIVED`.
- `program`: Inherited from `DepartmentName` or parsed from title. Tier: `HYBRID_DERIVED`.
- `batch_year`: **Not present in CMS API**. Parsed from gazette banner (`DOCLING_PDF_EXTRACT`).
- `semester`: Derived from title keywords or PDF header (`HYBRID_DERIVED`).
- `result_type`: Classified from title (`"Special Examinations"`, `"Backlog"`, `"Re-evaluation"`). Tier: `HYBRID_DERIVED`.
- `notification_number`: Extracted directly from `Result_title` regex (e.g. `r"Result Notification No\.\s*(\d+)"` $\rightarrow$ `"2431"`). Promoted to `HYBRID_DERIVED`.
- `declaration_date`: Reconciled from CMS `UploadDate` / `CreatedOn` (`CMS_API_DIRECT`).

#### 3. Admission Domain (`AdmissionDocMetadata`)
- `admission_year`: Extracted from `Title` (e.g. `"...Programme-2026"` $\rightarrow$ `2026`). Tier: `HYBRID_DERIVED`.
- `program`: Extracted from `Title` (e.g. `"M.Ed (Working Professional Programme)"`). Tier: `HYBRID_DERIVED`.
- `stage`: Classified from title keywords (`"Provisional Selection list-III"` $\rightarrow$ `"merit_list"`). Tier: `HYBRID_DERIVED`.
- `counseling_date`: **Not in CMS API**. Must be parsed from PDF tables (`DOCLING_PDF_EXTRACT`).
- `intake_capacity`: **Not in CMS API**. Must be parsed from seat matrix tables (`DOCLING_PDF_EXTRACT`).

#### 4. Notice Domain (`NoticeDocMetadata`)
- `issuing_office`: Derived from `DepartmentId` mapping or PDF header (`HYBRID_DERIVED`).
- `subject_tags`: Extracted from title keywords (`HYBRID_DERIVED`).
- `expiry_date`: **Available directly from CMS API `VisibleToDate`** (`CMS_API_DIRECT`).
- `is_urgent`: Keyword regex on title (`HYBRID_DERIVED`).

#### 5. Tender Domain (`TenderDocMetadata`) — *Major Promotion*
- `tender_number`: **Directly available as `TenderNo` from `tender/getalltender`** (e.g. `"2026_CUoK_933867_1"`). Promoted from `DOCLING_PDF_EXTRACT` to `CMS_API_DIRECT`!
- `nit_date`: Available directly as `StartDate` / `UploadDate` (`CMS_API_DIRECT`).
- `closing_date`: Available directly as `EndDate` (`CMS_API_DIRECT`).
- `emd_amount`: **Not in CMS API**. Must be parsed from tender schedule table (`DOCLING_PDF_EXTRACT`).

#### 6. Faculty & Employee Directory Domain (`FacultyDocMetadata`)
- `designation`: Available directly from `Designation` in `faculty/getallforwebsite` (`CMS_API_DIRECT`).
- `email`: Available directly from `EmailId` (`CMS_API_DIRECT`).
- `department_id`: Direct GUID from `DepartmentId` (`CMS_API_DIRECT`).
- `qualifications` & `research_areas`: Parsed from HTML `Details` (`HYBRID_DERIVED`).
- Non-faculty staff directory: Supported via newly discovered `employeeprofile/getallforwebsite`.

---

## 6. Actionable Implementation Recommendations

Based on these verified findings, the following concrete adjustments should be integrated into our scraping and ingestion modules:

1. **Adopt `tender/getalltender` in `crawl_pipeline` / `DirectApiClient`**:
   - Add `async def all_tenders(self)` calling `tender/getalltender` to capture `TenderNo`, `StartDate`, and `EndDate` directly, relieving downstream Docling parsing of tender number discovery.
2. **Support Single-Item Fallback via `/selectbyid` Endpoints**:
   - For incremental updates or document validation, add helper methods in `DirectApiClient` for `noticeboard/selectbyid`, `admission/getadmissionbyid`, `whatnew/selectbyid`, and `mainprogramms/selectbyid`.
3. **Formalize Client-Side Temporal Filtering**:
   - Since the backend SQL stored procedures do not honor `year` or `batch` parameters, `cuk_assistant.ingestion.normalize` must execute deterministic regex extractors (`r"\b20\d{2}\b"`, `r"Batch\s*(\d{4})"`) over `title` and PDF text to guarantee **Batch Isolation (FR-3.3)** in LanceDB.
4. **Scrape Administrative Directory (`AdministrativeListModule`)**:
   - Integrate `administrative/administrativeListById` and `employeeprofile/getallforwebsite` into the Phase 1 site tree crawler to capture statutory committee documents and university administrative officers.
5. **Deprecate `mastersearch/getmasterdata` for Batch Crawling**:
   - Do not rely on `mastersearch/getmasterdata` for scraping due to frequent SQL timeouts on broad queries; retain deterministic BFS tree crawling as the primary ingestion channel.

---
*Report generated and validated for CUK RAG Assistant Track 2.*
