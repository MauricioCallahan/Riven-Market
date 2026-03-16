# Frontend — Riven Market UI

React-based single-page application for searching and analyzing Warframe riven mod auctions. Built with TypeScript, Tailwind CSS, and shadcn/ui components.

## Tech Stack

| Technology | Purpose |
|-----------|---------|
| React 18 | UI framework |
| TypeScript | Type safety across components and API contracts |
| Vite | Dev server with HMR, proxies `/api/*` to Flask backend |
| Tailwind CSS | Utility-first styling |
| shadcn/ui | Accessible component primitives (Popover, Command, Switch, Badge) |
| Framer Motion | Animated table transitions |
| Lucide React | Icon library |

## Component Architecture

```
Index.tsx (page)
│
│  Owns all state: filters, results, status
│  Fetches weapons + attributes on mount
│  Calls /api/search on user action
│
├── FilterSidebar.tsx
│   │
│   │  Searchable weapon combobox (grouped by type)
│   │  Multi-select positive attributes (max 3, badge pills)
│   │  Single-select negative attribute
│   │  Numeric inputs: MR range, reroll range, mod rank
│   │  Dropdowns: sort, buyout policy, polarity, platform
│   │  Crossplay toggle (auto-triggers re-search)
│   │
│   └── ui/ (shadcn primitives)
│       ├── command.tsx    — searchable list (cmdk)
│       ├── popover.tsx    — dropdown containers
│       ├── switch.tsx     — crossplay toggle
│       └── badge.tsx      — selected attribute pills
│
└── RivenTable.tsx
    │
    │  Sortable results table with animated row transitions
    │  Stats bar: min/max/mean/median for buyout, start bid, top bid
    │  Click row → opens auction on warframe.market
    │  Loading/error/empty states
    │
    └── Columns: Weapon, Riven Name, Start Bid, Buyout, Top Bid,
        Listed, Updated, Positives, Negatives, MR, Rank, Rerolls, Polarity
```

## Key Interfaces

### `FilterValues` — Single source of truth for all filter state

```typescript
interface FilterValues {
  weaponName: string;            // weapon url_name
  weaponRivenType: string;       // drives attribute filtering
  positiveAttributes: string[];  // max 3 url_names
  negativeAttributes: string;    // max 1 url_name
  mrMin: string;
  mrMax: string;
  minRerolls: string;
  maxRerolls: string;
  modRank: string;
  sortBy: string;
  buyoutPolicy: string;
  polarity: string;
  platform: string;              // pc, ps4, xbox, switch
  crossplay: string;             // "true" | "false"
}
```

### `RivenRow` — Parsed auction data from backend

```typescript
interface RivenRow {
  id: string;
  weapon: string;
  rivenName: string;
  startBid: number | null;
  buyout: number | null;
  topBid: number | null;
  listed: string;
  lastUpdated: string;
  positiveAttributes: string[];
  negativeAttributes: string[];
  mr: number;
  rank: number;
  rerolls: number;
  polarity: string;
  auctionId: string;   // used to build warframe.market auction URL
}
```

## Dynamic Attribute Filtering

Attributes are fetched once on mount and filtered client-side based on the selected weapon's `riven_type`. Each attribute has an `exclusive_to` field:

- `null` → available for all weapon types
- `["rifle", "shotgun"]` → only shown when a rifle or shotgun is selected

This prevents invalid combinations (e.g., selecting a melee-only stat for a rifle riven).

## Running

```bash
npm install
npm run dev
# → http://localhost:8080
```

Requires the backend running on `:5000` — Vite proxies `/api/*` automatically.

## Scripts

| Command | Description |
|---------|-------------|
| `npm run dev` | Start dev server with HMR |
| `npm run build` | Production build |
| `npm run lint` | Run ESLint |
| `npm run test` | Run Vitest |
| `npm run test:watch` | Run Vitest in watch mode |
