import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    # Try package-style import first
    from backend.api.routes import _int_or_none, _parse_attr_pairs
    from backend.services.auction_service import normalize_filters, validate_filters
except ImportError:
    # Fallback for direct execution (backend/ is now in sys.path)
    from api.routes import _int_or_none, _parse_attr_pairs
    from services.auction_service import normalize_filters, validate_filters

# ---------------------------------------------------------------------------
# Helpers / Wrappers
# ---------------------------------------------------------------------------

def check_int_or_none(value, expected):
    """Wrapper to check _int_or_none and print details on failure."""
    result = _int_or_none(value)
    if result != expected:
        print(f"\n[FAIL] _int_or_none({value!r})\n  Expected: {expected!r}\n  Actual:   {result!r}")
    assert result == expected

def check_parse_attr_pairs(raw, expected):
    """Wrapper to check _parse_attr_pairs and print details on failure."""
    result = _parse_attr_pairs(raw)
    if result != expected:
        print(f"\n[FAIL] _parse_attr_pairs({raw!r})\n  Expected: {expected!r}\n  Actual:   {result!r}")
    assert result == expected

def check_normalize_filters(filters, expected_subset):
    """Wrapper to check normalize_filters. Checks only the keys present in expected_subset."""
    result = normalize_filters(filters)
    for k, v in expected_subset.items():
        if result.get(k) != v:
            print(f"\n[FAIL] normalize_filters({filters!r})\n  Key '{k}':\n  Expected: {v!r}\n  Actual:   {result.get(k)!r}")
            assert result.get(k) == v

def check_validate_filters(filters, expected_errors):
    """Wrapper to check validate_filters. expected_errors can be a list or a subset of strings."""
    result = validate_filters(filters)
    # If expected_errors is a list, check exact match
    if isinstance(expected_errors, list):
        if result != expected_errors:
            print(f"\n[FAIL] validate_filters({filters!r})\n  Expected: {expected_errors!r}\n  Actual:   {result!r}")
        assert result == expected_errors
    # If it's a string, check if it's contained in any error
    elif isinstance(expected_errors, str):
        found = any(expected_errors in e for e in result)
        if not found:
            print(f"\n[FAIL] validate_filters({filters!r})\n  Expected error containing: {expected_errors!r}\n  Actual errors: {result!r}")
        assert found

# ---------------------------------------------------------------------------
# Tests: _int_or_none
# ---------------------------------------------------------------------------

def test_int_or_none():
    # Valid
    check_int_or_none("123", 123)
    check_int_or_none("0", 0)
    check_int_or_none("-5", -5)

    # Whitespace
    check_int_or_none(" 123 ", 123)
    check_int_or_none("\t999\n", 999)

    # Invalid
    check_int_or_none("abc", None)
    check_int_or_none("12.5", None)
    check_int_or_none("", None)
    check_int_or_none(None, None)
    check_int_or_none("inf", None)
    check_int_or_none("nan", None)

    # Large Integers
    large = str(sys.maxsize + 1)
    check_int_or_none(large, int(large))

# ---------------------------------------------------------------------------
# Tests: _parse_attr_pairs
# ---------------------------------------------------------------------------

def test_parse_attr_pairs():
    # Valid
    check_parse_attr_pairs("crit_chance:150,multishot:90.5", [
        {"url_name": "crit_chance", "value": 150.0},
        {"url_name": "multishot", "value": 90.5},
    ])

    # Whitespace normalization
    check_parse_attr_pairs(" crit_chance : 150 ", [
        {"url_name": "crit_chance", "value": 150.0},
    ])

    # Case normalization
    check_parse_attr_pairs("Crit Chance: 150", [
        {"url_name": "crit_chance", "value": 150.0},
    ])

    # Trailing Comma (Empty segment)
    # Code: split(",") -> ["a:1", ""]. if ":" not in "" -> return None.
    # Current behavior assumption based on code reading: returns None on trailing comma.
    check_parse_attr_pairs("crit_chance:150,", None)

    # Duplicate Keys
    check_parse_attr_pairs("crit:1,crit:2", [
        {"url_name": "crit", "value": 1.0},
        {"url_name": "crit", "value": 2.0},
    ])

    # Invalid Formats
    check_parse_attr_pairs("crit_chance", None)       # Missing colon
    check_parse_attr_pairs("crit_chance:abc", None)   # Non-numeric
    check_parse_attr_pairs("", None)
    check_parse_attr_pairs(None, None)

    # Security / Math Safety
    check_parse_attr_pairs("crit_chance:inf", None)
    check_parse_attr_pairs("crit_chance:nan", None)

# ---------------------------------------------------------------------------
# Tests: normalize_filters
# ---------------------------------------------------------------------------

def test_normalize_filters():
    # Defaults
    check_normalize_filters({"weapon_url_name": "rubico"}, {
        "re_rolls_min": 0,
        "platform": "pc",
        "polarity": None
    })

    # Polarity "any" removal
    check_normalize_filters({"weapon_url_name": "rubico", "polarity": "any"}, {
        "polarity": None
    })

    # Attribute normalization
    check_normalize_filters({
        "weapon_url_name": "rubico",
        "positive_attributes": "Critical Chance, Multishot"
    }, {
        "positive_attributes": "critical_chance,multishot"
    })

    # Weapon Name normalization
    check_normalize_filters({"weapon_url_name": "Rubico Prime"}, {
        "weapon_url_name": "rubico_prime"
    })

# ---------------------------------------------------------------------------
# Tests: validate_filters
# ---------------------------------------------------------------------------

def test_validate_filters_valid():
    # A fully valid request
    check_validate_filters({
        "weapon_url_name": "rubico",
        "mastery_rank_min": 8,
        "mastery_rank_max": 16,
        "re_rolls_min": 0,
        "re_rolls_max": 10,
        "mod_rank": "maxed",
        "platform": "pc",
        "polarity": "naramon",
        "buyout_policy": "direct",
        "sort_by": "price_asc"
    }, [])

def test_validate_filters_required():
    check_validate_filters({}, "Weapon name is required.")

def test_validate_filters_bounds_mr():
    # Min bounds — floor is 8 (rivens require MR 8)
    check_validate_filters({"weapon_url_name": "x", "mastery_rank_min": 7}, "Mastery rank minimum must be between 8 and 16")
    check_validate_filters({"weapon_url_name": "x", "mastery_rank_min": 17}, "Mastery rank minimum must be between 8 and 16")

    # Max bounds
    check_validate_filters({"weapon_url_name": "x", "mastery_rank_max": 0}, "Mastery rank maximum must be between 1 and 16")
    check_validate_filters({"weapon_url_name": "x", "mastery_rank_max": 17}, "Mastery rank maximum must be between 1 and 16")

def test_validate_filters_bounds_rerolls():
    check_validate_filters({"weapon_url_name": "x", "re_rolls_min": -1}, "Re-rolls minimum must be at least 0")
    check_validate_filters({"weapon_url_name": "x", "re_rolls_max": -1}, "Re-rolls maximum must be at least 0")

    # Cross-field
    check_validate_filters({"weapon_url_name": "x", "re_rolls_min": 10, "re_rolls_max": 5}, "cannot exceed maximum")

def test_validate_filters_bounds_mod_rank():
    # Only "maxed" or None (empty) are valid — integers are rejected
    check_validate_filters({"weapon_url_name": "x", "mod_rank": 8}, "Mod rank must be 'maxed' or empty")
    check_validate_filters({"weapon_url_name": "x", "mod_rank": "invalid"}, "Mod rank must be 'maxed' or empty")
    # Valid values produce no error
    check_validate_filters({"weapon_url_name": "x", "mod_rank": "maxed"}, [])
    check_validate_filters({"weapon_url_name": "x", "mod_rank": None}, [])

def test_validate_filters_input_lengths():
    # Weapon > 100
    long_name = "a" * 101
    check_validate_filters({"weapon_url_name": long_name}, "Weapon name must be 100 characters or fewer")

    # Attributes > 200
    long_attrs = "a" * 201
    check_validate_filters({"weapon_url_name": "x", "positive_attributes": long_attrs}, "Positive attributes string must be 200 characters or fewer")
    check_validate_filters({"weapon_url_name": "x", "negative_attributes": long_attrs}, "Negative attributes string must be 200 characters or fewer")

def test_validate_filters_enums():
    # Invalid Platform
    check_validate_filters({"weapon_url_name": "x", "platform": "xbox_360"}, 'Platform "xbox_360" is not valid')

    # Invalid Polarity
    check_validate_filters({"weapon_url_name": "x", "polarity": "unknown"}, 'Polarity "unknown" is not valid')

    # Invalid Buyout Policy
    check_validate_filters({"weapon_url_name": "x", "buyout_policy": "steal"}, 'Buyout policy "steal" is not valid')

    # Invalid Sort
    check_validate_filters({"weapon_url_name": "x", "sort_by": "random"}, 'Sort option "random" is not valid')

if __name__ == "__main__":
    # Allow running as a script too
    try:
        test_int_or_none()
        test_parse_attr_pairs()
        test_normalize_filters()
        test_validate_filters_valid()
        test_validate_filters_required()
        test_validate_filters_bounds_mr()
        test_validate_filters_bounds_rerolls()
        test_validate_filters_bounds_mod_rank()
        test_validate_filters_input_lengths()
        test_validate_filters_enums()
        print("All tests passed!")
    except AssertionError:
        print("Some tests failed.")
        sys.exit(1)
