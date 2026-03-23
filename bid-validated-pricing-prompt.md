# Bid-Validated Riven Price Estimator

## Context

We are building a price estimation system for Warframe Riven mods using the warframe.market API. The core problem is that auction listings alone are unreliable — sellers can post any price they want, and there's no way to tell a legitimate listing from a troll listing just by looking at starting/buyout prices. Our solution is to use **bid data** as the primary price signal, since bids represent what players are actually willing to pay.

## API Endpoints

- **Search auctions:** `GET https://api.warframe.market/v1/auctions/search?type=riven&weapon_url_name={weapon}` — returns auction listings with starting_price, buyout_price, seller info, auction_id, and riven attributes. 
- **Fetch bids:** `GET https://api.warframe.market/v1/auctions/entry/{auction_id}/bids` — publicly accessible, no auth required. Returns bid history with bid value, bidder user info (id, reputation, ingame_name), and timestamps.

**Rate limit:** 3 requests/sec max. All requests require `Platform: pc` and `Language: en` headers.

## Bid Response Shape

```json
{
  "payload": {
    "bids": [
      {
        "value": 400,
        "created": "2026-03-19T09:35:17.000+00:00",
        "updated": "2026-03-19T09:35:17.000+00:00",
        "auction": "69b854707ce7760008c327a9",
        "user": {
          "reputation": 15,
          "platform": "pc",
          "locale": "zh-hans",
          "last_seen": "2026-03-22T14:00:16.434+00:00",
          "ingame_name": "FateccPure",
          "slug": "fateccpure",
          "crossplay": true,
          "status": "offline",
          "id": "60848617e68e920140cbe913",
          "region": "en",
          "avatar": null
        },
        "id": "69bbc3554a411b0007889f6b"
      }
    ]
  }
}
```

## Architecture: Split API Calls Between User Actions

To stay within rate limits, bid fetching is split across two user interactions:

1. **On listing selection** — user clicks a specific riven listing in the UI. Fetch bids for that single auction (`/v1/auctions/entry/{auction_id}/bids`).

2. **On estimator button press** — user clicks the "Estimate Price" button. Fetch bids for remaining comparable auctions from search results. Pre-filter auctions with obviously troll buyout prices before fetching to minimize API calls.

### Per-Session Bid Cache

- Cache bid responses in memory as a dictionary keyed by `auction_id`.
- Cache is per-session only — no persistence. Riven auctions are live and bids can arrive at any time, so stale data from a previous session would mislead the estimator.
- If bids for an auction are already cached (e.g., from the listing selection step), skip the fetch during the estimation step.

## Tiered Confidence System 

NOTE: Tiered Confidence system is already implemented edit to follow this prompt.

Not all rivens have active bid markets. Popular weapons (Acceltra, Rubico) will have competitive bidding. Niche weapons (Stug, Hind) may have zero bids across all listings. The estimator must handle both gracefully using a tiered fallback system:

### Tier 1 — High Confidence (bid-validated)

**Criteria:** Auction has 2+ bids from distinct users (different `user.id` from each other AND from the seller) where bidders have reputation > 0.

**Validation filters:**
- Bids are from distinct users (no self-bidding — bidder ID ≠ seller ID)
- Bidders have reputation > 0
- Bids are competitive (incremental increases, not a single massive jump)
- Bid timestamps are spread out (not all placed within seconds of each other, which could indicate manipulation)

**Price signal:** Use the highest bid value from validated auctions. This represents actual willingness to pay.

### Tier 2 — Medium Confidence (single bid)

**Criteria:** Auction has exactly 1 bid from a reputable user (reputation > 0, user ID ≠ seller ID).

**Price signal:** Use the bid value but widen the estimated price range to reflect less competitive price discovery.

### Tier 3 — Low Confidence (no bids, fallback)

**Criteria:** No auctions have any bids, or all bids fail validation.

**Price signal:** Fall back to buyout prices from auction search results with:
- IQR-based outlier removal to strip troll listings
- Seller reputation weighting (higher rep sellers' prices weighted more)

### Output

The estimator should return:
- **Estimated price range** (low - high)
- **Confidence tier** (1, 2, or 3)
- **Supporting data:** number of auctions analyzed, number of validated bids found, bid values used
- Surface the confidence tier to the user in the UI. Example: "Estimated: 20-40p (high confidence, 6 verified bids)" vs "Estimated: 15-50p (low confidence, no bid activity)"

## Implementation Notes

- This system lives in `evaluation/pricing.py`
- Respect the 3 req/sec rate limit — add appropriate sleep/throttling between bid fetches during the estimation step
- The confidence tier will feed into the planned Buy vs. Roll calculator — high confidence makes that calculation trustworthy, low confidence means the recommendation should be caveated
