# Task Board

## Open

### FilterSidebar

- [ ] **UI-008** In `FilterSidebar.tsx`: (1) move the Crossplay toggle row above the Platform dropdown; (2) add spacing between the "Crossplay" label and the `<Switch>` — the current `justify-between` row has no gap, add `gap-3` or a `min-w` on the label so the switch doesn't crowd the text.
- [ ] **UI-009** In `FilterSidebar.tsx`, replace the "Filters" `<h2>` text with the site logo image (`/logo.png` or wherever the asset lives). Wrap it in an `<a>` tag pointing to `"#"` (placeholder — real URL TBD when the estimates site is created). Open in `target="_blank"`. Keep the Estimate button to the right unchanged.
- [ ] **UI-007** Add a collapse/expand toggle to `FilterSidebar`. A button (e.g. `PanelLeftClose`/`PanelLeftOpen` lucide icon) in the sidebar header collapses the sidebar to zero width (or a slim icon-only rail). The main content area (`Index.tsx` layout) must use `flex-1` / `w-full` so it fills the freed space automatically. Collapsed state lives in `Index.tsx` as a boolean and is passed as a prop; the sidebar uses a CSS transition (`transition-[width]`) for a smooth slide. The toggle button remains visible in collapsed state so users can re-open.

### Price Estimator (EstimateSheet)

- [ ] **CHART-001** Add a stock-like price range chart to the estimator or search results to visualize average/high/low pricing.
  - Display a candlestick or range bar chart (e.g. using recharts) showing `low`, `average`, and `high` platinum prices for the searched riven.
  - Data source: the price stats already returned by `/api/estimate` (or `/api/search` `stats` field — `min`, `median`, `mean`, `max`, `q1`, `q3`).
  - Placement: inside `EstimateSheet.tsx` below the Market Overview section, or as a collapsible panel in the search results area.
  - Use recharts `ComposedChart` with a `Bar` for the low→high range and a `Line` or `ReferenceLine` for the average/median. No new dependencies needed — recharts is already installed.
  - Keep it read-only and presentational; no interactivity required beyond a tooltip on hover showing exact values.



- [ ] **UI-003** In `EstimateSheet.tsx` Stat Weights section, filter out stats with 0% weight before rendering — add `.filter(([, weight]) => weight > 0)` before the `.sort()` at line 148. Zero-weight stats contribute nothing to the estimate and clutter the UI.
- [ ] **UI-004** In `EstimateSheet.tsx` Market Overview section: (1) remove the `<StatItem label="Start Bid" ...>` row entirely; (2) for Buyout and TopBid, only show the median value — remove the min/max (Q1/Q4) flanks. Update `StatItem` or render inline so only median is displayed for those two fields.
- [ ] **UI-005** In `EstimateSheet.tsx`, wrap the confidence `<Badge>` in a `<Tooltip>` that explains the rating on hover. Tooltip text: **High** — 10+ comparable listings found; **Medium** — 5–9 comparables; **Low** — fewer than 5 comparables. Confidence is determined by `_confidence_level()` in `backend/evaluation/price_estimator.py`. Use the existing shadcn/ui `Tooltip`/`TooltipProvider`/`TooltipContent` components.
- [ ] **UI-006** In `EstimateSheet.tsx`, give the archetype `<Badge>` a color per build type (like confidence), and wrap it in a `<Tooltip>` explaining what it means on hover.
  - Color map (add `archetypeColor` alongside `confidenceColor`): **crit** → blue, **status** → orange/amber, **hybrid** → purple, **other** → default/muted.
  - Tooltip descriptions: **Crit** — focuses on critical chance/damage stats; **Status** — focuses on status chance and elemental damage; **Hybrid** — mix of crit and status stats; **Other** — utility or raw damage build.
  - Archetypes come from `backend/evaluation/archetypes.py`. Use shadcn/ui `Tooltip`/`TooltipProvider`/`TooltipContent`.

### Table & Search

- [x] **UI-001** When auction results hit the 500-result cap, show a "Showing 500 of X total" indicator. The backend already limits results; this just surfaces the truncation so users know to narrow filters.
- [ ] **UI-002** Remove buyout price, starting bid, and top bid columns from RivenTable — these will be surfaced inside the price estimator feature instead.
- [ ] **SORT-001** Implement pos/neg attribute sorting client-side — `sort_by: positive_attr_asc/desc` is not supported by the warframe.market API (returns 500). Rank auctions locally by top percentile value among positive attributes (penalize by negative attribute percentiles). Requires attribute stat data (min/max/avg per attribute).

### Validation

- [x] **VAL-001** Enforce `mastery_rank_min = 8` floor on the mastery rank input — rivens require MR 8 minimum. Clamp or show a validation error in both frontend and backend `validate_filters()`.
- [x] **VAL-002** Validate that `mastery_rank_min <= mastery_rank_max` when both are set — backend check already existed; added frontend inline warning in FilterSidebar + backend test.

### Frontend Reliability

- [ ] **TEST-001** `parseAttributeDisplay` in `frontend/src/types/estimate.ts` needs extensive unit tests — if it silently fails, `/api/estimate` is never called (handleEstimate bails on empty `positiveParsed`). Edge cases: multi-word stat names, negative values, zero values, malformed/missing `%`, extra whitespace.

### Backend Reliability

- [x] **RELY-004** Structured logging — replaced all `print()` in production backend code with `logging` module. `main.py` already had `logging.basicConfig` with `LOG_LEVEL` env var (default changed to INFO). Added per-request log line in routes.py. Test files retain `print()` for diagnostics.
- [x] **CACHE-001** Add result-level search cache to backend for warframe.market outage fallback.
  - **cache.py** — Add `SearchResultCache` class (or extend existing singleton). File-based JSON in `cache/search_results/`. TTL: 24h. No Flask imports. Methods: `get(key) -> dict | None`, `set(key, params, auctions)`. Write must be non-blocking (background thread or fire-and-forget).
  - **rivens.py** — After params are validated/built, generate a deterministic SHA256 cache key from sorted params. Happy path: call API → write result cache in background → return fresh data with `stale: false, cached_at: null`. Failure path: attempt cache lookup → if hit and within TTL, return with `stale: true, cached_at: <ISO>` → if miss, re-raise 502 as before. No retries in rivens.py — that stays in api_client.py.
  - **server.py** — Ensure `/api/search` response always includes `stale` (bool, default false) and `cached_at` (ISO string or null) — stable shape regardless of code path.
  - **Cache key format**: `sha256(json.dumps(sorted_params, sort_keys=True))` where params include weapon, attributes, platform, sort, filters. Normalize before hashing (strip None values, sort lists).
- [x] **RELY-001** Request deduplication — identical concurrent searches collapse into a single warframe.market API call.
  - In `cache.py`, maintain a `dict[str, threading.Event]` of in-flight keys. Before dispatching an API call, check if the same key is already in-flight; if so, wait on the Event and return the stored result. On completion, store result, set Event, clean up entry.
  - Use the same cache key format as CACHE-001 (SHA256 of sorted params).
  - Must not block unrelated searches — only deduplicates identical concurrent ones.
  - No new module-level singletons — attach state to the existing cache singleton.
  - Commit separately.
- [x] **RELY-002** Pricing confidence signal — add `sample_size` and `confidence` to evaluation output.
  - In the `evaluation/` module (not `server.py`), compute `sample_size: int` and `confidence: "low" | "medium" | "high"` alongside existing price stats. Thresholds as constants: low < 5, medium 5–15, high > 15.
  - Bubble both fields up through `rivens.py` and into the `/api/search` response shape.
  - Fields must always be present (never absent), defaulting to `sample_size: 0, confidence: "low"` on empty results.
  - No Flask imports in the evaluation module.
  - Commit separately.
- [x] **RELY-003** Disposition staleness detection — surface stale disposition data in the search response.
  - In `cache.py`, record a `last_updated: datetime` timestamp whenever disposition data is successfully refreshed from warframestat.us.
  - Expose `cache.get_disposition_age() -> timedelta | None`.
  - Add `disposition_stale: bool` to `/api/search` response — `true` if disposition data is older than 7 days or unavailable. Informational only; never block searches.
  - Field must always be present in response.
  - Commit separately.
- [ ] **PERF-001** Cache auction search results in `/api/estimate` (short TTL ~60s, keyed by weapon+platform+crossplay) — currently makes a live upstream call on every request.

### Backend / API

- [ ] **API-001** Investigate `buyout_policy: with_bid` — currently removed from dropdown because it returns 400, but bidding auctions are a real warframe.market feature. Determine the correct API parameter/value and re-add support once confirmed working.

## Planned (Larger Features)

- [ ] **EST-001** Exact Estimate — attribute range input with platinum budget ghost value.
  - **UI** — Add a new section or tab inside `EstimateSheet` (or a separate panel) called "Exact Estimate". For each selected positive/negative attribute show two number inputs: min value and max value (e.g. crit chance 150–200%). Include a "Budget" input field; its placeholder text is the estimated cost derived from the selected attribute ranges (updates live/on-blur as a ghost value). Use the same attribute list already loaded in the sidebar.
  - **Backend** — Extend `/api/estimate` (or add `/api/estimate/range`) to accept attribute ranges: `positiveAttributes=critical_chance:150:200,multishot:80:120`. Pipeline logic: find auctions where each attribute value falls within [min, max], then run the existing similarity + weighted-average price pipeline on that filtered set. Return the same `PriceEstimate` shape.
  - **Budget signal** — Populate the budget input's placeholder with the estimated price. If the user types a value lower than the estimate, show a subtle amber warning "below market estimate".
  - Commit backend and frontend separately.
- [ ] Mobile-responsive layout — collapsible sidebar/drawer for small screens

---

## Completed

- [x] Price estimation UI — frontend for `/api/estimate`
- [x] **PROD-003** Load `python-dotenv` in `main.py` (`load_dotenv()`) — dependency installed but never called
- [x] **PROD-001** Add `/api/health` endpoint returning cache-loaded status
- [x] **QUAL-002** Add global Flask error handlers (`@app.errorhandler(500)` etc.) returning JSON instead of HTML
- [x] **SEC-006/007** Add input length bounds (`weapon_url_name` ≤ 100 chars, attribute strings ≤ 500 chars) and missing range validation: `mastery_rank_min` (0–16), `re_rolls_max` (≥ 0), `mod_rank` (0–8)
- [x] **\_parse_attr_pairs** rejects `float("inf")` and `float("nan")` — add explicit check after `float()` conversion
- [x] **SEC-005** Initialize `flask-cors` in `server.py` with explicit allowed origins
- [x] **SEC-004** Remove `print(f"[DEBUG] ...")` in `rivens.py:91` or gate behind `logging.debug`
- [x] **SEC-003** Raw exception string leaked to clients in `rivens.py:171` — log internally, return generic message
- [x] **SEC-001** Gate `debug=True` behind `FLASK_DEBUG` env var in `main.py`
- [x] **SEC-002** Rate limiting — `cache.py` already rate-limits upstream API calls
- [x] **QUAL-001** `_int_or_none` in `server.py` crashes on non-numeric input — wrap `int(v)` in `try/except`
- [x] **SCOPE-001** Verify companion weapon rivens appear in the weapon dropdown
- [x] Fix `index.html` metadata — replaced all Lovable placeholders with Riven Market
- [x] Call `validate_base_stats()` on cache init to catch API stat drift
- [x] Remove unused shadcn/ui components (34 files), hooks, and dead CSS
- [x] Prune unused npm dependencies (29 packages + lovable-tagger)
- [x] Fix playwright.config.ts — replaced Lovable scaffold with standard config
- [x] Implement usage progress bar via status line
- [x] Restructure project into backend/frontend monorepo
- [x] Rename gitignore → .gitignore
- [x] Commit and push to origin/main
- [x] **GIT-001** Add `pytest` test coverage for `validate_filters`, `normalize_filters`, `_int_or_none`, `_parse_attr_pairs` — see edge case matrix from security review
- [x] Enable stricter TypeScript config (incremental: `strict`, `noImplicitAny`, `strictNullChecks`)

