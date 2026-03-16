import { useState, useCallback, useEffect, useMemo } from "react";
import FilterSidebar, {
  type FilterValues,
  type Weapon,
  type RivenAttribute,
} from "@/components/FilterSidebar";
import RivenTable, { type RivenRow, type PriceStats } from "@/components/RivenTable";

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

  // --- Dynamic data from backend cache ---
  const [weapons, setWeapons] = useState<Weapon[]>([]);
  const [allPositiveAttrs, setAllPositiveAttrs] = useState<RivenAttribute[]>([]);
  const [allNegativeAttrs, setAllNegativeAttrs] = useState<RivenAttribute[]>([]);

  // Fetch weapons and attributes on mount
  useEffect(() => {
    fetch("/api/riven/weapons")
      .then((r) => r.ok ? r.json() : Promise.reject("Failed to load weapons"))
      .then((data: Weapon[]) => setWeapons(data))
      .catch((err) => console.error("[weapons]", err));

    fetch("/api/riven/attributes")
      .then((r) => r.ok ? r.json() : Promise.reject("Failed to load attributes"))
      .then((data: { positive: RivenAttribute[]; negative: RivenAttribute[] }) => {
        setAllPositiveAttrs(data.positive);
        setAllNegativeAttrs(data.negative);
      })
      .catch((err) => console.error("[attributes]", err));
  }, []);

  // Filter attributes by selected weapon's riven_type using exclusive_to
  const filteredPositiveAttrs = useMemo(() => {
    if (!filters.weaponRivenType) return allPositiveAttrs;
    return allPositiveAttrs.filter(
      (a) => a.exclusive_to === null || a.exclusive_to.includes(filters.weaponRivenType)
    );
  }, [allPositiveAttrs, filters.weaponRivenType]);

  const filteredNegativeAttrs = useMemo(() => {
    if (!filters.weaponRivenType) return allNegativeAttrs;
    return allNegativeAttrs.filter(
      (a) => a.exclusive_to === null || a.exclusive_to.includes(filters.weaponRivenType)
    );
  }, [allNegativeAttrs, filters.weaponRivenType]);

  const handleSearch = useCallback(async () => {
    setStatus("loading");
    setError("");

    // Build query string — positiveAttributes is now an array of url_names
    const params = new URLSearchParams();
    if (filters.weaponName)       params.set("weaponName", filters.weaponName);
    if (filters.positiveAttributes.length > 0)
      params.set("positiveAttributes", filters.positiveAttributes.join(","));
    if (filters.negativeAttributes)
      params.set("negativeAttributes", filters.negativeAttributes);
    if (filters.mrMin)            params.set("mrMin", filters.mrMin);
    if (filters.mrMax)            params.set("mrMax", filters.mrMax);
    if (filters.minRerolls)       params.set("minRerolls", filters.minRerolls);
    if (filters.maxRerolls)       params.set("maxRerolls", filters.maxRerolls);
    if (filters.modRank)          params.set("modRank", filters.modRank);
    params.set("sortBy",          filters.sortBy);
    if (filters.buyoutPolicy)     params.set("buyoutPolicy", filters.buyoutPolicy);
    params.set("polarity",        filters.polarity);
    params.set("platform",        filters.platform);
    params.set("crossplay",       filters.crossplay);

    try {
      const res = await fetch(`/api/search?${params.toString()}`);

      if (!res.ok) {
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
      setError("Could not connect to the backend. Make sure backend/main.py is running.");
      setStatus("error");
    }
  }, [filters]);

  // Auto-search when crossplay changes, but not on initial mount
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
      />
      <RivenTable rows={rows} stats={stats} status={status} error={error} />
    </div>
  );
};

export default Index;
