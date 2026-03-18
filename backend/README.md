# Backend — Riven Market API

Flask-based API server that proxies and enriches data from the Warframe Market API, with a custom similarity-based pricing engine for riven valuation.

## Layered Architecture

```
backend/
├── main.py              — Entry point: initializes cache, starts Flask on :5000
├── api/
│   └── routes.py        — Route definitions, camelCase ↔ snake_case param mapping
├── services/
│   ├── auction_service.py — Orchestration: normalize → validate → build params → API call → parse
│   ├── cache_service.py   — File-based JSON cache with 24h TTL and background refresh
│   └── warframe_client.py — HTTP client for warframe.market (single responsibility)
├── core/
│   ├── models.py        — Dataclasses: Auction, RivenAttribute, FieldStats, PriceStats
│   └── config.py        — Constants: URLs, headers, dropdown options, valid platforms
├── .cache/              — Cached data (gitignored): weapons.json, attributes.json, dispositions.json
└── evaluation/          — Pricing engine package (domain logic)
    ├── __init__.py      — Public exports: compute_stats, estimate_price, PriceEstimate
    ├── stats.py         — Basic market stats (min/max/mean/median)
    ├── riven_math.py    — Base stat tables (32 attributes), roll normalization
    ├── stat_weights.py  — Market-driven stat importance via top-30% frequency analysis
    ├── archetypes.py    — Riven classification: Crit / Status / Hybrid / Other
    ├── similarity.py    — Cosine similarity with negative-stat and reroll adjustments
    └── price_estimator.py — Orchestrator: weights → vectors → similarity → IQR → weighted avg
```

## Design Principles

- **Separation of concerns** — `api/routes.py` only maps params and returns JSON. `services/auction_service.py` orchestrates. `services/warframe_client.py` handles HTTP. `core/models.py` handles parsing. `evaluation/` handles pricing.
- **Config-driven** — Dropdown options, valid values, and API URLs live in `core/config.py`. Validation sets are derived from config, not hardcoded.
- **Graceful degradation** — If warframestat.us is down, weapons are still served with a neutral disposition (3). If the cache is stale, background threads refresh it without blocking requests.

## API Endpoints

### `GET /api/search`

Search live riven auctions on warframe.market.

| Param | Frontend Key | Type | Notes |
|-------|-------------|------|-------|
| `weaponName` | `weapon_url_name` | string | **Required.** e.g. `rubico` |
| `positiveAttributes` | `positive_attributes` | string | Comma-separated url_names |
| `negativeAttributes` | `negative_attributes` | string | Single url_name |
| `mrMax` | `mastery_rank_max` | int | 1–16 |
| `minRerolls` | `re_rolls_min` | int | 0 = no minimum |
| `maxRerolls` | `re_rolls_max` | int | No upper limit |
| `sortBy` | `sort_by` | enum | `price_asc`, `price_desc`, `positive_attr_asc`, `positive_attr_desc` |
| `buyoutPolicy` | `buyout_policy` | enum | `direct`, `with_bid` |
| `polarity` | `polarity` | enum | `madurai`, `vazarin`, etc. Omit for "any" |
| `platform` | `platform` | enum | `pc`, `ps4`, `xbox`, `switch` |
| `crossplay` | `crossplay` | string | `"true"` or `"false"` |

**Response:** `{ auctions: RivenRow[], stats: PriceStats }` or `{ errors: string[] }`

### `GET /api/estimate`

Similarity-based price estimation for a specific riven build.

| Param | Format | Required |
|-------|--------|----------|
| `weaponName` | `rubico` | Yes |
| `positiveAttributes` | `critical_chance:180.5,multishot:110.2` | Yes |
| `negativeAttribute` | `recoil:-85.3` | No |
| `rerolls` | `5` | No |
| `platform` | `pc` | No |
| `crossplay` | `true` | No |

**Response:** `{ estimate: PriceEstimate, stats: PriceStats }` or `{ errors: string[] }`

### `GET /api/riven/weapons`

Returns the cached weapon list. Each entry includes `url_name`, `item_name`, `group`, and `disposition` (1–5).

### `GET /api/riven/attributes`

Returns `{ positive: Attribute[], negative: Attribute[] }`. Optionally filtered by `weapon_group` query param.

## Cache System

The cache stores three datasets fetched from external APIs:

| Cache File | Source | Contents |
|-----------|--------|----------|
| `weapons.json` | warframe.market `/v1/riven/items` | All riven-eligible weapons |
| `attributes.json` | warframe.market `/v1/riven/attributes` | All riven stat types |
| `dispositions.json` | warframestat.us `/weapons` | Riven disposition (1–5) per weapon |

**Behavior:**
- **24-hour TTL** — Data is refreshed in background threads when stale
- **Rate limiting** — 3 req/sec to warframe.market with exponential backoff on 429s
- **Thread-safe** — Concurrent requests read from the last valid cache
- **Disposition merge** — `get_weapons()` joins disposition data into weapons at read time via case-insensitive name matching, defaulting to 3 for unmatched weapons

## Pricing Engine Pipeline

The `estimate_price()` function in `evaluation/price_estimator.py` runs a multi-step pipeline:

```
Auctions for weapon
        │
        ▼
┌─────────────────┐
│  Stat Weights   │  Top 30% auctions → stat frequency → normalized weights
└────────┬────────┘
         ▼
┌─────────────────┐
│  Build Vectors  │  Target + each auction → weighted stat vectors (0–1 normalized)
└────────┬────────┘
         ▼
┌─────────────────┐
│  Archetypes     │  Classify as Crit/Status/Hybrid/Other → filter incompatible
└────────┬────────┘
         ▼
┌─────────────────┐
│  Similarity     │  Cosine similarity + negative adjustments + reroll penalty
└────────┬────────┘
         ▼
┌─────────────────┐
│  Filter         │  Threshold ≥ 0.35, then IQR outlier removal
└────────┬────────┘
         ▼
┌─────────────────┐
│  Weighted Avg   │  Σ(price × similarity × age_factor) / Σ(similarity × age_factor)
└─────────────────┘
         │
         ▼
    PriceEstimate
    (price, confidence, comparables, weights)
```

### Age Decay

Listing staleness is penalized with price-aware half-lives:
- **High-value** (top 25% by price): 90-day half-life — expensive rivens have smaller buyer pools
- **Standard**: 30-day half-life — stale cheap listings likely indicate inaccurate pricing

## Running

```bash
pip install flask requests
python main.py
# → http://localhost:5000
```

The frontend's Vite dev server proxies `/api/*` here automatically.
