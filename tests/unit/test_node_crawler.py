"""Unit tests for node crawler and early PDF link discovery."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cuk_assistant.core.config import Settings
from cuk_assistant.ingestion.crawl.node_crawler import (
    SiteNode,
    _fetch_node_content,
    _is_real_external,
    _parse_angular_route,
    build_node_table,
    nodes_to_jsonl,
)


def _make_node(**kwargs) -> SiteNode:
    defaults = {
        "node_id": "test_node_1",
        "route_name": "departmentList",
        "id": "DEPT_123",
        "menu_id": "MENU_456",
        "parent_node_id": "",
        "breadcrumb": ["School of Science", "Department of Physics"],
        "school_master_id": "SCH_1",
        "school_name": "School of Science",
        "department_master_id": "DEPT_123",
        "department_name": "Department of Physics",
        "source": "school-tree",
        "status": "pending",
        "http_status": 0,
        "angular_url": "https://www.cukashmir.ac.in/#/departmentList;id=DEPT_123;menuid=MENU_456",
        "api_endpoint": "",
        "request_payload": "",
    }
    defaults.update(kwargs)
    return SiteNode(**defaults)


def test_site_node_defaults_have_empty_pdf_links() -> None:
    node = _make_node()
    assert node.pdf_links == []
    assert isinstance(node.pdf_links, list)


@pytest.mark.asyncio
async def test_fetch_node_content_extracts_pdf_links() -> None:
    node = _make_node()

    # Mock API client
    html_with_pdf = (
        "<div>"
        "<h3>Syllabus and Notifications</h3>"
        "<p>Please see <a href='https://www.cukashmir.ac.in/docs/syllabus_2024.pdf'>Syllabus 2024</a>.</p>"
        "<p>Also check <a href='https://www.cukashmir.ac.in/docs/datesheet.pdf'>Date Sheet</a> and "
        "<a href='https://example.com/external_page'>External Link</a>.</p>"
        "</div>"
    )
    mock_api = AsyncMock()
    mock_api.department_page.return_value = [
        {
            "DepartmentDescription": html_with_pdf,
            "Title": "Physics Dept",
        }
    ]

    await _fetch_node_content(node, mock_api)

    assert node.status == "fetched"
    assert node.http_status == 200
    assert len(node.pdf_links) == 2

    pdf_urls = [p["url"] for p in node.pdf_links]
    assert "https://www.cukashmir.ac.in/docs/syllabus_2024.pdf" in pdf_urls
    assert "https://www.cukashmir.ac.in/docs/datesheet.pdf" in pdf_urls
    assert node.pdf_links[0]["found_on"] == node.angular_url
    assert node.pdf_links[0]["text"] == "Syllabus 2024"


def test_nodes_to_jsonl_serializes_pdf_links(tmp_path) -> None:
    out_file = tmp_path / "nodes_test.jsonl"
    node = _make_node()
    node.pdf_links = [
        {
            "url": "https://www.cukashmir.ac.in/test.pdf",
            "text": "Test Document",
            "found_on": node.angular_url,
        }
    ]

    nodes_to_jsonl([node], out_file)
    assert out_file.exists()

    lines = [json.loads(line) for line in out_file.read_text().splitlines() if line.strip()]
    assert len(lines) == 1
    assert "pdf_links" in lines[0]
    assert len(lines[0]["pdf_links"]) == 1
    assert lines[0]["pdf_links"][0]["url"] == "https://www.cukashmir.ac.in/test.pdf"


def test_is_real_external_helper() -> None:
    # False because ExternalLinkUrl is empty
    assert not _is_real_external({"IsExternalLink": True, "ExternalLinkUrl": ""})
    assert not _is_real_external({"IsExternalLink": True, "ExternalLinkUrl": None})
    assert not _is_real_external(
        {"IsExternalLink": False, "ExternalLinkUrl": "https://example.com"}
    )

    # True only when IsExternalLink is True and ExternalLinkUrl is non-empty
    assert _is_real_external({"IsExternalLink": True, "ExternalLinkUrl": "https://example.com"})


def test_normalize_href_spaces_and_prefixes() -> None:
    from cuk_assistant.ingestion.crawl.html_parser import parse_html

    html = (
        '<p><a href="https://cukapi.disgenweb.in/p/upload/1793341253116-Semester VII.pdf">Sem 7</a></p>'
        '<p><a href="1\thttps://cukapi.disgenweb.in/p/upload/1793341257916-Semester VIII.pdf">Sem 8</a></p>'
    )
    parsed = parse_html(html)
    assert len(parsed.links_out) == 2
    assert (
        parsed.links_out[0].href
        == "https://cukapi.disgenweb.in/p/upload/1793341253116-Semester%20VII.pdf"
    )
    assert (
        parsed.links_out[1].href
        == "https://cukapi.disgenweb.in/p/upload/1793341257916-Semester%20VIII.pdf"
    )


@pytest.mark.asyncio
async def test_cse_menu_item_with_is_external_true_and_empty_url_captures_pdfs() -> None:
    sample_record = {
        "DepartmentMasterId": "A81557E4-DC84-45D9-AE4D-E295B1EACD82",
        "ParentDepartmentMasterId": "7022529F-5494-4B1E-9A76-EB211C56019A",
        "IsHasLeftSectionSubMenus": False,
        "IsExternalLink": True,  # False external link flag!
        "IsActive": False,
        "ExternalLinkUrl": "",  # Empty URL!
        "DepartmentName": "B. Tech. CSE",
        "DepartmentTitle": "B. Tech. CSE",
        "DepartmentDescription": (
            '<p><a href="https://cukapi.disgenweb.in/p/upload/1682500433211-BTechCSE_Semester8_BOS_27_5_2020_B2_8_upload_20_9_2021.pdf">'
            "Semester 8</a></p>"
        ),
        "SubChildCount": 0,
    }

    mock_client = MagicMock()
    mock_client.get = AsyncMock()

    settings = Settings(
        base_url="https://www.cukashmir.ac.in",
        contact_email="test@cukashmir.ac.in",
        user_agent="TestAgent/1.0",
        rate_limit_rps=10.0,
        max_connections=2,
        circuit_breaker_threshold=5,
        max_pdf_bytes=10000000,
        project_root=Path("/tmp"),
        cache_dir=Path("/tmp/cache"),
        processed_dir=Path("/tmp/processed"),
        logs_dir=Path("/tmp/logs"),
        reports_dir=Path("/tmp/reports"),
        log_level="INFO",
    )

    with patch("cuk_assistant.ingestion.crawl.node_crawler.DirectApiClient") as mock_api_cls:
        mock_api = mock_api_cls.return_value
        mock_api.header_category_list = AsyncMock(return_value=[])
        mock_api.school_list = AsyncMock(
            return_value=[{"SchoolMasterId": "SCH_ENG", "SchoolName": "Engineering"}]
        )
        mock_api.mapped_departments = AsyncMock(
            return_value=[
                {
                    "DepartmentMasterId": "7022529F-5494-4B1E-9A76-EB211C56019A",
                    "DepartmentName": "CSE",
                }
            ]
        )
        mock_api.department_menu = AsyncMock(
            return_value=[
                {
                    "DepartmentMasterId": "7022529F-5494-4B1E-9A76-EB211C56019A",
                    "ParentDepartmentMasterId": None,
                    "DepartmentName": "CSE",
                },
                sample_record,
            ]
        )

        nodes = await build_node_table(settings, mock_client)

    cse_nodes = [n for n in nodes if n.menu_id == "A81557E4-DC84-45D9-AE4D-E295B1EACD82"]
    assert len(cse_nodes) == 1
    cse_node = cse_nodes[0]
    assert cse_node.route_name == "departmentList"
    assert cse_node.status == "pending"
    assert len(cse_node.pdf_links) == 1
    target_pdf = "https://cukapi.disgenweb.in/p/upload/1682500433211-BTechCSE_Semester8_BOS_27_5_2020_B2_8_upload_20_9_2021.pdf"
    assert cse_node.pdf_links[0]["url"] == target_pdf


def test_list_items_with_links_extracted():
    """Verify that <a> tags nested inside <li> and inline styles are extracted."""
    from cuk_assistant.ingestion.crawl.html_parser import parse_html

    html = (
        '<ol><li style="outline: none;"><span><i>'
        '<a href="https://cukapi.disgenweb.in/p/examnotification/1784616248702-List%20of%20Electives%20for%20PG%20Programmes%20new%20format.pdf">'
        "List of electives for PG programmes 2026 (Odd Semesters)</a></i></span></li>"
        '<li><a href="https://cukapi.disgenweb.in/p/upload/1785825325874-UG.pdf">UG Electives</a></li></ol>'
    )
    parsed = parse_html(html)
    assert len(parsed.links_out) == 2
    assert parsed.links_out[0].type == "pdf"
    assert "1784616248702" in parsed.links_out[0].href
    assert parsed.links_out[1].type == "pdf"
    assert "1785825325874" in parsed.links_out[1].href


def test_angular_route_parsing_and_is_real_external():
    """Verify Angular route parser and internal vs external link detection."""
    # Test _parse_angular_route
    r, id_, mid = _parse_angular_route("/#/administration;id=EB2A9992-5355-4B16")
    assert r == "administration"
    assert id_ == "EB2A9992-5355-4B16"
    assert mid == ""

    r, id_, mid = _parse_angular_route("/#/departmentList;id=DD9D0839;menuid=E4732BD3")
    assert r == "departmentList"
    assert id_ == "DD9D0839"
    assert mid == "E4732BD3"

    # Test _is_real_external with internal Angular routes
    assert not _is_real_external(
        {
            "IsExternalLink": True,
            "ExternalLinkUrl": "/#/administration;id=EB2A9992-5355-4B16",
        }
    )
    assert not _is_real_external(
        {
            "IsExternalLink": True,
            "ExternalLinkUrl": "https://www.cukashmir.ac.in/#/administrative-list;id=123",
        }
    )

    # Test _is_real_external with truly external links
    assert _is_real_external(
        {
            "IsExternalLink": True,
            "ExternalLinkUrl": "https://forms.eduqfix.com/cuktransportfee/add",
        }
    )
    assert _is_real_external(
        {
            "IsExternalLink": True,
            "ExternalLinkUrl": "https://cukashmircuet.samarth.edu.in",
        }
    )


def test_html_table_links_preserved_as_markdown():
    """Verify that <a> tags inside HTML tables are converted to markdown links and extracted in links_out."""
    from cuk_assistant.ingestion.crawl.html_parser import parse_html

    html_table = (
        '<table class="table table-hover">'
        "<tbody>"
        "<tr><th>S.No.</th><th>Direct Payments Link</th></tr>"
        '<tr><td>1.</td><td><a href="https://forms.eduqfix.com/cuktransportfee/add">Pay Transport Fee</a></td></tr>'
        '<tr><td>2.</td><td><a href="https://forms.eduqfix.com/cukrecruitmentadmissionform/add">Pay Recruitment Fee</a></td></tr>'
        '<tr><td>3.</td><td><a href="https://cukapi.disgenweb.in/docs/fee_structure.pdf">Fee Structure PDF</a></td></tr>'
        "</tbody></table>"
    )
    parsed = parse_html(html_table)

    # Check markdown table text preserves links
    assert "[Pay Transport Fee](https://forms.eduqfix.com/cuktransportfee/add)" in parsed.text
    assert (
        "[Pay Recruitment Fee](https://forms.eduqfix.com/cukrecruitmentadmissionform/add)"
        in parsed.text
    )
    assert "[Fee Structure PDF](https://cukapi.disgenweb.in/docs/fee_structure.pdf)" in parsed.text

    # Check links_out
    hrefs = [lo.href for lo in parsed.links_out]
    assert "https://forms.eduqfix.com/cuktransportfee/add" in hrefs
    assert "https://forms.eduqfix.com/cukrecruitmentadmissionform/add" in hrefs
    assert "https://cukapi.disgenweb.in/docs/fee_structure.pdf" in hrefs

    pdf_links = [lo for lo in parsed.links_out if lo.type == "pdf"]
    assert len(pdf_links) == 1
    assert pdf_links[0].href == "https://cukapi.disgenweb.in/docs/fee_structure.pdf"


def test_metadata_builder_implink_and_external_url_pdf():
    """Verify implink Description resolution and ExternalUrl PDF extraction."""
    from cuk_assistant.ingestion.crawl.metadata_builder import _file_url_permissive, build_metadata

    # 1. _file_url_permissive checks ExternalUrl and ExternalLinkUrl
    assert (
        _file_url_permissive({"ExternalUrl": "https://cukapi.disgenweb.in/p/upload/calendar.pdf"})
        == "https://cukapi.disgenweb.in/p/upload/calendar.pdf"
    )
    assert (
        _file_url_permissive(
            {"ExternalLinkUrl": "https://cukapi.disgenweb.in/p/upload/helpdesk.pdf"}
        )
        == "https://cukapi.disgenweb.in/p/upload/helpdesk.pdf"
    )

    # 2. build_metadata for implink uses Description for external target URL
    implink_record = {
        "ImpLinkId": "123",
        "Title": "CUET Portal",
        "Description": "https://cukashmircuet.samarth.edu.in",
        "Order": 1,
    }
    meta = build_metadata(
        "implink/selectimplinksforwebsite",
        implink_record,
        section="important_links",
    )
    assert meta["source_url"] == "https://cukashmircuet.samarth.edu.in"
    assert meta["title"] == "CUET Portal"


@pytest.mark.asyncio
async def test_fetch_node_content_administration_uses_administrative_list_by_id():
    """Verify route_name='administration' calls administrativeListById and scans AdministrativeDescription."""
    node = _make_node(
        route_name="administration",
        id="EB2A9992-5355-4B16-BE13-F04FF9E47749",
        menu_id="",
        angular_url="https://www.cukashmir.ac.in/#/administration;id=EB2A9992-5355-4B16-BE13-F04FF9E47749",
    )
    mock_api = AsyncMock()
    mock_api._post.return_value = [
        {
            "AdministrativeId": "EB2A9992-5355-4B16-BE13-F04FF9E47749",
            "AdministrativeName": "Archives",
            "AdministrativeTitle": "Archives",
            "AdministrativeDescription": (
                '<ol><li><a href="https://cukapi.disgenweb.in/p/upload/1777443094282-CASNotification020f2026.pdf">'
                "CAS Notification</a></li></ol>"
            ),
        }
    ]

    await _fetch_node_content(node, mock_api)

    assert node.status == "fetched"
    assert node.http_status == 200
    mock_api._post.assert_awaited_once_with(
        "administrative/administrativeListById",
        {"Id": "EB2A9992-5355-4B16-BE13-F04FF9E47749"},
    )
    assert len(node.pdf_links) == 1
    assert "1777443094282-CASNotification020f2026.pdf" in node.pdf_links[0]["url"]
