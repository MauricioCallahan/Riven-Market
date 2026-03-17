import type { RivenRow, PriceStats } from "@/components/RivenTable";

/** A comparable auction returned by the pricing pipeline. */
export interface ComparableAuction {
  similarity: number;
  archetype: string;
  auctionId: string;
  weapon: string;
  rivenName: string;
  startBid: number | null;
  buyout: number | null;
  topBid: number | null;
  mr: number;
  rank: number;
  rerolls: number;
  polarity: string;
  listed: string;
  lastUpdated: string;
  positiveAttributes: string[];
  negativeAttributes: string[];
  url: string;
}

export interface EstimateData {
  estimatedPrice: number;
  confidence: "high" | "medium" | "low";
  comparableCount: number;
  archetype: string;
  comparables: ComparableAuction[];
  statWeights: Record<string, number>;
}

export interface EstimateResponse {
  estimate: EstimateData;
  stats: PriceStats;
}

/**
 * Parses the backend's `to_display()` format back into url_name + value.
 *
 * Backend format (models.py:14-15): `f"{url_name.replace('_',' ')} {value:+.1f}%"`
 * Example: "critical chance +180.5%" -> { urlName: "critical_chance", value: 180.5 }
 */
export function parseAttributeDisplay(
  display: string,
): { urlName: string; value: number } | null {
  const match = display.match(/^(.+?)\s+([+-][\d.]+)%$/);
  if (!match) {
    console.warn(`[parseAttributeDisplay] failed to parse: "${display}"`);
    return null;
  }
  const urlName = match[1].trim().replace(/ /g, "_");
  const value = parseFloat(match[2]);
  if (isNaN(value)) return null;
  return { urlName, value };
}
