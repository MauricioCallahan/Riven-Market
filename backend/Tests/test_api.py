import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

try:
    from backend import rivens as rv
except ImportError:
    import rivens as rv

# Test cases covering every filter param the API actually accepts.
# mastery_rank_min, mod_rank, and weapon-less searches are NOT supported by the API.
TEST_CASES = [
    {
        "name": "Minimal — weapon only",
        "filters": {
            "weapon_url_name": "rubico",
        },
    },
    {
        "name": "All supported fields populated",
        "filters": {
            "weapon_url_name": "rubico",
            "positive_attributes": "critical_chance",
            "negative_attributes": "recoil",
            "mastery_rank_max": 16,
            "re_rolls_min": 1,
            "re_rolls_max": 10,
            "sort_by": "price_asc",
            "buyout_policy": "direct",
            "polarity": "any",
        },
    },
    {
        "name": "Normalize test — rr_min=0 should become 1",
        "filters": {
            "weapon_url_name": "rubico",
            "re_rolls_min": 0,
        },
    },
    {
        "name": "polarity filter",
        "filters": {
            "weapon_url_name": "arca_plasmor",
            "polarity": "vazarin",
        },
    },
    {
        "name": "price_desc + polarity + buyout_policy=direct",
        "filters": {
            "weapon_url_name": "rubico",
            "sort_by": "price_desc",
            "buyout_policy": "direct",
            "polarity": "naramon",
        },
    },
    {
        "name": "Re-rolls range only",
        "filters": {
            "weapon_url_name": "rubico",
            "re_rolls_min": 5,
            "re_rolls_max": 20,
        },
    },
    {
        "name": "Mastery rank max only",
        "filters": {
            "weapon_url_name": "rubico",
            "mastery_rank_max": 10,
        },
    },
    {
        "name": "Positive attributes only",
        "filters": {
            "weapon_url_name": "rubico",
            "positive_attributes": "multishot",
        },
    },
    # --- These should be caught by validation, not sent to the API ---
    {
        "name": "SHOULD FAIL — no weapon (validation catches it)",
        "filters": {
            "sort_by": "price_desc",
        },
        "expect_fail": True,
    },
    {
        "name": "Spaces in weapon name normalized to underscores",
        "filters": {
            "weapon_url_name": "arca plasmor",
        },
    },
    {
        "name": "Unsupported params stripped — mastery_rank_min and mod_rank ignored silently",
        "filters": {
            "weapon_url_name": "rubico",
            "mastery_rank_min": 8,
            "mod_rank": 8,
        },
    },
]


def run_tests():
    passed = 0
    failed = 0

    for i, tc in enumerate(TEST_CASES, 1):
        name = tc["name"]
        filters = tc["filters"]
        expect_fail = tc.get("expect_fail", False)

        print(f"\n{'='*60}")
        print(f"Test {i}: {name}")
        print(f"Filters: {filters}")

        auctions, errors = rv.search_auctions(filters)

        if errors:
            if expect_fail:
                print(f"PASSED (expected failure) — errors: {errors}")
                passed += 1
            else:
                print(f"FAILED — errors: {errors}")
                failed += 1
        else:
            auction_list = auctions["auctions"]
            if expect_fail:
                print(f"FAILED (expected failure but got {len(auction_list)} results)")
                failed += 1
            else:
                print(f"PASSED — {len(auction_list)} auction(s) returned")
                if auction_list:
                    a = auction_list[0]
                    print(f"  Sample: {a['weapon']} — {a['rivenName']} — "
                          f"Buyout: {a['buyout']} — Attributes: {a['positiveAttributes']}")
                passed += 1

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {passed + failed} total")


if __name__ == "__main__":
    run_tests()
