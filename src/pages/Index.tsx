import { useState } from "react";
import { motion } from "framer-motion";
import { Search, TrendingUp, BarChart3, Activity, ChevronDown, Filter, ArrowUpDown, Zap } from "lucide-react";

// ─── Mock Data ────────────────────────────────────────────────
const WEAPONS = ["Rubico", "Lanka", "Ignis Wraith", "Amprex", "Kohm", "Scoliac", "Gram Prime", "Catchmoon", "Tombfinger", "Rattleguts"];
const PLATFORMS = ["PC", "PS5", "XBOX", "SWITCH"];
const POSITIVE_ATTRS = ["Critical Chance", "Critical Damage", "Multishot", "Damage", "Toxin", "Electricity", "Cold", "Heat", "Status Chance", "Fire Rate", "Magazine Capacity"];
const NEGATIVE_ATTRS = ["Zoom", "Recoil", "Infested Damage", "Corpus Damage", "Grineer Damage", "Impact", "Puncture", "Slash"];
const SORT_OPTIONS = ["Price (Low → High)", "Price (High → Low)", "Recently Listed", "Most Popular"];
const MOD_RANKS = ["All", "0", "8"];
const BUYOUT_POLICIES = ["All", "Buyout Only", "Auction Only"];
const POLARITIES = ["Any", "Madurai", "Vazarin", "Naramon", "Zenurik"];

interface RivenListing {
  id: number;
  weapon: string;
  name: string;
  positives: { label: string; value: string }[];
  negative: { label: string; value: string } | null;
  price: number;
  mr: number;
  rerolls: number;
  rank: number;
  polarity: string;
  platform: string;
  listed: string;
  lastUpdated: string;
  startBid: number;
  topBid: number | null;
}

const generateListings = (): RivenListing[] => {
  const listings: RivenListing[] = [];
  for (let i = 0; i < 24; i++) {
    const weapon = WEAPONS[Math.floor(Math.random() * WEAPONS.length)];
    const numPositives = Math.floor(Math.random() * 2) + 2;
    const positives = [];
    const usedAttrs = new Set<string>();
    for (let j = 0; j < numPositives; j++) {
      let attr;
      do { attr = POSITIVE_ATTRS[Math.floor(Math.random() * POSITIVE_ATTRS.length)]; } while (usedAttrs.has(attr));
      usedAttrs.add(attr);
      positives.push({ label: attr, value: `+${(Math.random() * 200 + 50).toFixed(1)}%` });
    }
    const hasNegative = Math.random() > 0.3;
    const negative = hasNegative
      ? { label: NEGATIVE_ATTRS[Math.floor(Math.random() * NEGATIVE_ATTRS.length)], value: `-${(Math.random() * 80 + 10).toFixed(1)}%` }
      : null;
    const suffixes = ["critaata", "hexaron", "mantitron", "gelitis", "cronitis", "vexido", "toxican", "acripha"];
    listings.push({
      id: i,
      weapon,
      name: `${weapon} ${suffixes[Math.floor(Math.random() * suffixes.length)]}`,
      positives,
      negative,
      price: Math.floor(Math.random() * 3000 + 100),
      mr: Math.floor(Math.random() * 12 + 8),
      rerolls: Math.floor(Math.random() * 50),
      rank: Math.random() > 0.5 ? 8 : 0,
      polarity: ["Madurai", "Vazarin", "Naramon"][Math.floor(Math.random() * 3)],
      platform: "PC",
      listed: `${Math.floor(Math.random() * 24 + 1)}h ago`,
      lastUpdated: `${Math.floor(Math.random() * 12 + 1)}h ago`,
      startBid: Math.floor(Math.random() * 1000 + 50),
      topBid: Math.random() > 0.5 ? Math.floor(Math.random() * 2000 + 200) : null,
    });
  }
  return listings.sort((a, b) => a.price - b.price);
};

// ─── Sub-components ───────────────────────────────────────────

function FilterSelect({ label, options, defaultValue }: { label: string; options: string[]; defaultValue?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-label text-muted-foreground">{label}</label>
      <div className="relative">
        <select
          defaultValue={defaultValue || ""}
          className="w-full appearance-none bg-surface border border-border rounded-sm px-3 py-2 text-[13px] text-foreground focus:outline-none focus:border-primary/50 focus:glow-purple-subtle transition-all cursor-pointer"
        >
          {!defaultValue && <option value="" disabled>Select...</option>}
          {options.map((opt) => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        <ChevronDown className="absolute right-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
      </div>
    </div>
  );
}

function FilterInput({ label, defaultValue }: { label: string; defaultValue?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-label text-muted-foreground">{label}</label>
      <input
        type="text"
        defaultValue={defaultValue}
        className="w-full bg-surface border border-border rounded-sm px-3 py-2 text-[13px] text-foreground font-mono focus:outline-none focus:border-primary/50 transition-all"
      />
    </div>
  );
}

function StatusDot({ active, label }: { active?: boolean; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <div className={`w-1.5 h-1.5 rounded-full ${active ? "bg-primary animate-pulse-glow" : "bg-muted-foreground/30"}`} />
      <span className={`text-[11px] font-semibold uppercase tracking-wider ${active ? "text-foreground" : "text-muted-foreground/50"}`}>
        {label}
      </span>
    </div>
  );
}

function MarketStat({ label, value, trend }: { label: string; value: string; trend?: "up" | "down" }) {
  return (
    <div className="bg-surface border border-border rounded-sm p-4">
      <div className="text-label text-muted-foreground mb-1">{label}</div>
      <div className="flex items-baseline gap-2">
        <span className="text-xl font-mono font-semibold text-foreground">{value}</span>
        {trend && (
          <span className={`text-[11px] font-mono ${trend === "up" ? "text-trend-up" : "text-trend-down"}`}>
            {trend === "up" ? "▲ 4.2%" : "▼ 1.8%"}
          </span>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────

const containerVariants = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: { staggerChildren: 0.04 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.3, ease: [0.2, 0, 0, 1] as const } },
};

export default function Index() {
  const [listings] = useState<RivenListing[]>(generateListings);
  const [activeNav, setActiveNav] = useState<"search" | "compare">("search");
  const [showResults, setShowResults] = useState(false);
  const [activePlatform, setActivePlatform] = useState("PC");

  return (
    <div className="min-h-screen bg-background text-foreground selection:bg-primary/30">
      {/* ─── Top Navigation ─── */}
      <nav className="h-14 border-b border-border bg-surface/80 backdrop-blur-md flex items-center px-6 sticky top-0 z-50">
        <div className="flex items-center gap-8 w-full">
          {/* Logo */}
          <div className="flex items-center gap-2.5 mr-4">
            <Zap className="w-6 h-6 text-primary" />
            <span className="text-sm font-bold tracking-tight text-foreground">
              RIVEN<span className="text-primary">TERMINAL</span>
            </span>
          </div>

          {/* Nav Items */}
          <div className="flex gap-1">
            {[
              { key: "search" as const, label: "MARKET SEARCH", icon: Search },
              { key: "compare" as const, label: "PRICE COMPARISON", icon: BarChart3 },
            ].map(({ key, label, icon: Icon }) => (
              <button
                key={key}
                onClick={() => setActiveNav(key)}
                className={`relative flex items-center gap-2 px-4 py-2 text-[11px] font-semibold uppercase tracking-widest transition-colors rounded-sm ${
                  activeNav === key
                    ? "text-primary bg-primary/10"
                    : "text-muted-foreground hover:text-accent"
                }`}
              >
                <Icon className="w-3.5 h-3.5" />
                {label}
                {activeNav === key && (
                  <motion.div
                    layoutId="nav-indicator"
                    className="absolute bottom-0 left-0 right-0 h-[2px] bg-primary"
                  />
                )}
              </button>
            ))}
          </div>

          {/* Right side */}
          <div className="ml-auto flex items-center gap-4">
            {PLATFORMS.map((p) => (
              <button
                key={p}
                onClick={() => setActivePlatform(p)}
                className="cursor-pointer"
              >
                <StatusDot active={p === activePlatform} label={p} />
              </button>
            ))}
          </div>
        </div>
      </nav>

      {/* ─── Main Layout ─── */}
      <div className="flex">
        {/* ─── Sidebar Filters ─── */}
        <aside className="w-[260px] shrink-0 border-r border-border h-[calc(100vh-3.5rem)] sticky top-14 overflow-y-auto bg-background p-5 space-y-5">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-label text-primary flex items-center gap-1.5">
              <Filter className="w-3 h-3" />
              FILTER PARAMETERS
            </h3>
          </div>

          <FilterSelect label="PLATFORM" options={PLATFORMS} defaultValue="PC" />
          
          <div className="space-y-1.5">
            <label className="text-label text-muted-foreground">CROSSPLAY</label>
            <button className="w-11 h-6 rounded-full bg-primary relative transition-colors">
              <div className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-foreground transition-transform" />
            </button>
          </div>

          <FilterSelect label="WEAPON" options={["Select weapon...", ...WEAPONS]} />
          <FilterSelect label="POSITIVE ATTRIBUTES (MAX 3)" options={POSITIVE_ATTRS} />
          <FilterSelect label="NEGATIVE ATTRIBUTE (MAX 1)" options={NEGATIVE_ATTRS} />
          <FilterInput label="MASTERY RANK MIN" defaultValue="0" />
          <FilterInput label="MASTERY RANK MAX" defaultValue="16" />
          <FilterInput label="MIN REROLLS" defaultValue="0" />
          <FilterInput label="MAX REROLLS" defaultValue="∞" />
          <FilterSelect label="MOD RANK" options={MOD_RANKS} defaultValue="All" />
          <FilterSelect label="SORT BY" options={SORT_OPTIONS} defaultValue="Price (Low → High)" />
          <FilterSelect label="BUYOUT POLICY" options={BUYOUT_POLICIES} defaultValue="All" />
          <FilterSelect label="POLARITY" options={POLARITIES} defaultValue="Any" />

          <button
            onClick={() => setShowResults(true)}
            className="w-full bg-primary hover:bg-accent text-primary-foreground text-[11px] font-bold uppercase tracking-widest py-3 rounded-sm transition-all hover:glow-purple flex items-center justify-center gap-2"
          >
            <Search className="w-3.5 h-3.5" />
            EXECUTE SEARCH
          </button>
        </aside>

        {/* ─── Main Content ─── */}
        <main className="flex-1 min-w-0">
          {!showResults ? (
            <div className="flex items-center justify-center h-[calc(100vh-3.5rem)]">
              <div className="text-center space-y-3">
                <Activity className="w-10 h-10 text-primary/30 mx-auto" />
                <p className="text-muted-foreground text-sm">Configure filters and press Search to load results.</p>
              </div>
            </div>
          ) : (
            <motion.div
              variants={containerVariants}
              initial="hidden"
              animate="show"
              className="p-6 space-y-6"
            >
              {/* Market Overview */}
              <motion.div variants={itemVariants}>
                <div className="flex items-end justify-between mb-4">
                  <div>
                    <h1 className="text-2xl font-semibold tracking-tight">
                      Riven Terminal <span className="text-primary">v4.2</span>
                    </h1>
                    <p className="text-muted-foreground text-[13px] font-mono mt-0.5">
                      [SYSTEM_READY]: {listings.length} ACTIVE LISTINGS
                    </p>
                  </div>
                  <div className="flex gap-2">
                    <MarketStat label="AVG VALUATION" value="1,284 PL" trend="up" />
                    <MarketStat label="24H VOLUME" value="12,481" trend="up" />
                    <MarketStat label="ACTIVE SELLERS" value="3,892" />
                  </div>
                </div>
              </motion.div>

              {/* Table Header */}
              <motion.div variants={itemVariants}>
                <div className="grid grid-cols-12 gap-0 text-label text-muted-foreground border-b border-primary/20 pb-2 px-4">
                  <div className="col-span-2">WEAPON</div>
                  <div className="col-span-2">RIVEN NAME</div>
                  <div className="col-span-1 text-right">START BID</div>
                  <div className="col-span-1 text-right">BUYOUT</div>
                  <div className="col-span-1 text-right">TOP BID</div>
                  <div className="col-span-1">LISTED</div>
                  <div className="col-span-3">ATTRIBUTES</div>
                  <div className="col-span-1 text-right">
                    <span className="inline-flex items-center gap-1">MR <ArrowUpDown className="w-2.5 h-2.5" /></span>
                  </div>
                </div>
              </motion.div>

              {/* Listings */}
              {listings.map((listing) => (
                <motion.div
                  key={listing.id}
                  variants={itemVariants}
                  whileHover={{ x: 2 }}
                  className="group grid grid-cols-12 gap-0 items-center px-4 py-3 scanline-border hover:bg-surface/80 transition-all cursor-pointer relative"
                >
                  {/* Purple accent bar on hover */}
                  <div className="absolute left-0 top-0 w-[2px] h-full bg-primary opacity-0 group-hover:opacity-100 transition-opacity" />

                  <div className="col-span-2">
                    <span className="text-[13px] font-medium text-foreground">{listing.weapon}</span>
                  </div>
                  <div className="col-span-2">
                    <span className="text-[12px] font-mono text-accent">{listing.name}</span>
                  </div>
                  <div className="col-span-1 text-right">
                    <span className="text-[13px] font-mono text-foreground">{listing.startBid.toLocaleString()}</span>
                    <span className="text-[9px] text-muted-foreground ml-0.5">PL</span>
                  </div>
                  <div className="col-span-1 text-right">
                    <span className="text-[13px] font-mono font-semibold text-foreground">{listing.price.toLocaleString()}</span>
                    <span className="text-[9px] text-muted-foreground ml-0.5">PL</span>
                  </div>
                  <div className="col-span-1 text-right">
                    {listing.topBid ? (
                      <>
                        <span className="text-[13px] font-mono text-foreground">{listing.topBid.toLocaleString()}</span>
                        <span className="text-[9px] text-muted-foreground ml-0.5">PL</span>
                      </>
                    ) : (
                      <span className="text-[11px] text-muted-foreground">—</span>
                    )}
                  </div>
                  <div className="col-span-1">
                    <span className="text-[12px] text-muted-foreground">{listing.listed}</span>
                  </div>
                  <div className="col-span-3 flex flex-wrap gap-1">
                    {listing.positives.map((p, i) => (
                      <span key={i} className="text-[10px] font-mono bg-primary/10 text-accent px-1.5 py-0.5 rounded-sm">
                        {p.value} {p.label}
                      </span>
                    ))}
                    {listing.negative && (
                      <span className="text-[10px] font-mono bg-red-500/10 text-red-400 px-1.5 py-0.5 rounded-sm">
                        {listing.negative.value} {listing.negative.label}
                      </span>
                    )}
                  </div>
                  <div className="col-span-1 text-right">
                    <span className="text-[12px] font-mono text-muted-foreground">{listing.mr}</span>
                  </div>
                </motion.div>
              ))}
            </motion.div>
          )}
        </main>
      </div>
    </div>
  );
}
