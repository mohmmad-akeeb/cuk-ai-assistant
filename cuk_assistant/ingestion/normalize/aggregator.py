"""Multi-route reference aggregator for raw assets and documents.

Merges multi-route references pointing to the same underlying asset (e.g. PDFs
or shared forms linked from multiple department or school menus), harmonizing:
  - associated_departments
  - associated_schools
  - associated_routes
  - is_university_wide
  - primary_department
"""

from __future__ import annotations

from typing import Any


def aggregate_asset_references(
    entries: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge metadata across multiple manifest references to the same asset.

    Returns the consolidated metadata dictionary.
    """
    if not entries:
        return {}

    base = dict(entries[0].get("raw_meta", {}))

    all_depts: set[str] = set()
    all_schools: set[str] = set()
    all_routes: list[list[str]] = []

    for item in entries:
        prov = item.get("provenance", {})
        meta = item.get("raw_meta", {})

        # Merge simple fields if base is missing them
        for k, v in meta.items():
            if (base.get(k) is None or base.get(k) == "") and v not in (None, ""):
                base[k] = v

        # Collect departments
        dept = prov.get("department") or meta.get("department") or meta.get("department_name")
        if dept:
            all_depts.add(str(dept))
        for d in prov.get("associated_departments", []):
            if d:
                all_depts.add(str(d))

        # Collect schools
        school = prov.get("school") or meta.get("school") or meta.get("school_name")
        if school:
            all_schools.add(str(school))
        for s in prov.get("associated_schools", []):
            if s:
                all_schools.add(str(s))

        # Collect routes / node paths
        node_path = prov.get("node_path") or meta.get("node_path")
        if node_path and isinstance(node_path, list) and node_path not in all_routes:
            all_routes.append(node_path)
        for r in prov.get("associated_routes", []):
            if r and isinstance(r, list) and r not in all_routes:
                all_routes.append(r)

    sorted_depts = sorted(all_depts)
    sorted_schools = sorted(all_schools)

    base["associated_departments"] = sorted_depts
    base["associated_schools"] = sorted_schools
    base["associated_routes"] = all_routes

    # Determine university-wide scope
    is_univ = (
        bool(base.get("is_university_wide", False))
        or len(sorted_depts) >= 3
        or len(sorted_schools) >= 2
    )
    base["is_university_wide"] = is_univ

    # Primary department
    if is_univ:
        primary_dept = "University-Wide"
    elif sorted_depts:
        primary_dept = sorted_depts[0]
    else:
        primary_dept = base.get("department") or "General"
    base["primary_department"] = primary_dept

    return base


__all__ = ["aggregate_asset_references"]
