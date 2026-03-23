import { ExternalLink } from "lucide-react";
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip as ReTooltip,
  ResponsiveContainer,
} from "recharts";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import type { EstimateResponse, ComparableAuction } from "@/types/estimate";
import type { FieldStats, PriceStats } from "@/components/RivenTable";

interface EstimateSheetProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  result: EstimateResponse | null;
  status: "idle" | "loading" | "success" | "error";
  error: string;
  rivenName: string;
  weaponName: string;
}

const confidenceColor: Record<string, string> = {
  high: "bg-stat-positive/15 text-stat-positive border-stat-positive/30",
  medium: "bg-warning/15 text-warning border-warning/30",
  low: "bg-destructive/15 text-destructive border-destructive/30",
};

const confidenceTooltip: Record<string, string> = {
  high: "High confidence: 2+ verified bids from distinct reputable bidders",
  medium: "Medium confidence: 1 verified bid from a reputable bidder",
  low: "Low confidence: no verified bid activity, using buyout price fallback",
};

const archetypeColor: Record<string, string> = {
  crit: "bg-primary/15 text-primary border-primary/30",
  status: "bg-warning/15 text-warning border-warning/30",
  hybrid: "bg-accent/15 text-accent border-accent/30",
  other: "",
};

const archetypeTooltip: Record<string, string> = {
  crit: "Focuses on critical chance and critical damage stats",
  status: "Focuses on status chance and elemental damage",
  hybrid: "Mix of critical and status stats",
  other: "Utility or raw damage build",
};

function formatPrice(n: number) {
  return "~" + Math.round(n).toLocaleString() + "p";
}

function formatNum(n: number | null) {
  if (n == null) return "\u2014";
  return n.toLocaleString() + "p";
}

function StatItem({
  label,
  field,
  medianOnly = false,
}: {
  label: string;
  field: FieldStats | null;
  medianOnly?: boolean;
}) {
  if (!field) return null;
  return (
    <div className="flex flex-col items-center gap-0.5">
      <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      {medianOnly ? (
        <span className="text-xs font-medium">{formatNum(field.median)}</span>
      ) : (
        <span className="text-xs">
          {formatNum(field.min)} /{" "}
          <span className="font-medium">{formatNum(field.median)}</span> /{" "}
          {formatNum(field.max)}
        </span>
      )}
    </div>
  );
}

function LoadingSkeleton() {
  return (
    <div className="flex flex-col gap-6 pt-2">
      <div className="flex flex-col items-center gap-3">
        <Skeleton className="h-10 w-32" />
        <div className="flex gap-2">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <Skeleton className="h-4 w-48" />
      </div>
      <Skeleton className="h-20 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}

export default function EstimateSheet({
  open,
  onOpenChange,
  result,
  status,
  error,
  rivenName,
  weaponName,
}: EstimateSheetProps) {
  const estimate = result?.estimate;
  const stats = result?.stats;

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="sm:max-w-2xl overflow-y-auto">
        <SheetHeader>
          <SheetTitle>Price Estimate</SheetTitle>
          <SheetDescription>
            {weaponName && rivenName
              ? `${weaponName} \u2014 ${rivenName}`
              : "Analyzing riven..."}
          </SheetDescription>
        </SheetHeader>

        {status === "loading" && <LoadingSkeleton />}

        {status === "error" && (
          <div className="mt-6 rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
            {error || "Failed to get price estimate."}
          </div>
        )}

        {status === "success" && estimate && (
          <div className="flex flex-col gap-6 pt-2">
            {/* Hero — price range */}
            <div className="flex flex-col items-center gap-2 py-4 rounded-lg border border-border bg-muted/30">
              {estimate.priceHigh > 0 ? (
                <div className="flex flex-col items-center gap-0.5">
                  <span className="text-3xl font-bold tracking-tight">
                    {Math.round(estimate.priceLow)}–{Math.round(estimate.priceHigh)}p
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {formatPrice(estimate.estimatedPrice)}
                  </span>
                </div>
              ) : estimate.estimatedPrice > 0 ? (
                <span className="text-3xl font-bold tracking-tight">
                  {formatPrice(estimate.estimatedPrice)}
                </span>
              ) : (
                <span className="text-lg text-muted-foreground">
                  No price estimate available
                </span>
              )}
              <div className="flex items-center gap-2">
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="outline"
                      className={confidenceColor[estimate.confidence] ?? ""}
                    >
                      {estimate.confidence} confidence
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    {confidenceTooltip[estimate.confidence]}
                  </TooltipContent>
                </Tooltip>
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Badge
                      variant="outline"
                      className={`capitalize ${archetypeColor[estimate.archetype] ?? ""}`}
                    >
                      {estimate.archetype}
                    </Badge>
                  </TooltipTrigger>
                  <TooltipContent>
                    {archetypeTooltip[estimate.archetype] ?? "Build type"}
                  </TooltipContent>
                </Tooltip>
              </div>
              <span className="text-xs text-muted-foreground">
                {estimate.bidConfidenceTier <= 2 ? (
                  <>
                    Based on {estimate.validatedBidCount} verified bid
                    {estimate.validatedBidCount !== 1 ? "s" : ""} across{" "}
                    {estimate.auctionsWithBids} auction
                    {estimate.auctionsWithBids !== 1 ? "s" : ""}
                  </>
                ) : (
                  <>
                    Based on {estimate.comparableCount} comparable listing
                    {estimate.comparableCount !== 1 ? "s" : ""} (no bid activity)
                  </>
                )}
              </span>
            </div>

            {/* Stat Weights */}
            {Object.keys(estimate.statWeights).length > 0 && (
              <div className="flex flex-col gap-1.5">
                <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                  Stat Weights
                </h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(estimate.statWeights)
                    .filter(([, weight]) => weight >= 0.005)
                    .sort(([, a], [, b]) => b - a)
                    .map(([stat, weight]) => (
                      <span
                        key={stat}
                        className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/50 px-2 py-0.5 text-xs"
                      >
                        <span className="text-foreground">
                          {stat.replace(/_/g, " ")}
                        </span>
                        <span className="text-muted-foreground">
                          {(weight * 100).toFixed(0)}%
                        </span>
                      </span>
                    ))}
                </div>
              </div>
            )}

            {/* Market Stats */}
            {stats && stats.count > 0 && (() => {
              const chartData = [
                stats.buyout && { name: "Buyout", low: stats.buyout.min, range: stats.buyout.max - stats.buyout.min, median: stats.buyout.median },
                stats.topBid && { name: "Top Bid", low: stats.topBid.min, range: stats.topBid.max - stats.topBid.min, median: stats.topBid.median },
              ].filter(Boolean) as { name: string; low: number; range: number; median: number }[];
              chartData.sort((a, b) => a.low - b.low);
              return (
                <div className="flex flex-col gap-1.5">
                  <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    Market Overview ({stats.count} auctions)
                  </h3>
                  <div className="flex items-center justify-around rounded-md border border-border bg-muted/30 py-2">
                    <StatItem label="Buyout" field={stats.buyout} medianOnly />
                    <StatItem label="Top Bid" field={stats.topBid} medianOnly />
                  </div>
                  {chartData.length > 0 && (
                    <div className="rounded-md border border-border bg-muted/30 pt-2 pb-1">
                      <ResponsiveContainer width="100%" height={90}>
                        <ComposedChart data={chartData} margin={{ top: 4, right: 16, bottom: 0, left: 16 }} stackOffset="none">
                          <XAxis dataKey="name" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} />
                          <YAxis hide />
                          <ReTooltip
                            formatter={(value: number, name: string) => {
                              if (name === "low") return [`${value}p`, "Min"];
                              if (name === "range") return [`${value}p`, "Range (min→max)"];
                              if (name === "median") return [`${value}p`, "Median"];
                              return [value, name];
                            }}
                            contentStyle={{ fontSize: 11 }}
                          />
                          <Bar dataKey="low" stackId="range" fill="transparent" isAnimationActive={false} />
                          <Bar dataKey="range" stackId="range" fill="hsl(var(--muted-foreground))" opacity={0.3} radius={[3, 3, 3, 3]} isAnimationActive={false} />
                          <Line dataKey="median" dot={{ r: 4, fill: "hsl(var(--primary))" }} stroke="hsl(var(--primary))" strokeWidth={2} isAnimationActive={false} />
                        </ComposedChart>
                      </ResponsiveContainer>
                    </div>
                  )}
                </div>
              );
            })()}

            {/* Comparables Table */}
            <div className="flex flex-col gap-1.5">
              <h3 className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Comparable Listings
              </h3>
              {estimate.comparables.length === 0 ? (
                <div className="rounded-md border border-border bg-muted/30 p-4 text-center text-sm text-muted-foreground">
                  Not enough comparable listings found.
                </div>
              ) : (
                <div className="rounded-md border border-border overflow-auto max-h-[400px]">
                  <table
                    className="w-full text-xs border-collapse"
                    style={{ fontFeatureSettings: "'tnum'" }}
                  >
                    <thead className="sticky top-0 bg-table-header z-10">
                      <tr>
                        <th className="py-1.5 px-2 text-left font-medium border-b border-border">
                          <Tooltip>
                            <TooltipTrigger asChild>
                              <span className="cursor-help border-b border-dotted border-muted-foreground">Sim</span>
                            </TooltipTrigger>
                            <TooltipContent>
                              Similarity score — how closely this listing matches your riven's stat combination. Capped at 100%.
                            </TooltipContent>
                          </Tooltip>
                        </th>
                        <th className="py-1.5 px-2 text-left font-medium border-b border-border">
                          Riven
                        </th>
                        <th className="py-1.5 px-2 text-right font-medium border-b border-border">
                          Buyout
                        </th>
                        <th className="py-1.5 px-2 text-right font-medium border-b border-border">
                          Bid
                        </th>
                        <th className="py-1.5 px-2 text-left font-medium border-b border-border">
                          Attributes
                        </th>
                        <th className="py-1.5 px-2 text-center font-medium border-b border-border">
                          Re
                        </th>
                        <th className="py-1.5 px-2 text-left font-medium border-b border-border">
                          Listed
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {estimate.comparables.map(
                        (c: ComparableAuction, i: number) => (
                          <tr
                            key={c.auctionId}
                            className={`border-b border-border ${i % 2 === 0 ? "bg-card" : "bg-muted"}`}
                          >
                            <td className="py-1.5 px-2 whitespace-nowrap">
                              {Math.min(c.similarity * 100, 100).toFixed(1)}%
                            </td>
                            <td className="py-1.5 px-2 whitespace-nowrap">
                              <a
                                href={c.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 hover:underline hover:text-primary"
                              >
                                {c.rivenName}
                                <ExternalLink
                                  size={10}
                                  className="opacity-50"
                                />
                              </a>
                            </td>
                            <td className="py-1.5 px-2 text-right whitespace-nowrap">
                              {formatNum(c.buyout)}
                            </td>
                            <td className="py-1.5 px-2 text-right whitespace-nowrap">
                              {c.startBid != null ? formatNum(c.startBid) : null}
                            </td>
                            <td className="py-1.5 px-2">
                              <span>
                                {c.positiveAttributes.map((s, j) => (
                                  <span key={j} className="text-stat-positive">
                                    {s}
                                    {j < c.positiveAttributes.length - 1
                                      ? ", "
                                      : ""}
                                  </span>
                                ))}
                                {c.negativeAttributes.length > 0 && (
                                  <>
                                    {" "}
                                    {c.negativeAttributes.map((s, j) => (
                                      <span
                                        key={j}
                                        className="text-stat-negative"
                                      >
                                        {s}
                                        {j < c.negativeAttributes.length - 1
                                          ? ", "
                                          : ""}
                                      </span>
                                    ))}
                                  </>
                                )}
                              </span>
                            </td>
                            <td className="py-1.5 px-2 text-center whitespace-nowrap">
                              {c.rerolls}
                            </td>
                            <td className="py-1.5 px-2 whitespace-nowrap text-muted-foreground">
                              {c.listed}
                            </td>
                          </tr>
                        ),
                      )}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
