"""Async HTTP client with retry, backoff, and rate limits for CUK raw collection.

Interacts with https://cukapi.disgenweb.in and https://cukashmir.ac.in.
Saves pure, unmodified HTTP/API responses directly to disk.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from cuk_assistant.core.http_cache import CachedClient

logger = logging.getLogger(__name__)

API_BASE = "https://cukapi.disgenweb.in"

_API_HEADERS = {
    "Content-Type": "application/json",
    "langtype": "1",
    "Origin": "https://cukashmir.ac.in",
    "Referer": "https://cukashmir.ac.in/",
    "Accept": "application/json",
}


def _sanitize_guid(val: Any) -> str:
    """Verify val is a valid UUID/GUID format. If invalid or empty, return ''."""
    if not val:
        return ""
    s = str(val).strip()
    try:
        uuid.UUID(s)
        return s
    except (ValueError, AttributeError, TypeError):
        return ""


def _unpack_list(data: Any) -> list[dict]:
    """Unpack nested lists (e.g. tender/getalltender returns [[{...}]])."""
    if not isinstance(data, list):
        return []
    flat: list[dict] = []
    for item in data:
        if isinstance(item, list):
            flat.extend(_unpack_list(item))
        elif isinstance(item, dict):
            flat.append(item)
    return flat


def _payload_suffix(payload: dict) -> str:
    """Return a short stable query-string suffix from a payload dict."""
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.md5(raw.encode()).hexdigest()[:12]  # noqa: S324


class DirectApiClient:
    """Async client that injects CUK API headers, rate limits, and caches responses."""

    def __init__(self, cached_client: CachedClient) -> None:
        self._client = cached_client

    @retry(
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=False,
    )
    async def _post_raw(self, url: str, payload: dict) -> bytes:
        user_agent = getattr(self._client, "_user_agent", "CukAssistantBot/1.0")
        async with httpx.AsyncClient(
            headers={**_API_HEADERS, "User-Agent": user_agent},
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        ) as hx:
            resp = await hx.post(url, content=json.dumps(payload).encode())
            resp.raise_for_status()
            return resp.content

    async def _post(self, path: str, payload: dict) -> Any:
        """POST to API_BASE/path with payload; cache by (path, payload hash)."""
        url = f"{API_BASE}/{path}"
        suffix = _payload_suffix(payload)
        cache_url = f"{url}?_ph={suffix}"

        cached = await self._client.get(cache_url)
        if cached.from_cache and cached.body:
            try:
                parsed = json.loads(cached.body)
                return _unpack_list(parsed) if isinstance(parsed, list) else parsed
            except Exception:
                pass

        try:
            body = await self._post_raw(url, payload)
            from cuk_assistant.core.http_cache import _write_cache, cache_key

            key = cache_key(cache_url)
            _write_cache(
                self._client._cache_dir,
                key,
                body,
                200,
                {"content-type": "application/json"},
                cache_url,
            )
            parsed = json.loads(body)
            return _unpack_list(parsed) if isinstance(parsed, list) else parsed
        except Exception as exc:
            logger.warning("API POST failed: %s — %s", path, exc)
            return []

    @retry(
        retry=retry_if_exception_type(
            (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError)
        ),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=False,
    )
    async def _get_raw(self, url: str) -> bytes:
        user_agent = getattr(self._client, "_user_agent", "CukAssistantBot/1.0")
        async with httpx.AsyncClient(
            headers={**_API_HEADERS, "User-Agent": user_agent},
            timeout=httpx.Timeout(30.0),
            follow_redirects=False,
        ) as hx:
            resp = await hx.get(url)
            resp.raise_for_status()
            return resp.content

    async def _get(self, path: str) -> Any:
        """GET from API_BASE/path with API headers; caches the response."""
        url = f"{API_BASE}/{path}"

        cached = await self._client.get(url)
        if cached.from_cache and cached.body:
            try:
                return json.loads(cached.body)
            except Exception:
                pass

        try:
            body = await self._get_raw(url)
            from cuk_assistant.core.http_cache import _write_cache, cache_key

            key = cache_key(url)
            _write_cache(
                self._client._cache_dir,
                key,
                body,
                200,
                {"content-type": "application/json"},
                url,
            )
            return json.loads(body)
        except Exception as exc:
            logger.warning("API GET failed: %s — %s", path, exc)
            return []

    # ── Public API endpoints ────────────────────────────────────────────────

    async def school_list(self) -> list[dict]:
        data = await self._get("school/schoolList")
        return data if isinstance(data, list) else []

    async def mapped_departments(self, school_master_id: str) -> list[dict]:
        data = await self._post(
            "department/getMappedDepartmentListBySchoolMasterId",
            {"SchoolMasterId": school_master_id},
        )
        return data if isinstance(data, list) else []

    async def header_categories(self) -> list[dict]:
        data = await self._get("headercategory/headercategoryList")
        return data if isinstance(data, list) else []

    async def header_category_list(self) -> list[dict]:
        return await self.header_categories()

    async def department_menu(self, department_master_id: str) -> list[dict]:
        data = await self._post(
            "department/getMappedDepartmentMenuListByDepartmentMasterId",
            {"DepartmentMasterId": department_master_id},
        )
        return _unpack_list(data)

    async def department_page(self, page_id: str) -> list[dict]:
        data = await self._post(
            "department/departmentListById",
            {"Id": page_id},
        )
        return _unpack_list(data)

    async def sub_categories(self, header_category_id: str) -> list[dict]:
        data = await self._post(
            "headercategory/subCategoryListByHeaderCategoryId",
            {"HeaderCategoryId": header_category_id},
        )
        return data if isinstance(data, list) else []

    async def department_detail(self, department_master_id: str) -> dict:
        data = await self._post(
            "department/getDepartmentDetailsByDepartmentMasterId",
            {"DepartmentMasterId": department_master_id},
        )
        if isinstance(data, list) and data:
            return data[0] if isinstance(data[0], dict) else {}
        return data if isinstance(data, dict) else {}

    async def faculty_by_dept(self, department_id: str) -> list[dict]:
        data = await self._post(
            "faculty/getallforwebsite",
            {"langType": 1, "DepartmentId": department_id},
        )
        return data if isinstance(data, list) else []

    async def all_tenders(self) -> list[dict]:
        data = await self._post("tender/getalltender", {"langType": 1})
        return _unpack_list(data)

    async def all_admissions(self, seen: int = 0) -> list[dict]:
        data = await self._post("admission/all", {"seen": seen, "next": 0})
        return _unpack_list(data)

    async def all_notices(self, seen: int = 0) -> list[dict]:
        data = await self._post("noticeboard/all", {"seen": seen, "next": 0})
        return _unpack_list(data)

    async def all_employments(self, seen: int = 0) -> list[dict]:
        data = await self._post("employments/all", {"seen": seen, "next": 0})
        return _unpack_list(data)

    async def all_press_releases(self, seen: int = 0) -> list[dict]:
        data = await self._post(
            "pressrelease/getAllPressReleasesForWebSite", {"seen": seen, "next": 0}
        )
        return _unpack_list(data)

    async def press_releases(self, seen: int = 0, next_n: int = 50) -> list[dict]:
        data = await self._post(
            "pressrelease/getAllPressReleasesForWebSite",
            {"langType": 1, "seen": seen, "next": next_n},
        )
        return _unpack_list(data)

    async def moe_press_releases(self, seen: int = 0, next_n: int = 50) -> list[dict]:
        data = await self._post(
            "moe/getAllPressReleasesForWebSite",
            {"langType": 1, "seen": seen, "next": next_n},
        )
        return _unpack_list(data)

    async def administrative_menu(self, section_id: str) -> list[dict]:
        data = await self._post(
            "administrative/administrativeListById",
            {"Id": section_id, "LangType": 1},
        )
        return _unpack_list(data)

    async def employee_profiles(self, section_id: str) -> list[dict]:
        data = await self._post(
            "employeeprofile/getallforwebsite",
            {"langType": 1, "SectionId": section_id},
        )
        return _unpack_list(data)

    async def paged_list(
        self,
        endpoint: str,
        department_id: str = "",
        seen: int = 0,
        next_n: int = 100,
    ) -> list[dict]:
        clean_dept_id = _sanitize_guid(department_id)
        data = await self._post(
            endpoint,
            {"langType": 1, "DepartmentId": clean_dept_id, "seen": seen, "next": next_n},
        )
        return _unpack_list(data)

    async def list_endpoint(self, endpoint: str, payload: dict) -> list[dict]:
        data = await self._post(endpoint, payload)
        return _unpack_list(data)


async def download_pdf_cached(
    url: str,
    dest_path: Path,
    cached_client: CachedClient,
    *,
    skip_pdf: bool = False,
) -> bool:
    """Download PDF to dest_path if not already downloaded or cached with matching size.

    Returns True if file is ready at dest_path, False if skipped or failed.
    """
    if skip_pdf:
        return False

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists() and dest_path.stat().st_size > 0:
        # File already exists on disk
        return True

    # Try fetching from CachedClient
    try:
        resp = await cached_client.get(url)
        if resp.status_code == 200 and resp.body:
            dest_path.write_bytes(resp.body)
            return True
    except Exception as exc:
        logger.debug("PDF download failed for %s: %s", url, exc)

    return False


__all__ = [
    "API_BASE",
    "DirectApiClient",
    "_API_HEADERS",
    "_payload_suffix",
    "_sanitize_guid",
    "_unpack_list",
    "download_pdf_cached",
]
