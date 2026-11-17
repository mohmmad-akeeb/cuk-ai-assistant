"""Unit tests for crawler and ingestion alignment with CUK-SPEC-META-002 and CUK-DOC-SPA-001."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cuk_assistant.ingestion.crawl.direct_client import (
    DirectApiClient,
    _sanitize_guid,
    _unpack_list,
)
from cuk_assistant.ingestion.crawl.metadata_builder import (
    _doc_id,
    build_metadata,
)
from cuk_assistant.ingestion.crawl.node_crawler import (
    _KNOWN_ROUTES,
    _UNMAPPED_ROUTES,
    SiteNode,
    _fetch_node_content,
    _parse_angular_route,
    _resolve_content_endpoint_and_payload,
)
from cuk_assistant.ingestion.crawl.runner import (
    _GLOBAL_LIST_ENDPOINTS,
    _fetch_content_detail_fallback,
)

# ---------------------------------------------------------------------------
# DirectApiClient Tests
# ---------------------------------------------------------------------------


class TestDirectApiClientAlignment:
    def test_guid_sanitization(self) -> None:
        valid_guid = "25512ADA-1234-4567-8901-123456789ABC"
        assert _sanitize_guid(valid_guid) == valid_guid
        assert _sanitize_guid("non_guid_string") == ""
        assert _sanitize_guid("") == ""
        assert _sanitize_guid(None) == ""
        assert _sanitize_guid("12345") == ""

    def test_unpack_nested_lists(self) -> None:
        raw_nested = [[{"TenderNo": "NIT-01", "Title": "Tender 1"}]]
        unpacked = _unpack_list(raw_nested)
        assert len(unpacked) == 1
        assert unpacked[0]["TenderNo"] == "NIT-01"

        flat = [{"a": 1}, {"b": 2}]
        assert _unpack_list(flat) == flat
        assert _unpack_list([]) == []
        assert _unpack_list("not a list") == []

    @pytest.mark.asyncio
    async def test_all_tenders_endpoint(self) -> None:
        mock_cached = MagicMock()
        client = DirectApiClient(mock_cached)
        client._post = AsyncMock(return_value=[[{"TenderNo": "NIT-01", "StartDate": "2026-01-01"}]])

        res = await client.all_tenders()
        client._post.assert_awaited_once_with("tender/getalltender", {"langType": 1})
        assert len(res) == 1
        assert res[0]["TenderNo"] == "NIT-01"

    @pytest.mark.asyncio
    async def test_press_releases_endpoints(self) -> None:
        mock_cached = MagicMock()
        client = DirectApiClient(mock_cached)
        client._post = AsyncMock(return_value=[{"Id": "PR1", "Name": "Press Release 1"}])

        res_pr = await client.press_releases(seen=0, next_n=50)
        client._post.assert_awaited_with(
            "pressrelease/getAllPressReleasesForWebSite",
            {"langType": 1, "seen": 0, "next": 50},
        )
        assert len(res_pr) == 1

        res_moe = await client.moe_press_releases(seen=10, next_n=20)
        client._post.assert_awaited_with(
            "moe/getAllPressReleasesForWebSite",
            {"langType": 1, "seen": 10, "next": 20},
        )
        assert len(res_moe) == 1

    @pytest.mark.asyncio
    async def test_administrative_menu_and_employee_profiles(self) -> None:
        mock_cached = MagicMock()
        client = DirectApiClient(mock_cached)
        client._post = AsyncMock(return_value=[{"Id": "ADM1", "Title": "Executive Council"}])

        res_admin = await client.administrative_menu("SEC-123")
        client._post.assert_awaited_with(
            "administrative/administrativeListById",
            {"Id": "SEC-123", "LangType": 1},
        )
        assert len(res_admin) == 1

        res_emp = await client.employee_profiles("SEC-123")
        client._post.assert_awaited_with(
            "employeeprofile/getallforwebsite",
            {"langType": 1, "SectionId": "SEC-123"},
        )
        assert len(res_emp) == 1

    @pytest.mark.asyncio
    async def test_paged_list_sanitizes_department_id(self) -> None:
        mock_cached = MagicMock()
        client = DirectApiClient(mock_cached)
        client._post = AsyncMock(return_value=[])

        # Non-GUID string should be stripped to ""
        await client.paged_list("noticeboard/all", department_id="invalid-guid")
        client._post.assert_awaited_with(
            "noticeboard/all",
            {"langType": 1, "DepartmentId": "", "seen": 0, "next": 100},
        )

        # Valid GUID should be preserved
        valid_guid = "7022529F-5494-4B1E-9A76-EB211C56019A"
        await client.paged_list("noticeboard/all", department_id=valid_guid)
        client._post.assert_awaited_with(
            "noticeboard/all",
            {"langType": 1, "DepartmentId": valid_guid, "seen": 0, "next": 100},
        )


# ---------------------------------------------------------------------------
# NodeCrawler Tests
# ---------------------------------------------------------------------------


class TestNodeCrawlerAlignment:
    def test_routes_manifest(self) -> None:
        expected_known = {
            "content",
            "notifications",
            "message",
            "implink",
            "universitydoc",
            "universityini",
            "tenders",
            "employment",
            "upcoming-event",
        }
        for r in expected_known:
            assert r in _KNOWN_ROUTES, f"Route {r} must be in _KNOWN_ROUTES"
            assert r not in _UNMAPPED_ROUTES, f"Route {r} must NOT be in _UNMAPPED_ROUTES"

    def test_parse_angular_route_with_query_params(self) -> None:
        route, id_val, menu_id = _parse_angular_route(
            "https://www.cukashmir.ac.in/#/content?type=notice&id=ABC-123"
        )
        assert route == "content"
        assert id_val == "ABC-123"

        route, id_val, menu_id = _parse_angular_route(
            "https://www.cukashmir.ac.in/#/administrative-list;id=ADM-456"
        )
        assert route == "administrative-list"
        assert id_val == "ADM-456"

    def test_resolve_content_endpoint_and_payload(self) -> None:
        ep, payload = _resolve_content_endpoint_and_payload("notice", "GUID-1")
        assert ep == "noticeboard/selectbyid"
        assert payload == {"langType": 1, "Id": "GUID-1"}

        ep, payload = _resolve_content_endpoint_and_payload("tender", "GUID-2")
        assert ep == "tender/getbyidforwebsite"
        assert payload == {"langType": 1, "RowId154": "GUID-2"}

        ep, payload = _resolve_content_endpoint_and_payload("admission", "GUID-3")
        assert ep == "admission/getadmissionbyid"
        assert payload == {"langType": 1, "Id": "GUID-3"}

        ep, payload = _resolve_content_endpoint_and_payload("whatnew", "GUID-4")
        assert ep == "whatnew/selectbyid"
        assert payload == {"langType": 1, "RowId154": "GUID-4"}

    @pytest.mark.asyncio
    async def test_fetch_node_content_administrative_list(self) -> None:
        node = SiteNode(
            node_id="node_admin_1",
            route_name="administrative-list",
            id="SEC_99",
            menu_id="",
            parent_node_id="",
            breadcrumb=["Administration", "Committees"],
            school_master_id="",
            school_name="",
            department_master_id="",
            department_name="",
            source="nav-tree",
            status="pending",
            http_status=0,
            angular_url="https://www.cukashmir.ac.in/#/administrative-list;id=SEC_99",
            api_endpoint="",
            request_payload="",
        )
        mock_api = MagicMock()
        mock_api.administrative_menu = AsyncMock(return_value=[{"Title": "Committee"}])
        mock_api.employee_profiles = AsyncMock(return_value=[{"Name": "Staff Member"}])

        await _fetch_node_content(node, mock_api)

        assert node.status == "fetched"
        assert node.api_endpoint == "administrative/administrativeListById"
        assert len(node.content_records) == 2
        mock_api.administrative_menu.assert_awaited_once_with("SEC_99")
        mock_api.employee_profiles.assert_awaited_once_with("SEC_99")

    @pytest.mark.asyncio
    async def test_fetch_node_content_content_route(self) -> None:
        node = SiteNode(
            node_id="node_content_1",
            route_name="content",
            id="NOTICE_GUID",
            menu_id="",
            parent_node_id="",
            breadcrumb=["Notices"],
            school_master_id="",
            school_name="",
            department_master_id="",
            department_name="",
            source="html-link",
            status="pending",
            http_status=0,
            angular_url="https://www.cukashmir.ac.in/#/content?type=notice&id=NOTICE_GUID",
            api_endpoint="",
            request_payload="",
        )
        mock_api = MagicMock()
        mock_api._post = AsyncMock(return_value=[{"Title": "Important Notice Detail"}])

        await _fetch_node_content(node, mock_api)

        assert node.status == "fetched"
        assert node.api_endpoint == "noticeboard/selectbyid"
        assert len(node.content_records) == 1
        mock_api._post.assert_awaited_once_with(
            "noticeboard/selectbyid", {"langType": 1, "Id": "NOTICE_GUID"}
        )


# ---------------------------------------------------------------------------
# Runner Tests
# ---------------------------------------------------------------------------


class TestRunnerAlignment:
    def test_global_list_endpoints_configured(self) -> None:
        eps = [ep for ep, _ in _GLOBAL_LIST_ENDPOINTS]
        assert "tender/getalltender" in eps
        assert "tender/all" not in eps
        assert "pressrelease/getAllPressReleasesForWebSite" in eps
        assert "moe/getAllPressReleasesForWebSite" in eps

    @pytest.mark.asyncio
    async def test_single_item_detail_fallback(self) -> None:
        mock_api = MagicMock()
        mock_api._post = AsyncMock(
            return_value=[
                {
                    "Details": "<p>Full rich content</p>",
                    "FileUrl": "https://cuk.ac.in/attachment.pdf",
                }
            ]
        )

        # Row with /content URL
        row = {
            "Id": "GUID-X",
            "Url": "https://www.cukashmir.ac.in/#/content?type=notice&id=GUID-X",
        }
        detail = await _fetch_content_detail_fallback(mock_api, row, "noticeboard/all")
        assert detail is not None
        assert detail["FileUrl"] == "https://cuk.ac.in/attachment.pdf"
        mock_api._post.assert_awaited_with(
            "noticeboard/selectbyid", {"langType": 1, "Id": "GUID-X"}
        )


# ---------------------------------------------------------------------------
# MetadataBuilder Tests
# ---------------------------------------------------------------------------


class TestMetadataBuilderAlignment:
    def test_canonical_universal_fields_present(self) -> None:
        meta = build_metadata(
            "noticeboard/all",
            {
                "Id": "NOTICE_1",
                "Title": "Winter Vacation Circular 2026.pdf",
                "LangType": 1,
                "DepartmentId": "",
                "PublishedOn": "2026-11-15T10:00:00",
                "VisibleToDate": "2026-12-31",
            },
            section="Administration",
            school_name="School of Engineering",
            school_master_id="SCH_ENG",
            department_name="CSE",
            department_master_id="DEPT_CSE",
            node_path=["Home", "Notices"],
        )

        # UniversalDocMetadata canonical fields
        assert meta["doc_id"] == _doc_id("noticeboard/all", "NOTICE_1")
        assert meta["doc_type"] == "notice"
        assert meta["title"] == "Winter Vacation Circular 2026.pdf"
        assert meta["normalized_title"] == "winter vacation circular 2026"
        assert meta["school"] == "School of Engineering"
        assert meta["school_master_id"] == "SCH_ENG"
        assert meta["department"] == "CSE"
        assert meta["department_master_id"] == "DEPT_CSE"
        assert meta["published_date"] == "2026-11-15"
        assert meta["academic_year"] == "2026"
        assert meta["language"] == "en"
        assert meta["is_university_wide"] is True
        assert meta["audience"] in ("students", "faculty", "staff", "public")
        assert meta["is_sensitive"] is False
        assert "content_hash" in meta
        assert "page_url" in meta

    def test_tender_polymorphic_hints(self) -> None:
        record = {
            "Id": "TND_1",
            "TenderNo": "CUK/NIT/2026/05",
            "Title": "Notice Inviting Tender for IT Equipment",
            "StartDate": "2026-10-01",
            "EndDate": "2026-11-01",
            "LangType": 1,
        }
        meta = build_metadata("tender/getalltender", record)
        assert meta["doc_type"] == "tender"
        assert meta["tender_number"] == "CUK/NIT/2026/05"
        assert meta["nit_date"] == "2026-10-01"
        assert meta["closing_date"] == "2026-11-01"

    def test_result_polymorphic_hints(self) -> None:
        record = {
            "RowId": 101,
            "Result_title": "Result Notification No. 2428 for B.Tech CSE Autumn 2024 (Re-evaluation)",
            "UploadDate": "2025-01-15",
            "LangType": 1,
        }
        meta = build_metadata("examinationresult/ExaminationResultListForWebSite", record)
        assert meta["doc_type"] == "result"
        assert meta["notification_number"] == "2428"
        assert meta["exam_session"] == "Autumn 2024"
        assert meta["result_type"] == "re_evaluation"
        assert meta["declaration_date"] == "2025-01-15"

    def test_notice_polymorphic_hints(self) -> None:
        record = {
            "Id": "N1",
            "Title": "URGENT Notice: Fee Submission Deadline",
            "VisibleToDate": "2026-11-30",
            "LangType": 1,
        }
        meta = build_metadata("noticeboard/all", record, department_name="Finance Department")
        assert meta["doc_type"] == "notice"
        assert meta["expiry_date"] == "2026-11-30"
        assert meta["issuing_office"] == "Finance Department"
        assert meta["is_urgent"] is True

    def test_faculty_polymorphic_hints(self) -> None:
        record = {
            "Id": "FAC_1",
            "Title": "Dr. Alice",
            "Designation": "Associate Professor",
            "EmailId": "alice@cukashmir.ac.in",
            "DepartmentId": "DEPT_CS",
        }
        meta = build_metadata("faculty/getallforwebsite", record)
        assert meta["doc_type"] == "faculty"
        assert meta["designation"] == "Associate Professor"
        assert meta["email"] == "alice@cukashmir.ac.in"


# ---------------------------------------------------------------------------
# PDF Extractor Alignment Tests
# ---------------------------------------------------------------------------


class TestPdfExtractorAlignment:
    @pytest.mark.asyncio
    async def test_10_page_pdf_produces_single_document(self, tmp_path) -> None:
        """Verify that a 10-page PDF produces exactly 1 document with page_count=10 and unified text."""
        import fitz

        from cuk_assistant.ingestion.crawl.pdf_extractor import extract_pdf

        doc = fitz.open()
        for i in range(10):
            page = doc.new_page()
            page.insert_text((50, 50), f"Content on page {i + 1} of syllabus.")
        pdf_bytes = doc.tobytes()
        doc.close()

        mock_client = MagicMock()
        mock_head_resp = MagicMock()
        mock_head_resp.headers = {"content-length": str(len(pdf_bytes))}
        mock_client.head = AsyncMock(return_value=mock_head_resp)

        mock_get_resp = MagicMock()
        mock_get_resp.status = 200
        mock_get_resp.body = pdf_bytes
        mock_client.get = AsyncMock(return_value=mock_get_resp)

        mock_settings = MagicMock()
        mock_settings.max_pdf_bytes = 50_000_000
        mock_settings.project_root = tmp_path

        base_meta = {
            "title": "Syllabus 2026",
            "file_name": "syllabus.pdf",
            "is_sensitive": False,
            "record_id": "SYL_100",
            "raw_api_endpoint": "department/departmentListById",
        }

        docs = await extract_pdf(
            "https://cukapi.disgenweb.in/p/upload/syllabus.pdf",
            base_meta,
            mock_client,
            mock_settings,
        )

        assert len(docs) == 1
        result = docs[0]
        meta = result["metadata"]
        text = result["text"]

        assert meta["page_count"] == 10
        assert meta["page_number"] is None
        assert meta["chunk_index"] == 0
        assert "content_hash" in meta
        assert meta["doc_id"] is not None
        assert len(meta["doc_id"]) == 24

        # Verify unified text contains page demarcations
        for i in range(1, 11):
            assert f"--- Page {i} ---" in text
            assert f"Content on page {i} of syllabus." in text
