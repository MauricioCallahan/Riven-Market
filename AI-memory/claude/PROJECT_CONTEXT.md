# PROJECT_CONTEXT.md

## Project
A full-stack market analysis tool for Warframe's Riven Mod trading economy. Users search live auction data with granular filters and get similarity-based price estimates. Built for players who trade Riven Mods and want fair pricing insight.

## Architecture
Monorepo with a Python/Flask REST API (`backend/`) and a React/TypeScript SPA (`frontend/`). The frontend proxies all `/api/*` requests to Flask via Vite's dev server. The backend acts as a gateway to two external APIs (warframe.market for auctions, warframestat.us for dispositions) and runs a custom pricing engine server-side.

The backend follows a layered architecture:
- **Core**: Shared data structures and configuration.
- **Services**: Business logic and external integrations.
- **API**: HTTP routing and request/response handling.
- **Evaluation**: Domain-specific pricing and similarity engine.

## Main Modules
- `backend/api/routes.py` — Flask route definitions; maps camelCase frontend params to snake_case backend filters
- `backend/services/auction_service.py` — Search orchestration: normalize → validate → build params → call API → parse results
- `backend/services/cache_service.py` — File-based JSON cache with 24h TTL, background refresh threads, rate-limited API calls
- `backend/evaluation/` — Pricing engine (5 modules): stat weights, archetype classification, cosine similarity, reroll penalty, outlier removal
- `backend/core/models.py` — Auction data model with API-to-frontend serialization
- `backend/services/warframe_client.py` — HTTP client for warframe.market auction search endpoint
- `frontend/src/pages/Index.tsx` — Main page; manages filter state, triggers search, renders results
- `frontend/src/components/FilterSidebar.tsx` — Filter controls (weapon, attributes, platform, etc.)
- `frontend/src/components/RivenTable.tsx` — Auction results table with price statistics display

## Data Flow
User sets filters in FilterSidebar → frontend sends GET `/api/search` → `routes.py` maps params → `auction_service.py` normalizes/validates/builds query → `warframe_client.py` calls warframe.market → results parsed into `Auction` models → `compute_stats()` calculates price statistics → JSON response rendered in RivenTable.

## Key Dependencies
- Flask — lightweight Python API server
- warframe.market API v1 — live auction data source
- warframestat.us — weapon disposition data (affects riven stat ranges)
- React 18 + Vite — SPA with hot reload and `/api` proxy
- shadcn/ui + Tailwind — UI component library and styling
- @tanstack/react-query — data fetching (configured but search uses manual fetch)

## Engineering Principles
1. Backend owns all pricing logic.
2. API responses must remain stable because the frontend relies on specific JSON shapes.
3. Cache refresh must never block request handling.
4. External APIs are unreliable — all calls must be defensive (see warframe_client.py).
5. Keep API logic thin and push logic into services (auction_service.py) or evaluation.
6. The evaluation engine must have no dependency on Flask — it is a pure Python module.

## Error Handling Rules

- Validation errors return 400 with human-readable messages.
- External API failures return 502.
- Internal server errors return 500.
- Never expose stack traces in API responses.

## File Responsibilities

api/routes.py
Handles HTTP routing and request/response formatting only.
No business logic should live here.

services/auction_service.py
Owns the search pipeline:
normalize → validate → query → parse → compute stats.

evaluation/
Contains all price analysis logic. This module should remain independent of Flask.

services/warframe_client.py
Handles external API calls and retry logic.
This is the single location for all retry logic and API-level error handling. Callers should not re-implement resilience.

services/cache_service.py
Provides cached API data and background refresh logic.
Other modules should treat it as the single source of truth.

## Code Style

Python:
- Use type hints everywhere
- Prefer small functions
- Avoid nested conditionals
- All modules should be stateless where possible. Singletons like the cache live in `services/cache_service.py`.

React:
- Functional components only
- State kept in page-level components when possible
- Components should remain presentational

## System Boundaries

Frontend
- Responsible for UI state and filter controls.
- Never computes pricing logic.

Backend
- Responsible for API validation and pricing engine.

External APIs
- warframe.market: auction data
- warframestat.us: weapon dispositions


## Notes for AI Assistants
- Frontend sends camelCase params; `routes.py` maps them to snake_case for the backend — maintain this boundary
- All attribute validation uses cached API data (`cache.get_positive_attribute_names()`) — attributes are not hardcoded
- `evaluation/riven_math.py` has hardcoded base stat ranges validated against API data on cache init
- After any architectural change, flag if PROJECT_CONTEXT.md needs updating
