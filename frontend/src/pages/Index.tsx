import { useState, useCallback, useEffect, useMemo } from "react";
import FilterSidebar, {
  type FilterValues,
  type Weapon,
  type RivenAttribute,
} from "@/components/FilterSidebar";
import RivenTable, {
  type RivenRow,
  type PriceStats,
} from "@/components/RivenTable";
import EstimateSheet from "@/components/EstimateSheet";
import {
  parseAttributeDisplay,
  type EstimateResponse,
  type AuctionBid,
  type AuctionBidsResponse,
} from "@/types/estimate";

const defaultFilters: FilterValues = {
  weaponName: "",
  weaponRivenType: "",
  positiveAttributes: [],
  negativeAttributes: "",
  mrMin: "",
  mrMax: "",
  minRerolls: "",
  maxRerolls: "",
  modRank: "",
  sortBy: "price_asc",
  buyoutPolicy: "",
  polarity: "any",
  platform: "pc",
  crossplay: "true",
};

type Status = "idle" | "loading" | "success" | "error";

const Index = () => {
  const [filters, setFilters] = useState<FilterValues>(defaultFilters);
  const [rows, setRows] = useState<RivenRow[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>("");
  const [stats, setStats] = useState<PriceStats | null>(null);

  // Selection state (lifted from RivenTable so EstimateSheet can access it)
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Estimate sheet state — tracks the open/close state, async status, and result payload
  const [estimateResult, setEstimateResult] = useState<EstimateResponse | null>(
    null,
  );
  const [estimateStatus, setEstimateStatus] = useState<Status>("idle");
  const [estimateError, setEstimateError] = useState<string>("");
  const [estimateOpen, setEstimateOpen] = useState(false);

  // Per-session bid cache — in-memory only, cleared on new search.
  const [bidCache, setBidCache] = useState<Record<string, AuctionBid[]>>({});

  // --- Dynamic data from backend cache ---
  const [weapons, setWeapons] = useState<Weapon[]>([]);
  const [allPositiveAttrs, setAllPositiveAttrs] = useState<RivenAttribute[]>(
    [],
  );
  const [allNegativeAttrs, setAllNegativeAttrs] = useState<RivenAttribute[]>(
    [],
  );

  // Fetch the full weapon list and attribute catalogue from the backend cache on
  // initial mount. These lists are static for a given game patch and rarely change.
  useEffect(() => {
    fetch("/api/riven/weapons")
      .then((r) => (r.ok ? r.json() : Promise.reject("Failed to load weapons")))
      .then((data: Weapon[]) => setWeapons(data))
      .catch((err) => console.error("[weapons]", err));

    fetch("/api/riven/attributes")
      .then((r) =>
        r.ok ? r.json() : Promise.reject("Failed to load attributes"),
      )
      .then(
        (data: { positive: RivenAttribute[]; negative: RivenAttribute[] }) => {
          setAllPositiveAttrs(data.positive);
          setAllNegativeAttrs(data.negative);
        },
      )
      .catch((err) => console.error("[attributes]", err));
  }, []);

  // Filter the global attribute list down to stats valid for the selected weapon's
  // riven_type. Attributes with exclusive_to === null are universal (apply to all
  // weapon types). Re-computes only when the weapon type or attribute list changes.
  const filteredPositiveAttrs = useMemo(() => {
    if (!filters.weaponRivenType) return allPositiveAttrs;
    return allPositiveAttrs.filter(
      (a) =>
        a.exclusive_to === null ||
        a.exclusive_to.includes(filters.weaponRivenType),
    );
  }, [allPositiveAttrs, filters.weaponRivenType]);

  const filteredNegativeAttrs = useMemo(() => {
    if (!filters.weaponRivenType) return allNegativeAttrs;
    return allNegativeAttrs.filter(
      (a) =>
        a.exclusive_to === null ||
        a.exclusive_to.includes(filters.weaponRivenType),
    );
  }, [allNegativeAttrs, filters.weaponRivenType]);

  // Derive the full RivenRow for the selected auction ID so EstimateSheet can
  // display the riven name and weapon without prop-drilling the entire rows array.
  const selectedRow = useMemo(
    () => (selectedId ? (rows.find((r) => r.id === selectedId) ?? null) : null),
    [selectedId, rows],
  );

  // The Estimate button is only active when a row is selected, the last search
  // succeeded, and a weapon is chosen (needed to call /api/estimate).
  const canEstimate =
    selectedId !== null && status === "success" && filters.weaponName !== "";

  // Fetch bids for the selected auction on row click (pre-warms bid cache).
  useEffect(() => {
    if (!selectedId || bidCache[selectedId]) return;
    const platform = filters.platform;
    fetch(`/api/auction/${selectedId}/bids?platform=${platform}`)
      .then((r) => (r.ok ? r.json() : Promise.reject("Failed")))
      .then((data: AuctionBidsResponse) => {
        setBidCache((prev) => ({ ...prev, [data.auctionId]: data.bids }));
      })
      .catch((err) => console.error("[bids]", err));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId]);

  // handleSearch — fires when the user clicks Search or when crossplay toggles.
  // Resets all result state before the request so stale data is never shown, then
  // serialises the current filter values into query params and calls /api/search.
  const handleSearch = useCallback(async () => {
    setStatus("loading");
    setError("");
    setSelectedId(null);
    setBidCache({});
    setEstimateOpen(false);
    setEstimateResult(null);
    setEstimateStatus("idle");
    setEstimateError("");

    // Build query string — positiveAttributes is now an array of url_names
    const params = new URLSearchParams();
    if (filters.weaponName) params.set("weaponName", filters.weaponName);
    if (filters.positiveAttributes.length > 0)
      params.set("positiveAttributes", filters.positiveAttributes.join(","));
    if (filters.negativeAttributes)
      params.set("negativeAttributes", filters.negativeAttributes);
    if (filters.mrMin) params.set("mrMin", filters.mrMin);
    if (filters.mrMax) params.set("mrMax", filters.mrMax);
    if (filters.minRerolls) params.set("minRerolls", filters.minRerolls);
    if (filters.maxRerolls) params.set("maxRerolls", filters.maxRerolls);
    if (filters.modRank) params.set("modRank", filters.modRank);
    params.set("sortBy", filters.sortBy);
    if (filters.buyoutPolicy) params.set("buyoutPolicy", filters.buyoutPolicy);
    params.set("polarity", filters.polarity);
    params.set("platform", filters.platform);
    params.set("crossplay", filters.crossplay);

    try {
      const res = await fetch(`/api/search?${params.toString()}`);

      if (!res.ok) {
        // Backend returns { errors: string[] } for validation/upstream failures
        const body = await res.json();
        const msg = Array.isArray(body.errors)
          ? body.errors.join("\n")
          : "Search failed.";
        setError(msg);
        setStatus("error");
        return;
      }

      const data = await res.json();
      setRows(data.auctions);
      setStats(data.stats);
      setStatus("success");
    } catch {
      // Network-level failure (backend not running, DNS error, etc.)
      setError(
        "Could not connect to the backend. Make sure backend/main.py is running.",
      );
      setStatus("error");
    }
  }, [filters]);

  // handleEstimate — fires when the user clicks "Estimate" on a selected row.
  // Parses the display-format attribute strings back into url_name:value pairs
  // (the format /api/estimate expects) and opens the EstimateSheet panel.
  const handleEstimate = useCallback(async () => {
    if (!selectedRow || !filters.weaponName) return;

    // Parse display-format attributes back into url_name:value pairs
    const positiveParsed = selectedRow.positiveAttributes
      .map(parseAttributeDisplay)
      .filter((a): a is NonNullable<typeof a> => a !== null);

    // Cannot estimate without at least one positive attribute value
    if (positiveParsed.length === 0) return;

    const params = new URLSearchParams();
    params.set("weaponName", filters.weaponName);
    params.set(
      "positiveAttributes",
      positiveParsed.map((a) => `${a.urlName}:${a.value}`).join(","),
    );

    // Only the first negative attribute is sent — rivens have at most one negative
    if (selectedRow.negativeAttributes.length > 0) {
      const negParsed = parseAttributeDisplay(
        selectedRow.negativeAttributes[0],
      );
      if (negParsed) {
        params.set(
          "negativeAttribute",
          `${negParsed.urlName}:${negParsed.value}`,
        );
      }
    }

    params.set("rerolls", String(selectedRow.rerolls));
    params.set("platform", filters.platform);
    params.set("crossplay", filters.crossplay);

    setEstimateStatus("loading");
    setEstimateError("");
    setEstimateResult(null);
    setEstimateOpen(true);

    try {
      const res = await fetch(`/api/estimate?${params.toString()}`);

      if (!res.ok) {
        // Backend returns { errors: string[] } for validation failures
        const body = await res.json();
        const msg = Array.isArray(body.errors)
          ? body.errors.join("\n")
          : "Estimate failed.";
        setEstimateError(msg);
        setEstimateStatus("error");
        return;
      }

      const data: EstimateResponse = await res.json();
      setEstimateResult(data);
      setEstimateStatus("success");
    } catch {
      // Network-level failure — backend unreachable
      setEstimateError("Could not connect to the backend.");
      setEstimateStatus("error");
    }
  }, [selectedRow, filters.weaponName, filters.platform, filters.crossplay]);

  // Auto-search when crossplay changes, but not on initial mount (status === "idle").
  // This keeps results fresh without requiring the user to manually re-click Search.
  useEffect(() => {
    if (status !== "idle") {
      handleSearch();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.crossplay]);

  return (
    <div className="h-screen w-full flex overflow-hidden">
      <FilterSidebar
        filters={filters}
        onChange={setFilters}
        onSearch={handleSearch}
        isLoading={status === "loading"}
        weapons={weapons}
        positiveAttrs={filteredPositiveAttrs}
        negativeAttrs={filteredNegativeAttrs}
        onEstimate={handleEstimate}
        canEstimate={canEstimate}
      />
      <RivenTable
        rows={rows}
        stats={stats}
        status={status}
        error={error}
        selectedId={selectedId}
        onRowSelect={setSelectedId}
      />
      <EstimateSheet
        open={estimateOpen}
        onOpenChange={setEstimateOpen}
        result={estimateResult}
        status={estimateStatus}
        error={estimateError}
        rivenName={selectedRow?.rivenName ?? ""}
        weaponName={selectedRow?.weapon ?? ""}
      />
    </div>
  );
};

export default Index;
