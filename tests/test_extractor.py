"""
tests/test_extractor.py — Unit tests for se_scraper.extractor

Run with::

    pytest tests/ -v

All tests are deterministic and require zero network access.
"""

import pytest

from se_scraper.extractor import (
    COLUMN_ORDER,
    _clean,
    _s,
    extract_record,
    partner_list_from_body,
)


# ── _s() ──────────────────────────────────────────────────────────────────────


class TestSafeStr:
    def test_none_returns_empty_string(self):
        assert _s(None) == ""

    def test_bool_true_returns_lowercase(self):
        assert _s(True) == "true"

    def test_bool_false_returns_lowercase(self):
        assert _s(False) == "false"

    def test_int_converts_to_string(self):
        assert _s(42) == "42"

    def test_string_is_stripped(self):
        assert _s("  hello  ") == "hello"

    def test_empty_string_returned_as_is(self):
        assert _s("") == ""


# ── _clean() ──────────────────────────────────────────────────────────────────


class TestClean:
    def test_removes_null_byte(self):
        assert "\x00" not in _clean("foo\x00bar")

    def test_removes_tab(self):
        assert "\t" not in _clean("col1\tcol2")

    def test_removes_newline(self):
        assert "\n" not in _clean("line1\nline2")

    def test_removes_del_char(self):
        assert "\x7f" not in _clean("abc\x7fdef")

    def test_clean_string_is_unchanged(self):
        assert _clean("Hello World") == "Hello World"

    def test_strips_outer_whitespace(self):
        assert _clean("  trimmed  ") == "trimmed"


# ── Fixtures ──────────────────────────────────────────────────────────────────

MINIMAL_ITEM: dict = {
    "id": 12345,
    "companyName": "ACME Corp",
    "city": "Paris",
    "country": "France",
    "countryId": "FR",
    "address1": "1 Rue de Rivoli",
    "address2": None,
    "zipCode": "75001",
    "latitude": 48.8566,
    "longitude": 2.3522,
    "webSite": "https://acme.fr",
    "webSite2": None,
    "logoUrl": None,
    "accountBfoId": "BFO-001",
    "idGroup": "G1",
    "administrativeRegion": "Ile-de-France",
    "stateId": None,
    "emailExists": True,
    "phoneExists": False,
    "openingHoursType": "standard",
    "eshop": False,
    "productCount": 10,
    "partnerDetails": {
        "firstName": "Jean",
        "lastName": "Dupont",
        "about": "Authorized distributor",
        "partnerContact": {
            "email": "jean@acme.fr",
            "phone": "+33 1 23 45 67 89",
        },
        "descriptions": [
            {"description": "Main description", "isDefault": True},
            {"description": "Alt description", "isDefault": False},
        ],
    },
    "businessType": [
        {"code": "DIST", "name": "Distributor"},
        {"code": "INT", "name": "Integrator"},
    ],
    "programLevels": [
        {
            "logoUrl": "https://logo.png",
            "globalProgramLevelId": "GOLD",
            "displayRank": 1,
            "b2cAvailable": True,
        }
    ],
    "openingHours": [],
    "preferredMarketServe": [],
    "competence": [],
    "areaOfFocus": [],
    "customReference": [],
}


# ── extract_record() ──────────────────────────────────────────────────────────


class TestExtractRecord:
    def test_returns_dict(self):
        assert isinstance(extract_record(MINIMAL_ITEM), dict)

    def test_scalar_id_as_string(self):
        assert extract_record(MINIMAL_ITEM)["id"] == "12345"

    def test_scalar_string_fields(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["companyName"] == "ACME Corp"
        assert result["city"] == "Paris"
        assert result["country"] == "France"

    def test_contact_email(self):
        assert extract_record(MINIMAL_ITEM)["contact_email"] == "jean@acme.fr"

    def test_contact_phone(self):
        assert extract_record(MINIMAL_ITEM)["contact_phone"] == "+33 1 23 45 67 89"

    def test_first_and_last_name(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["firstName"] == "Jean"
        assert result["lastName"] == "Dupont"

    def test_default_description_selected(self):
        assert extract_record(MINIMAL_ITEM)["description"] == "Main description"

    def test_business_type_codes_semicolon_joined(self):
        assert extract_record(MINIMAL_ITEM)["businessType_codes"] == "DIST; INT"

    def test_business_type_names_semicolon_joined(self):
        assert extract_record(MINIMAL_ITEM)["businessType_names"] == "Distributor; Integrator"

    def test_program_level_first_entry_only(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["programLevel_globalId"] == "GOLD"
        assert result["programLevel_displayRank"] == "1"

    def test_bool_fields_lowercased_strings(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["emailExists"] == "true"
        assert result["phoneExists"] == "false"
        assert result["eshop"] == "false"

    def test_none_fields_become_empty_string(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["address2"] == ""
        assert result["webSite2"] == ""
        assert result["logoUrl"] == ""

    def test_empty_arrays_become_empty_strings(self):
        result = extract_record(MINIMAL_ITEM)
        assert result["openingHours"] == ""
        assert result["competence"] == ""
        assert result["areaOfFocus"] == ""

    def test_missing_partner_details_does_not_raise(self):
        item = {"id": 999, "companyName": "Bare Co"}
        result = extract_record(item)
        assert result["contact_email"] == ""
        assert result["description"] == ""
        assert result["businessType_codes"] == ""
        assert result["programLevel_globalId"] == ""

    def test_control_chars_stripped_from_company_name(self):
        item = {"id": 1, "companyName": "Bad\x00Corp\x01"}
        result = extract_record(item)
        assert "\x00" not in result["companyName"]
        assert "\x01" not in result["companyName"]

    def test_all_column_order_keys_present(self):
        result = extract_record(MINIMAL_ITEM)
        for col in COLUMN_ORDER:
            assert col in result, f"Missing expected column: {col!r}"


# ── partner_list_from_body() ──────────────────────────────────────────────────


class TestPartnerListFromBody:
    def test_list_returned_directly(self):
        data = [{"id": 1}, {"id": 2}]
        assert partner_list_from_body(data) == data

    def test_dict_with_items_key(self):
        assert partner_list_from_body({"items": [{"id": 1}]}) == [{"id": 1}]

    def test_dict_with_results_key(self):
        assert partner_list_from_body({"results": [{"id": 2}]}) == [{"id": 2}]

    def test_dict_with_partners_key(self):
        assert partner_list_from_body({"partners": [{"id": 3}]}) == [{"id": 3}]

    def test_single_partner_dict_wrapped_in_list(self):
        data = {"id": 42, "companyName": "Solo Co"}
        assert partner_list_from_body(data) == [data]

    def test_empty_dict_returns_empty_list(self):
        assert partner_list_from_body({}) == []

    def test_empty_items_key_skipped_falls_through_to_results(self):
        data = {"items": [], "results": [{"id": 5}]}
        assert partner_list_from_body(data) == [{"id": 5}]

    def test_none_returns_empty_list(self):
        assert partner_list_from_body(None) == []

    def test_string_returns_empty_list(self):
        assert partner_list_from_body("not a list") == []


# ── COLUMN_ORDER sanity ────────────────────────────────────────────────────────


class TestColumnOrder:
    def test_no_duplicate_columns(self):
        assert len(COLUMN_ORDER) == len(set(COLUMN_ORDER)), "Duplicate column names found"

    def test_id_is_first(self):
        assert COLUMN_ORDER[0] == "id"

    def test_minimum_column_count(self):
        assert len(COLUMN_ORDER) >= 30, "Unexpectedly few columns defined"
