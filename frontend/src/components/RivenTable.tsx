import { AnimatePresence, motion } from "framer-motion";
import { ExternalLink, Loader2 } from "lucide-react";

export interface FieldStats {
  min: number;
  max: number;
  mean: number;
  median: number;
}

export interface PriceStats {
  count: number;
  buyout: FieldStats | null;
  startBid: FieldStats | null;
  topBid: FieldStats | null;
}

export interface RivenRow {
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
  auctionId: string;
  url: string;
}

interface RivenTableProps {
  rows: RivenRow[];
  stats: PriceStats | null;
  status: "idle" | "loading" | "success" | "error";
  error?: string;
  selectedId: string | null;
  onRowSelect: (id: string | null) => void;
}

const columns = [
  { key: "weapon", label: "Weapon", width: "120px", align: "left" as const },
  {
    key: "rivenName",
    label: "Riven Name",
    width: "140px",
    align: "left" as const,
  },
  {
    key: "startBid",
    label: "Start Bid",
    width: "80px",
    align: "right" as const,
  },
  { key: "buyout", label: "Buyout", width: "80px", align: "right" as const },
  { key: "topBid", label: "Top Bid", width: "80px", align: "right" as const },
  { key: "listed", label: "Listed", width: "100px", align: "left" as const },
  {
    key: "lastUpdated",
    label: "Last Updated",
    width: "100px",
    align: "left" as const,
  },
  {
    key: "attributes",
    label: "Attributes",
    width: undefined,
    align: "left" as const,
  },
  { key: "mr", label: "MR", width: "50px", align: "center" as const },
  { key: "rank", label: "Rank", width: "50px", align: "center" as const },
  { key: "rerolls", label: "Rerolls", width: "60px", align: "center" as const },
  {
    key: "polarity",
    label: "Polarity",
    width: "70px",
    align: "center" as const,
  },
];

function formatNum(n: number | null) {
  if (n == null) return "—";
  return n.toLocaleString() + "p";
}

function StatItem({
  label,
  field,
}: {
  label: string;
  field: FieldStats | null;
}) {
  if (!field) return null;
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      <span>{formatNum(field.min)}</span>
      <span className="text-muted-foreground">/</span>
      <span className="font-medium">{formatNum(field.median)}</span>
      <span className="text-muted-foreground">/</span>
      <span>{formatNum(field.max)}</span>
    </span>
  );
}

export default function RivenTable({
  rows,
  stats,
  status,
  error,
  selectedId,
  onRowSelect,
}: RivenTableProps) {
  const handleRowClick = (id: string) =>
    onRowSelect(id === selectedId ? null : id);

  // Hide the Weapon column when all visible rows share the same weapon — it's redundant
  // when the user searched for a specific weapon. Show it when the results are mixed.
  const showWeaponCol =
    rows.length === 0 || rows.some((r) => r.weapon !== rows[0].weapon);

  const visibleColumns = showWeaponCol
    ? columns
    : columns.filter((c) => c.key !== "weapon");

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0">
      <div className="flex-1 overflow-auto">
        <table
          className="w-full border-collapse text-sm"
          style={{ fontFeatureSettings: "'tnum'" }}
        >
          <thead className="sticky top-0 z-10">
            <tr className="bg-table-header">
              {visibleColumns.map((col) => (
                <th
                  key={col.key}
                  className="py-2 px-3 font-medium text-foreground border-b border-border whitespace-nowrap"
                  style={{
                    width: col.width,
                    minWidth: col.width,
                    textAlign: col.align,
                    ...(col.key === "attributes" ? { width: "100%" } : {}),
                  }}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isSelected = row.id === selectedId;
              return (
                <tr
                  key={row.id}
                  onClick={() => handleRowClick(row.id)}
                  className={`border-b border-border transition-colors duration-150 cursor-pointer ${
                    isSelected
                      ? "bg-row-selected"
                      : i % 2 === 0
                        ? "bg-card"
                        : "bg-muted"
                  } ${!isSelected ? "hover:bg-row-hover" : ""}`}
                >
                  {showWeaponCol && (
                    <td className="py-2 px-3 whitespace-nowrap">{row.weapon}</td>
                  )}
                  <td className="py-2 px-3 whitespace-nowrap">
                    <a
                      href={row.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      className="group/link inline-flex items-center gap-1 rounded px-1 -mx-1 transition-all hover:underline hover:text-primary hover:bg-primary/10"
                    >
                      {row.rivenName}
                      <ExternalLink
                        size={12}
                        className="opacity-0 group-hover/link:opacity-100 transition-opacity"
                      />
                    </a>
                  </td>
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    {formatNum(row.startBid)}
                  </td>
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    {formatNum(row.buyout)}
                  </td>
                  <td className="py-2 px-3 text-right whitespace-nowrap">
                    {formatNum(row.topBid)}
                  </td>
                  <td className="py-2 px-3 whitespace-nowrap text-muted-foreground">
                    {row.listed}
                  </td>
                  <td className="py-2 px-3 whitespace-nowrap text-muted-foreground">
                    {row.lastUpdated}
                  </td>
                  <td className="py-2 px-3">
                    <span>
                      {row.positiveAttributes.map((s, j) => (
                        <span key={j} className="text-stat-positive">
                          {s}
                          {j < row.positiveAttributes.length - 1 ? ", " : ""}
                        </span>
                      ))}
                      {row.negativeAttributes.length > 0 && (
                        <>
                          {" "}
                          {row.negativeAttributes.map((s, j) => (
                            <span key={j} className="text-stat-negative">
                              {s}
                              {j < row.negativeAttributes.length - 1
                                ? ", "
                                : ""}
                            </span>
                          ))}
                        </>
                      )}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center whitespace-nowrap">
                    {row.mr}
                  </td>
                  <td className="py-2 px-3 text-center whitespace-nowrap">
                    {row.rank}
                  </td>
                  <td className="py-2 px-3 text-center whitespace-nowrap">
                    {row.rerolls}
                  </td>
                  <td className="py-2 px-3 text-center whitespace-nowrap capitalize">
                    {row.polarity}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {status === "idle" && rows.length === 0 && (
          <div className="flex items-center justify-center h-64 text-muted-foreground text-sm">
            Configure filters and press Search to load results.
          </div>
        )}
      </div>

      {/* Stats Bar */}
      {stats && stats.count > 0 && (
        <div className="flex items-center gap-6 px-4 py-1.5 border-t border-border bg-muted/50 text-xs">
          {stats.count === 500 ? (
            <span className="text-warning font-medium">
              500+ auctions (results capped — narrow filters)
            </span>
          ) : (
            <span className="text-muted-foreground font-medium">
              {stats.count} auctions
            </span>
          )}
          <StatItem label="Buyout" field={stats.buyout} />
          <StatItem label="Start Bid" field={stats.startBid} />
          <StatItem label="Top Bid" field={stats.topBid} />
          <span className="text-muted-foreground ml-auto">
            min / median / max
          </span>
        </div>
      )}

      {/* Status Bar */}
      <div className="h-8 min-h-[32px] flex items-center px-4 border-t border-border bg-background text-xs text-muted-foreground">
        <AnimatePresence mode="wait">
          {status === "loading" && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex items-center gap-1.5"
            >
              <Loader2 size={12} className="animate-spin" />
              Searching…
            </motion.div>
          )}
          {status === "success" && (
            <motion.div
              key="success"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              {rows.length === 500
                ? `Showing 500+ results — narrow filters for more precision.`
                : `Showing ${rows.length} results.`}
            </motion.div>
          )}
          {status === "error" && (
            <motion.div
              key="error"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="text-destructive"
            >
              Error: {error || "Failed to fetch data."}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
