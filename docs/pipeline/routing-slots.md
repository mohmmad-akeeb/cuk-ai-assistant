# Routing + Slot Filling

> **Intent detection, entity extraction, and faceted disambiguation.** The `AdaptiveRouter` classifies queries and the `FacetedSlotFiller` extracts mandatory slots, generating interactive chips when slots are missing.
>
> Related: [Pipeline Overview](./overview.md) · [Guardrails](./guardrails.md) · [UI Interaction](../api-ui/ui.md)

---

## 1. Purpose

When a user asks "What is the syllabus of DBMS?", the router needs to:
1. Detect this is a syllabus intent
2. Infer DBMS → B.Tech CSE (program), but batch_year and semester are missing
3. Ask the user to select batch_year via chips, then semester via chips
4. Once all slots are filled, build a metadata filter for LanceDB retrieval

---

## 2. Routing Decision Tree

```mermaid
flowchart TD
    QUERY["User query"]
    NORMALIZE["normalize_query()<br/>Strip + collapse whitespace"]
    EXTRACT["extract_entities()<br/>Circular IDs, academic years,<br/>course codes, negations, slots"]

    GUARD{"Input guard<br/>injected?"}
    GUARD_CHECK["input_guard.validate()"]
    GUARD_RESULT{"Safe + in domain?"}
    DEFLECTED["DEFLECTED<br/>reason = deflection_message"]

    CONV["is_conversational()"]
    CONV_CHECKS["Check patterns:<br/>• GREETING_RE (hi, hello, salam)<br/>• PERSONA_RE (who are you)<br/>• GRATITUDE_RE (thanks, jazakallah)<br/>• FAREWELL_RE (bye, goodnight)<br/>• SMALLTALK_RE (how are you)"]
    SUBSTANTIVE{"Contains substantive<br/>university keywords?"}
    CONV_YES["True — conversational"]
    CONV_NO["False — requires retrieval"]

    ACADEMIC["detect_academic_intent()"]
    ACADEMIC_CHECKS["Check patterns:<br/>• SYLLABUS_RE (syllabus, curriculum)<br/>• RESULT_RE (results, marksheet)<br/>• DATESHEET_RE (datesheet)<br/>• ADMISSION_RE (admissions, cutoff)<br/>• Known course titles (dbms, os, hrm...)"]
    ACADEMIC_RESULT{"Academic intent<br/>detected?"}

    FILL["fill_slots()"]
    SLOT_CHECK{"All mandatory<br/>slots filled?"}

    FACETED["FACETED_ACADEMIC<br/>Emit slot_prompt with chips<br/>for first missing slot"]
    HYBRID_FILTER["HYBRID_RETRIEVAL<br/>with metadata_filter"]
    HYBRID_GENERAL["HYBRID_RETRIEVAL<br/>No filter, general inquiry"]

    QUERY --> NORMALIZE --> EXTRACT --> GUARD
    GUARD -->|"Yes"| GUARD_CHECK --> GUARD_RESULT
    GUARD -->|"No"| CONV
    GUARD_RESULT -->|"No"| DEFLECTED
    GUARD_RESULT -->|"Yes"| CONV
    CONV --> SUBSTANTIVE
    SUBSTANTIVE -->|"Yes"| CONV_NO
    SUBSTANTIVE -->|"No"| CONV_CHECKS
    CONV_CHECKS -->|"Match"| CONV_YES
    CONV_CHECKS -->|"No match"| CONV_NO
    CONV_YES -->|"DIRECT_CONVERSATIONAL"| OUT_CONV["Stream greeting"]
    CONV_NO --> ACADEMIC
    ACADEMIC --> ACADEMIC_CHECKS --> ACADEMIC_RESULT
    ACADEMIC_RESULT -->|"Yes"| FILL --> SLOT_CHECK
    ACADEMIC_RESULT -->|"No"| HYBRID_GENERAL
    SLOT_CHECK -->|"No"| FACETED
    SLOT_CHECK -->|"Yes"| HYBRID_FILTER

    style DEFLECTED fill:#3a1a1a,color:#fff
    style OUT_CONV fill:#3a2a3a,color:#fff
    style FACETED fill:#3a2a1a,color:#fff
    style HYBRID_FILTER fill:#1a3a1a,color:#fff
    style HYBRID_GENERAL fill:#1a2a3a,color:#fff
```

---

## 3. Intent Detection

The `detect_academic_intent()` method uses regex patterns to classify queries:

```mermaid
flowchart LR
    TEXT["User query text"]
    SYL_CHECK{"SYLLABUS_RE match?<br/>(syllabus, curriculum,<br/>course outline, units, credits)"}
    RES_CHECK{"RESULT_RE match?<br/>(results, marksheet,<br/>grade sheet, backlog)"}
    DATE_CHECK{"DATESHEET_RE match?<br/>(datesheet, exam schedule,<br/>exam timetable)"}
    ADM_CHECK{"ADMISSION_RE match?<br/>(admissions, cutoff,<br/>merit list, counselling)"}
    COURSE_CHECK{"Known course title<br/>in text?<br/>(dbms, os, hrm, etc.)"}
    NONE["None — general query"]

    SYLLABUS["SYLLABUS"]
    RESULT["RESULT"]
    DATESHEET["DATESHEET"]
    ADMISSION["ADMISSION"]

    TEXT --> SYL_CHECK
    SYL_CHECK -->|"Yes"| SYLLABUS
    SYL_CHECK -->|"No"| RES_CHECK
    RES_CHECK -->|"Yes"| RESULT
    RES_CHECK -->|"No"| DATE_CHECK
    DATE_CHECK -->|"Yes"| DATESHEET
    DATE_CHECK -->|"No"| ADM_CHECK
    ADM_CHECK -->|"Yes"| ADMISSION
    ADM_CHECK -->|"No"| COURSE_CHECK
    COURSE_CHECK -->|"Yes"| SYLLABUS
    COURSE_CHECK -->|"No"| NONE

    style SYLLABUS fill:#1a3a1a,color:#fff
    style RESULT fill:#1a2a3a,color:#fff
    style DATESHEET fill:#3a2a1a,color:#fff
    style ADMISSION fill:#3a1a2a,color:#fff
    style NONE fill:#3a1a1a,color:#fff
```

> **Note:** If a known course title (like "dbms") is found even without the word "syllabus", the intent defaults to `SYLLABUS`. This handles queries like "What is DBMS?" by inferring syllabus intent.

---

## 4. Slot Extraction

The `extract_slots()` method extracts academic slots from query text and merges with session slots:

```mermaid
flowchart TD
    QUERY["Query text"]
    SESSION["Session slots<br/>(from previous chip selections)"]

    subgraph EXTRACTION["7 extraction steps (in order)"]
        S1["1. Course title + program inference<br/>Check KNOWN_COURSE_PROGRAM_MAP<br/>'dbms' → course_title='DBMS', program='B.Tech CSE'"]
        S2["2. Program extraction<br/>_PROGRAM_PATTERNS regex<br/>B.Tech, M.Tech, MCA, MBA, BBA,<br/>B.Sc IT, M.Sc IT, BA LLB, LLM,<br/>B.Ed, M.Ed, M.A.*, M.Sc.*, Ph.D"]
        S3["3. Semester extraction<br/>_SEMESTER_RE<br/>'Sem 3', '3rd semester', 'Sem-III'<br/>→ 'Semester 3'"]
        S4["4. Batch year extraction<br/>_BATCH_EXPLICIT_RE: 'Batch 2024'<br/>_BATCH_SUFFIX_RE: '2024 batch'<br/>_FOUR_DIGIT_YEAR_RE: '2024'"]
        S5["5. Course code extraction<br/>_COURSE_CODE_RE<br/>'BT-101', 'BT-CSE-401', 'CS-101'<br/>→ uppercase, hyphenated"]
        S6["6. Exam session extraction<br/>_EXAM_SESSION_RE<br/>'Autumn 2024', 'Spring 2023'"]
        S7["7. Admission year<br/>Defaults to batch_year if found"]
    end

    MERGE["Merge session_slots (pre-existing)<br/>over query-extracted slots"]
    OUTPUT["Extracted slots dict"]

    QUERY --> S1 --> S2 --> S3 --> S4 --> S5 --> S6 --> S7
    S7 --> MERGE
    SESSION --> MERGE
    MERGE --> OUTPUT

    style EXTRACTION fill:#1a2a3a,color:#fff
```

### Course-to-program knowledge base

The `KNOWN_COURSE_PROGRAM_MAP` maps well-known course abbreviations to canonical titles and programs:

| Query contains | course_title | program |
|----------------|-------------|---------|
| `dbms`, `database management systems` | Database Management Systems | B.Tech CSE |
| `dsa`, `data structures` | Data Structures & Algorithms | B.Tech CSE |
| `os`, `operating systems` | Operating Systems | B.Tech CSE |
| `coa`, `computer organization` | Computer Organization & Architecture | B.Tech CSE |
| `toc`, `theory of computation` | Theory of Computation | B.Tech CSE |
| `corporate law`, `constitutional law` | (respective) | BA LLB |
| `financial accounting`, `marketing management` | (respective) | MBA |
| `hrm`, `human resource management` | Human Resource Management | MBA |
| `quantum mechanics`, `classical mechanics` | (respective) | M.Sc Physics |
| `organic chemistry` | Organic Chemistry | M.Sc Chemistry |

---

## 5. Mandatory Slots per Intent

```mermaid
flowchart LR
    SYL["SYLLABUS"] --> S1["program"]
    S1 --> S2["batch_year"]
    S2 --> S3["semester"]

    RES["RESULT"] --> R1["program"]
    R1 --> R2["semester"]

    DATE["DATESHEET"] --> D1["program"]
    D1 --> D2["semester"]

    ADM["ADMISSION"] --> A1["program"]
    A1 --> A2["admission_year"]

    GEN["GENERAL"] --> G1["(no mandatory slots)"]

    style SYL fill:#1a3a1a,color:#fff
    style RES fill:#1a2a3a,color:#fff
    style DATE fill:#3a2a1a,color:#fff
    style ADM fill:#3a1a2a,color:#fff
    style GEN fill:#3a2a3a,color:#fff
```

| Intent | Mandatory slots | Optional slots |
|--------|----------------|----------------|
| SYLLABUS | `program`, `batch_year`, `semester` | `course_code`, `course_title`, `credits` |
| RESULT | `program`, `semester` | `exam_session` |
| DATESHEET | `program`, `semester` | — |
| ADMISSION | `program`, `admission_year` | `stage`, `intake_capacity` |
| GENERAL | (none) | — |

---

## 6. Slot Filling Flow

```mermaid
flowchart TD
    QUERY["Query text"]
    SESSION["Session slots<br/>(accumulated from chip clicks)"]
    INTENT["detected intent<br/>(syllabus, result, etc.)"]

    DETECT["detect_academic_intent()"]
    EXTRACT["extract_slots(query, session_slots)"]
    MANDATORY["get_mandatory_slots(intent)"]
    MISSING["missing = [slot for slot in mandatory<br/>if slot not in extracted or not extracted[slot]]"]

    CHECK{"len(missing) == 0?"}
    COMPLETE["Slots complete!"]
    BUILD_FILTER["_build_metadata_filter(intent, slots)"]
    RETURN_COMPLETE["SlotFillingResult(<br/>is_complete=True,<br/>metadata_filter='doc_type == ... AND ...')"]

    INCOMPLETE["Slots incomplete"]
    PRIMARY["primary_missing = missing[0]"]
    CHIPS["_build_chip_payload(primary_missing, intent)"]
    QUICK["chip_payload.to_quick_reply_payload()"]
    RETURN_INCOMPLETE["SlotFillingResult(<br/>is_complete=False,<br/>target_slot=primary_missing,<br/>missing_slots=missing,<br/>chip_payload=chips,<br/>quick_reply_payload=quick_reply)"]

    QUERY --> DETECT --> INTENT
    QUERY --> EXTRACT
    SESSION --> EXTRACT
    INTENT --> MANDATORY
    EXTRACT --> MISSING
    MANDATORY --> MISSING
    MISSING --> CHECK
    CHECK -->|"Yes"| COMPLETE --> BUILD_FILTER --> RETURN_COMPLETE
    CHECK -->|"No"| INCOMPLETE --> PRIMARY --> CHIPS --> QUICK --> RETURN_INCOMPLETE

    style COMPLETE fill:#1a3a1a,color:#fff
    style INCOMPLETE fill:#3a2a1a,color:#fff
    style RETURN_COMPLETE fill:#1a3a1a,color:#fff
    style RETURN_INCOMPLETE fill:#3a2a1a,color:#fff
```

---

## 7. Chip Payload Generation

When slots are missing, the slot-filler builds interactive chips for the **first** missing slot:

```mermaid
flowchart TD
    MISSING["primary_missing slot"]
    CHECK_SLOT{"Which slot?"}

    PROGRAM["program chips<br/>'Which academic program are you inquiring about?'<br/>B.Tech CSE, MCA, MBA, B.Sc IT, BA LLB, M.A. English"]
    BATCH["batch_year chips<br/>'Which admission batch or regulation cohort year?'<br/>2024 (NEP), 2023, 2022, 2021, 2020"]
    SEMESTER["semester chips<br/>'Which semester syllabus do you need?'<br/>Semester 1–8"]
    EXAM_SESSION["exam_session chips<br/>'Which examination session?'<br/>Autumn 2024, Spring 2024, Autumn 2023, Spring 2023"]
    ADMISSION_YEAR["admission_year chips<br/>'Which academic admission intake year?'<br/>2025, 2024, 2023"]
    DEFAULT["Generic prompt<br/>'Please specify the {slot}:'"]

    MISSING --> CHECK_SLOT
    CHECK_SLOT -->|"program"| PROGRAM
    CHECK_SLOT -->|"batch_year"| BATCH
    CHECK_SLOT -->|"semester"| SEMESTER
    CHECK_SLOT -->|"exam_session"| EXAM_SESSION
    CHECK_SLOT -->|"admission_year"| ADMISSION_YEAR
    CHECK_SLOT -->|"other"| DEFAULT

    style PROGRAM fill:#1a2a3a,color:#fff
    style BATCH fill:#1a3a1a,color:#fff
    style SEMESTER fill:#3a2a1a,color:#fff
```

### Chip payload format

```json
{
  "type": "slot_prompt",
  "target_slot": "batch_year",
  "prompt": "Which admission batch or regulation cohort year?",
  "options": [
    {"label": "2024 (NEP)", "value": "2024", "description": null},
    {"label": "2023", "value": "2023", "description": null},
    {"label": "2022", "value": "2022", "description": null},
    {"label": "2021", "value": "2021", "description": null},
    {"label": "2020", "value": "2020", "description": null}
  ],
  "is_multi_select": false
}
```

---

## 8. Metadata Filter Construction

When all mandatory slots are filled, `_build_metadata_filter()` generates a LanceDB SQL WHERE clause:

```mermaid
flowchart TD
    SLOTS["Completed slots dict<br/>{program: 'B.Tech CSE',<br/>batch_year: '2024',<br/>semester: 'Semester 4'}"]
    INTENT["Intent: SYLLABUS"]

    CLAUSE_DOC["clause: doc_type == 'syllabus'"]
    CLAUSE_PROG["clause: program == 'B.Tech CSE'"]

    SYL_EXTRA["Syllabus-specific:<br/>batch_year == '2024'<br/>semester == 'Semester 4'<br/>course_code == 'BT-CSE-401' (if present)"]
    RES_EXTRA["Result-specific:<br/>semester == 'Semester 4'<br/>exam_session == 'Autumn 2024' (if present)"]
    DATE_EXTRA["Datesheet-specific:<br/>semester == 'Semester 4'"]
    ADM_EXTRA["Admission-specific:<br/>admission_year == '2024'"]

    JOIN["Join with ' AND '<br/>doc_type == 'syllabus' AND program == 'B.Tech CSE' AND batch_year == '2024' AND semester == 'Semester 4'"]

    SLOTS --> CLAUSE_DOC
    SLOTS --> CLAUSE_PROG
    INTENT --> SYL_EXTRA
    INTENT --> RES_EXTRA
    INTENT --> DATE_EXTRA
    INTENT --> ADM_EXTRA
    CLAUSE_DOC --> JOIN
    CLAUSE_PROG --> JOIN
    SYL_EXTRA --> JOIN
    JOIN --> OUTPUT["metadata_filter string"]

    style JOIN fill:#1a3a1a,color:#fff
```

### Filter examples by intent

| Intent | Filter clause |
|--------|-------------|
| Syllabus | `doc_type == 'syllabus' AND program == 'B.Tech CSE' AND batch_year == '2024' AND semester == 'Semester 4'` |
| Result | `doc_type == 'result' AND program == 'B.Tech CSE' AND semester == 'Semester 4'` |
| Datesheet | `doc_type == 'datesheet' AND program == 'B.Tech CSE' AND semester == 'Semester 4'` |
| Admission | `doc_type == 'admission' AND program == 'B.Tech CSE' AND admission_year == '2024'` |

---

## 9. Known Issues

### 9.1 Metadata filter column mismatch (CRITICAL)

The slot-filler builds filters against `program`, `batch_year`, `semester`, `course_code`, `exam_session`, `admission_year` as if they were top-level LanceDB columns. They are **not** — these fields live inside `metadata_json` (a JSON string column).

```mermaid
flowchart LR
    FILTER["Generated filter:<br/>program == 'B.Tech CSE' AND batch_year == '2024'"]

    subgraph LAN["LanceDB chunks table"]
        TOP["Top-level columns:<br/>doc_type ✅, school ✅, department ✅"]
        JSON["metadata_json (string):<br/>{'program': 'B.Tech CSE',<br/>'batch_year': '2024',<br/>'semester': 'Semester 4',<br/>...}"]
    end

    SANITIZE["where_filter sanitizer in hybrid_search()<br/>Checks each clause column against<br/>self._table.schema.names"]
    STRIP["Strips clauses with<br/>unknown columns"]
    RESULT["Clean filter:<br/>doc_type == 'syllabus'<br/>(only top-level column survives)"]

    FILTER --> SANITIZE
    SANITIZE -->|"program not in schema"| STRIP
    SANITIZE -->|"batch_year not in schema"| STRIP
    STRIP --> RESULT

    style STRIP fill:#3a1a1a,color:#fff
    style RESULT fill:#3a1a1a,color:#fff
```

**Impact:** Filters silently fail. The retrieval returns all chunks matching `doc_type == 'syllabus'` regardless of program/batch/semester. The user gets results from wrong batches and programs.

**Fix:** Add `program`, `batch_year`, `semester`, `course_code`, `exam_session`, `admission_year` as nullable top-level columns in `CHUNKS_ARROW_SCHEMA`, and extract them from metadata during `_chunk_record_to_row()`. This requires re-indexing.

### 9.2 Slot selection does nothing (UI bug)

When a user clicks a chip (e.g. "2024" for batch_year), the Chainlit `on_slot_selected` callback updates `active_slots` and calls `process_query()` again. However, the orchestrator's `route()` method re-evaluates from scratch — it checks the input guard, runs conversational detection, and then calls `fill_slots()` with the accumulated session slots.

The flow works correctly if session slots are properly passed through. The bug is in the UI layer where `last_query` may not be preserved correctly between chip clicks. See [ui.md](../api-ui/ui.md) for details.

### 9.3 Obvious slots still asked (missing feature)

The system asks for `program` even when the course title implies it. For example:
- "What is the syllabus of DBMS?" → DBMS is a B.Tech CSE course (known from `KNOWN_COURSE_PROGRAM_MAP`), so `program` is inferred as "B.Tech CSE". But `batch_year` and `semester` are still asked.
- However, the department is also obvious (CSE → Department of Computer Science & Engineering). The system has no logic to skip department selection since department is not a mandatory slot (it's inferred from program).

The current design correctly infers program from course title, but does not infer:
- `department` from `program` (e.g. B.Tech CSE → Department of CSE)
- `semester` from `course_code` (e.g. BT-CSE-401 → Semester 4, based on the "4" in the code)
- `batch_year` from `academic_year` in document metadata

These inferences would reduce the number of chip prompts the user sees.

---

## 10. Complete Turn Example

```
User: "What is the syllabus of DBMS?"

Step 1: detect_academic_intent("What is the syllabus of DBMS?")
  → "syllabus" keyword matches SYLLABUS_RE
  → intent = SYLLABUS

Step 2: extract_slots("What is the syllabus of DBMS?", session_slots={})
  → "dbms" found in KNOWN_COURSE_PROGRAM_MAP
  → course_title = "Database Management Systems", program = "B.Tech CSE"
  → No semester, batch_year, or course_code found

Step 3: get_mandatory_slots(SYLLABUS)
  → ["program", "batch_year", "semester"]

Step 4: missing = ["batch_year", "semester"]
  (program was inferred from course title)

Step 5: primary_missing = "batch_year"
  → Build chip payload with batch year options

Step 6: Router returns FACETED_ACADEMIC with slot_prompt event
  → UI displays chips: [2024 (NEP), 2023, 2022, 2021, 2020]

--- User clicks "2024" ---

Step 7: extract_slots("What is the syllabus of DBMS?", session_slots={batch_year: "2024"})
  → program = "B.Tech CSE" (from course map)
  → batch_year = "2024" (from session slots)
  → No semester found

Step 8: missing = ["semester"]
  → primary_missing = "semester"
  → Build chip payload with semester options

Step 9: Router returns FACETED_ACADEMIC with slot_prompt event
  → UI displays chips: [Semester 1-8]

--- User clicks "Semester 4" ---

Step 10: extract_slots("What is the syllabus of DBMS?",
           session_slots={batch_year: "2024", semester: "Semester 4"})
  → program = "B.Tech CSE"
  → batch_year = "2024"
  → semester = "Semester 4"

Step 11: missing = []
  → All slots complete!

Step 12: _build_metadata_filter(SYLLABUS, slots)
  → "doc_type == 'syllabus' AND program == 'B.Tech CSE' AND batch_year == '2024' AND semester == 'Semester 4'"

Step 13: Router returns HYBRID_RETRIEVAL with metadata_filter
  → Proceed to Step 4 (retrieval)
  → ⚠️ Filter will be silently stripped (see issue 9.1)
```

---

## 11. Key Files

| File | Responsibility |
|------|---------------|
| `agent/router.py` | `AdaptiveRouter` — routing decision engine |
| `agent/slot_filler.py` | `FacetedSlotFiller` — slot extraction + chip generation |
| `schemas/chunks.py` | `ChunkRecord` — chunk data model |
| `retrieval/subsystems/lancedb_store.py` | `LanceDBStore.hybrid_search` — where filter sanitizer |
