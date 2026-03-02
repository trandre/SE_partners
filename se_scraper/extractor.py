"""
extractor.py — Pure data extraction and flattening logic.

All functions are synchronous with no side effects.
They operate only on plain Python dicts and return plain Python dicts,
making them trivially unit-testable without Playwright or network access.
"""

import json
import re

# ── Column ordering ───────────────────────────────────────────────────────────
# Controls the left-to-right column order in the output CSV.
# Fields found in the data that are NOT listed here are appended at the end.
COLUMN_ORDER: list[str] = [
    # Identity
    "id", "accountBfoId", "idGroup",
    # Company
    "companyName",
    # Address
    "address1", "address2", "city", "zipCode",
    "administrativeRegion", "stateId",
    "country", "countryId",
    # Geo
    "latitude", "longitude",
    # Web & logo
    "webSite", "webSite2", "logoUrl",
    # Contact (from partnerDetails.partnerContact)
    "contact_email", "contact_phone",
    # Person (from partnerDetails)
    "firstName", "lastName", "about", "description",
    # Flags
    "emailExists", "phoneExists", "eshop",
    "openingHoursType", "productCount",
    # Business type
    "businessType_codes", "businessType_names",
    # Program level (first entry)
    "programLevel_logoUrl", "programLevel_globalId",
    "programLevel_displayRank", "programLevel_b2cAvailable",
    # Usually-empty arrays
    "openingHours", "preferredMarketServe",
    "competence", "areaOfFocus", "customReference",
]


def _s(v) -> str:
    """Safely coerce any value to a stripped string. None → ''."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v).lower()
    return str(v).strip()


def _clean(v: str) -> str:
    """Strip ASCII control characters (0x00–0x1F, 0x7F) from a string."""
    return re.sub(r"[\x00-\x1f\x7f]", " ", v).strip()


def extract_record(item: dict) -> dict:
    """
    Flatten one SE partner JSON object into a single flat dict.

    Args:
        item: A raw partner JSON object from the id-list-grouped API response.

    Returns:
        A flat dict with keys matching COLUMN_ORDER (plus any extras found).
    """
    row: dict = {}

    # ── Scalar top-level fields ───────────────────────────────────────────────
    for f in (
        "accountBfoId", "id", "idGroup",
        "country", "companyName",
        "address1", "address2", "zipCode", "city",
        "webSite", "webSite2", "countryId",
        "latitude", "longitude",
        "administrativeRegion", "stateId",
        "emailExists", "phoneExists",
        "openingHoursType", "eshop",
        "productCount", "logoUrl",
    ):
        row[f] = _clean(_s(item.get(f)))

    # ── partnerDetails (nested object) ────────────────────────────────────────
    pd_data = item.get("partnerDetails") or {}
    row["firstName"] = _clean(_s(pd_data.get("firstName")))
    row["lastName"]  = _clean(_s(pd_data.get("lastName")))
    row["about"]     = _clean(_s(pd_data.get("about")))

    contact = pd_data.get("partnerContact") or {}
    row["contact_email"] = _clean(_s(contact.get("email")))
    row["contact_phone"] = _clean(_s(contact.get("phone")))

    descs = pd_data.get("descriptions") or []
    row["description"] = _clean(next(
        (_s(d.get("description")) for d in descs
         if d.get("isDefault") and d.get("description")),
        ""
    ))

    # ── businessType[] (array of {code, name}) ────────────────────────────────
    bt_list = item.get("businessType") or []
    row["businessType_codes"] = "; ".join(
        _s(b.get("code")) for b in bt_list if b.get("code")
    )
    row["businessType_names"] = "; ".join(
        _s(b.get("name")) for b in bt_list if b.get("name")
    )

    # ── programLevels[] (take first entry only) ───────────────────────────────
    pl_list = item.get("programLevels") or []
    pl = pl_list[0] if pl_list else {}
    row["programLevel_logoUrl"]      = _clean(_s(pl.get("logoUrl")))
    row["programLevel_globalId"]     = _clean(_s(pl.get("globalProgramLevelId")))
    row["programLevel_displayRank"]  = _clean(_s(pl.get("displayRank")))
    row["programLevel_b2cAvailable"] = _clean(_s(pl.get("b2cAvailable")))

    # ── Usually-empty arrays (serialize items as JSON joined by "; ") ──────────
    for arr_f in (
        "openingHours", "preferredMarketServe",
        "competence", "areaOfFocus", "customReference",
    ):
        arr = item.get(arr_f) or []
        row[arr_f] = "; ".join(json.dumps(v, ensure_ascii=False) for v in arr)

    return row


def partner_list_from_body(body) -> list:
    """
    Extract a list of partner dicts from various JSON response shapes.

    The API occasionally returns the list directly, or wraps it in a dict
    under one of several possible key names.

    Args:
        body: Parsed JSON (list, dict, or anything else).

    Returns:
        A list of partner dicts (may be empty).
    """
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for key in (
            "items", "results", "data", "partners", "distributors",
            "dealers", "content", "hits", "records", "list",
        ):
            val = body.get(key)
            if isinstance(val, list) and val:
                return val
        # Single-object response — wrap in a list
        if any(k in body for k in ("id", "companyName", "partnerName", "name")):
            return [body]
    return []
