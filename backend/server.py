from flask import Flask, jsonify, request
import rivens as rv
import cache
from evaluation import compute_stats, estimate_price

app = Flask(__name__)


def _int_or_none(value: str):
    # Converts a query string value to int, returns None if blank or missing.
    v = (value or "").strip()
    return int(v) if v else None


def _str_or_none(value: str):
    # Strips and lowercases a query string value, returns None if blank.
    v = (value or "").strip().lower()
    return v if v else None


@app.route("/api/search", methods=["GET"])
def search():
    # Maps camelCase query params from the React frontend to the snake_case
    # filter dict that rivens.search_auctions() expects.
    args = request.args

    filters = {
        "weapon_url_name": _str_or_none(args.get("weaponName")),
        "positive_attributes":  _str_or_none(args.get("positiveAttributes")),
        "negative_attributes":  _str_or_none(args.get("negativeAttributes")),
        "mastery_rank_min": _int_or_none(args.get("mrMin")),
        "mastery_rank_max": _int_or_none(args.get("mrMax")),
        "mod_rank":        _str_or_none(args.get("modRank")),
        "re_rolls_min":    _int_or_none(args.get("minRerolls")),
        "re_rolls_max":    _int_or_none(args.get("maxRerolls")),
        "sort_by":         _str_or_none(args.get("sortBy")),
        "buyout_policy":   _str_or_none(args.get("buyoutPolicy")),
        "polarity":        _str_or_none(args.get("polarity")),
        "platform":        _str_or_none(args.get("platform")),
        "crossplay":       _str_or_none(args.get("crossplay")),
    }

    result, errors = rv.search_auctions(filters)

    if errors:
        # Return validation/API errors so the frontend can display them
        return jsonify({"errors": errors}), 400

    return jsonify(result)


@app.route("/api/riven/weapons", methods=["GET"])
def riven_weapons():
    # Returns the cached weapon list grouped by weapon type.
    # Each entry: { url_name, item_name, group }
    weapons = cache.get_weapons()
    if weapons is None:
        return jsonify({"error": "Weapon data not yet available — cache is loading."}), 503
    return jsonify(weapons)


@app.route("/api/riven/attributes", methods=["GET"])
def riven_attributes():
    # Returns cached attributes split into positive and negative lists.
    # Optionally filtered by weapon_group query param.
    attrs = cache.get_attributes()
    if attrs is None:
        return jsonify({"error": "Attribute data not yet available — cache is loading."}), 503

    weapon_group = request.args.get("weapon_group", "").strip().lower()

    def matches_group(attr):
        if not weapon_group:
            return True
        # Attribute group can be a comma-separated list or "all" etc.
        attr_group = attr.get("group", "")
        if not attr_group:
            return True
        return weapon_group in attr_group.lower()

    # Filter out search_only attributes — those are for internal API use
    filtered = [a for a in attrs if not a.get("search_only", False) and matches_group(a)]

    positive = filtered  # all non-search_only attributes can be positive
    negative = [a for a in filtered if not a.get("positive_only", False)]

    return jsonify({
        "positive": positive,
        "negative": negative,
    })


def _parse_attr_pairs(raw: str) -> list[dict] | None:
    """Parse 'url_name:value,url_name:value' into [{"url_name": str, "value": float}, ...].

    Returns None if the string is empty or malformed.
    """
    if not raw or not raw.strip():
        return None
    pairs = []
    for segment in raw.split(","):
        segment = segment.strip()
        if ":" not in segment:
            return None
        name, val_str = segment.rsplit(":", 1)
        name = name.strip().lower().replace(" ", "_")
        try:
            value = float(val_str.strip())
        except ValueError:
            return None
        if name:
            pairs.append({"url_name": name, "value": value})
    return pairs if pairs else None


@app.route("/api/estimate", methods=["GET"])
def estimate():
    # Price estimation endpoint.
    # Parses target riven attributes, fetches all auctions for the weapon,
    # and runs the similarity-based pricing pipeline.
    args = request.args

    weapon = _str_or_none(args.get("weaponName"))
    if not weapon:
        return jsonify({"errors": ["Weapon name is required."]}), 400

    # Parse positive attributes (required): "critical_chance:180.5,multishot:110.2"
    pos_raw = args.get("positiveAttributes", "")
    positive_attrs = _parse_attr_pairs(pos_raw)
    if not positive_attrs:
        return jsonify({"errors": [
            "positiveAttributes is required. Format: url_name:value,url_name:value "
            "(e.g. critical_chance:180.5,multishot:110.2)"
        ]}), 400

    # Parse negative attribute (optional): "recoil:-85.3"
    neg_raw = args.get("negativeAttribute", "")
    negative_attr = None
    if neg_raw and neg_raw.strip():
        parsed = _parse_attr_pairs(neg_raw)
        if not parsed:
            return jsonify({"errors": [
                "negativeAttribute format invalid. Expected url_name:value (e.g. recoil:-85.3)"
            ]}), 400
        negative_attr = parsed[0]  # single negative only

    re_rolls = _int_or_none(args.get("rerolls")) or 0
    platform = _str_or_none(args.get("platform")) or "pc"
    crossplay = _str_or_none(args.get("crossplay")) or "true"

    # Fetch all auctions for this weapon (no stat filters) via rivens orchestration
    auctions, errors = rv.fetch_weapon_auctions(weapon, platform, crossplay)
    if errors:
        return jsonify({"errors": errors}), 400

    if not auctions:
        return jsonify({"errors": [
            f"No auctions found for weapon '{weapon}' on {platform}."
        ]}), 404

    # Look up weapon disposition
    weapon_display = weapon.replace("_", " ").title()
    disposition = cache.get_disposition(weapon_display)

    # Run the pricing pipeline
    result = estimate_price(
        positive_attrs=positive_attrs,
        negative_attr=negative_attr,
        re_rolls=re_rolls,
        auctions=auctions,
        disposition=disposition,
    )

    # Also include basic market stats for context
    stats = compute_stats(auctions)

    return jsonify({
        "estimate": result.to_dict(),
        "stats": stats.to_dict(),
    })


