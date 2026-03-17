import { useState, useRef, useEffect, useMemo } from "react";
import { Search, X, ChevronDown, Check, Calculator } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";

// --- Types shared with Index.tsx ---

export interface Weapon {
  url_name: string;
  item_name: string;
  group: string; // display grouping: primary, secondary, melee, etc.
  riven_type: string; // for attribute filtering: rifle, pistol, melee, etc.
  disposition: number; // riven disposition 1-5 (from warframestat.us, default 3)
}

export interface RivenAttribute {
  url_name: string;
  effect: string;
  positive_only: boolean;
  negative_only: boolean;
  search_only: boolean;
  group: string;
  exclusive_to: string[] | null; // list of riven_types this attr applies to, or null = all
}

export interface FilterValues {
  weaponName: string; // url_name of selected weapon
  weaponRivenType: string; // riven_type of selected weapon (for attribute filtering)
  positiveAttributes: string[]; // url_names, max 3
  negativeAttributes: string; // url_name, max 1
  mrMin: string;
  mrMax: string;
  minRerolls: string;
  maxRerolls: string;
  modRank: string;
  sortBy: string;
  buyoutPolicy: string;
  polarity: string;
  platform: string;
  crossplay: string;
}

interface FilterSidebarProps {
  filters: FilterValues;
  onChange: (filters: FilterValues) => void;
  onSearch: () => void;
  isLoading: boolean;
  weapons: Weapon[];
  positiveAttrs: RivenAttribute[];
  negativeAttrs: RivenAttribute[];
  onEstimate: () => void;
  canEstimate: boolean;
}

// --- Shared styles ---

function FilterField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        {label}
      </label>
      {children}
    </div>
  );
}

const inputClass =
  "h-9 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground placeholder:text-muted-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background";

const selectClass =
  "h-9 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background appearance-none cursor-pointer";

const comboTriggerClass =
  "h-9 w-full rounded-md border border-input bg-card px-3 text-sm text-foreground flex items-center justify-between cursor-pointer transition-colors hover:bg-accent/50 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:ring-offset-background";

// --- Weapon Combobox ---

function WeaponCombobox({
  weapons,
  value,
  onSelect,
}: {
  weapons: Weapon[];
  value: string;
  onSelect: (urlName: string, rivenType: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const selected = weapons.find((w) => w.url_name === value);

  // Group weapons by type
  const grouped = useMemo(() => {
    const groups: Record<string, Weapon[]> = {};
    for (const w of weapons) {
      const g = w.group || "Other";
      if (!groups[g]) groups[g] = [];
      groups[g].push(w);
    }
    // Sort group names alphabetically, capitalize
    return Object.entries(groups).sort(([a], [b]) => a.localeCompare(b));
  }, [weapons]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={comboTriggerClass}>
          <span className={selected ? "" : "text-muted-foreground"}>
            {selected ? selected.item_name : "Select weapon..."}
          </span>
          <ChevronDown size={14} className="shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[228px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search weapons..." />
          <CommandList>
            <CommandEmpty>No weapon found.</CommandEmpty>
            {grouped.map(([group, items]) => (
              <CommandGroup
                key={group}
                heading={group.charAt(0).toUpperCase() + group.slice(1)}
              >
                {items.map((w) => (
                  <CommandItem
                    key={w.url_name}
                    value={w.item_name}
                    onSelect={() => {
                      onSelect(w.url_name, w.riven_type);
                      setOpen(false);
                    }}
                  >
                    <Check
                      size={14}
                      className={`mr-2 ${value === w.url_name ? "opacity-100" : "opacity-0"}`}
                    />
                    {w.item_name}
                  </CommandItem>
                ))}
              </CommandGroup>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

// --- Attribute Combobox (single-select) ---

function AttributeCombobox({
  attrs,
  value,
  onSelect,
  placeholder,
  excludeValues,
}: {
  attrs: RivenAttribute[];
  value: string;
  onSelect: (urlName: string) => void;
  placeholder: string;
  excludeValues?: string[];
}) {
  const [open, setOpen] = useState(false);
  const selected = attrs.find((a) => a.url_name === value);
  const excluded = new Set(excludeValues || []);

  const available = useMemo(
    () => attrs.filter((a) => !excluded.has(a.url_name)),
    [attrs, excluded.size],
  );

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={comboTriggerClass}>
          <span className={selected ? "" : "text-muted-foreground"}>
            {selected ? selected.effect : placeholder}
          </span>
          <div className="flex items-center gap-1 shrink-0">
            {value && (
              <span
                role="button"
                className="opacity-50 hover:opacity-100"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect("");
                }}
              >
                <X size={12} />
              </span>
            )}
            <ChevronDown size={14} className="opacity-50" />
          </div>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[228px] p-0" align="start">
        <Command>
          <CommandInput placeholder="Search attributes..." />
          <CommandList>
            <CommandEmpty>No attribute found.</CommandEmpty>
            <CommandGroup>
              {available.map((a) => (
                <CommandItem
                  key={a.url_name}
                  value={a.effect}
                  onSelect={() => {
                    onSelect(a.url_name);
                    setOpen(false);
                  }}
                >
                  <Check
                    size={14}
                    className={`mr-2 ${value === a.url_name ? "opacity-100" : "opacity-0"}`}
                  />
                  {a.effect}
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}

// --- Multi-Select Attribute Combobox (positive attrs, max 3) ---

function AttributeMultiSelect({
  attrs,
  values,
  onChange,
  max,
  excludeValues,
}: {
  attrs: RivenAttribute[];
  values: string[];
  onChange: (values: string[]) => void;
  max: number;
  excludeValues?: string[];
}) {
  const [open, setOpen] = useState(false);
  const excluded = new Set(excludeValues || []);

  const available = useMemo(
    () => attrs.filter((a) => !excluded.has(a.url_name)),
    [attrs, excluded.size],
  );

  const selectedAttrs = values
    .map((v) => attrs.find((a) => a.url_name === v))
    .filter(Boolean) as RivenAttribute[];

  const toggle = (urlName: string) => {
    if (values.includes(urlName)) {
      onChange(values.filter((v) => v !== urlName));
    } else if (values.length < max) {
      onChange([...values, urlName]);
    }
  };

  const remove = (urlName: string) => {
    onChange(values.filter((v) => v !== urlName));
  };

  return (
    <div className="flex flex-col gap-1.5">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button type="button" className={comboTriggerClass}>
            <span className="text-muted-foreground">
              {values.length === 0
                ? "Select attributes..."
                : `${values.length}/${max} selected`}
            </span>
            <ChevronDown size={14} className="shrink-0 opacity-50" />
          </button>
        </PopoverTrigger>
        <PopoverContent className="w-[228px] p-0" align="start">
          <Command>
            <CommandInput placeholder="Search attributes..." />
            <CommandList>
              <CommandEmpty>No attribute found.</CommandEmpty>
              <CommandGroup>
                {available.map((a) => {
                  const isSelected = values.includes(a.url_name);
                  const isDisabled = !isSelected && values.length >= max;
                  return (
                    <CommandItem
                      key={a.url_name}
                      value={a.effect}
                      onSelect={() => !isDisabled && toggle(a.url_name)}
                      className={isDisabled ? "opacity-40" : ""}
                    >
                      <Check
                        size={14}
                        className={`mr-2 ${isSelected ? "opacity-100" : "opacity-0"}`}
                      />
                      {a.effect}
                    </CommandItem>
                  );
                })}
              </CommandGroup>
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {/* Selected badges */}
      {selectedAttrs.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {selectedAttrs.map((a) => (
            <Badge
              key={a.url_name}
              variant="secondary"
              className="text-xs gap-1 cursor-pointer hover:bg-secondary/60"
              onClick={() => remove(a.url_name)}
            >
              {a.effect}
              <X size={10} />
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Dropdown chevron helper ---

function SelectChevron() {
  return (
    <div className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground">
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path
          d="M3 4.5L6 7.5L9 4.5"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </div>
  );
}

// --- Main FilterSidebar ---

export default function FilterSidebar({
  filters,
  onChange,
  onSearch,
  isLoading,
  weapons,
  positiveAttrs,
  negativeAttrs,
  onEstimate,
  canEstimate,
}: FilterSidebarProps) {
  const set =
    (key: keyof FilterValues) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      onChange({ ...filters, [key]: e.target.value });

  const handleWeaponSelect = (urlName: string, rivenType: string) => {
    // When weapon changes, clear attributes since available stats differ by riven_type
    onChange({
      ...filters,
      weaponName: urlName,
      weaponRivenType: rivenType,
      positiveAttributes: [],
      negativeAttributes: "",
    });
  };

  return (
    <aside
      className="w-[260px] min-w-[260px] h-screen flex flex-col bg-card border-r border-border"
      style={{
        boxShadow: "0 0 0 1px rgba(0,0,0,.05), 0 1px 3px 0 rgba(0,0,0,.03)",
      }}
    >
      <div className="p-4 border-b border-border flex items-center justify-between">
        <h2 className="text-lg font-medium tracking-tight text-foreground">
          Filters
        </h2>
        <button
          type="button"
          onClick={onEstimate}
          disabled={!canEstimate}
          className="h-7 px-2.5 rounded-md border border-input bg-background text-xs font-medium text-foreground inline-flex items-center gap-1.5 transition-colors hover:bg-accent hover:text-accent-foreground disabled:opacity-40 disabled:pointer-events-none"
        >
          <Calculator size={14} />
          Estimate
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
        <FilterField label="Platform">
          <div className="relative">
            <select
              className={selectClass}
              value={filters.platform}
              onChange={set("platform")}
            >
              <option value="pc">PC</option>
              <option value="ps4">PlayStation</option>
              <option value="xbox">Xbox</option>
              <option value="switch">Switch</option>
            </select>
            <SelectChevron />
          </div>
        </FilterField>

        <div className="flex items-center justify-between">
          <label className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Crossplay
          </label>
          <Switch
            checked={filters.crossplay === "true"}
            onCheckedChange={(checked) =>
              onChange({ ...filters, crossplay: checked ? "true" : "false" })
            }
          />
        </div>

        <FilterField label="Weapon">
          <WeaponCombobox
            weapons={weapons}
            value={filters.weaponName}
            onSelect={handleWeaponSelect}
          />
        </FilterField>

        <FilterField label="Positive Attributes (max 3)">
          <AttributeMultiSelect
            attrs={positiveAttrs}
            values={filters.positiveAttributes}
            onChange={(vals) =>
              onChange({ ...filters, positiveAttributes: vals })
            }
            max={3}
            excludeValues={
              filters.negativeAttributes ? [filters.negativeAttributes] : []
            }
          />
        </FilterField>

        <FilterField label="Negative Attribute (max 1)">
          <AttributeCombobox
            attrs={negativeAttrs}
            value={filters.negativeAttributes}
            onSelect={(val) =>
              onChange({ ...filters, negativeAttributes: val })
            }
            placeholder="Select attribute..."
            excludeValues={filters.positiveAttributes}
          />
        </FilterField>

        <FilterField label="Mastery Rank Min">
          <input
            className={inputClass}
            type="number"
            min={1}
            max={16}
            placeholder="0"
            value={filters.mrMin}
            onChange={set("mrMin")}
          />
        </FilterField>

        <FilterField label="Mastery Rank Max">
          <input
            className={inputClass}
            type="number"
            min={1}
            max={16}
            placeholder="16"
            value={filters.mrMax}
            onChange={set("mrMax")}
          />
        </FilterField>

        <FilterField label="Min Rerolls">
          <input
            className={inputClass}
            type="number"
            min={0}
            placeholder="0"
            value={filters.minRerolls}
            onChange={set("minRerolls")}
          />
        </FilterField>

        <FilterField label="Max Rerolls">
          <input
            className={inputClass}
            type="number"
            min={0}
            max={1000}
            placeholder="∞"
            value={filters.maxRerolls}
            onChange={set("maxRerolls")}
          />
        </FilterField>

        <FilterField label="Mod Rank">
          <div className="relative">
            <select
              className={selectClass}
              value={filters.modRank}
              onChange={set("modRank")}
            >
              <option value="">All</option>
              <option value="maxed">Maxed</option>
            </select>
            <SelectChevron />
          </div>
        </FilterField>

        <FilterField label="Sort By">
          <div className="relative">
            <select
              className={selectClass}
              value={filters.sortBy}
              onChange={set("sortBy")}
            >
              <option value="price_asc">Price (Low → High)</option>
              <option value="price_desc">Price (High → Low)</option>
              <option value="positive_attr_asc">Positive Attr (Asc)</option>
              <option value="positive_attr_desc">Positive Attr (Desc)</option>
            </select>
            <SelectChevron />
          </div>
        </FilterField>

        <FilterField label="Buyout Policy">
          <div className="relative">
            <select
              className={selectClass}
              value={filters.buyoutPolicy}
              onChange={set("buyoutPolicy")}
            >
              <option value="">All</option>
              <option value="direct">Direct Buy</option>
              <option value="with_bid">With Bidding</option>
            </select>
            <SelectChevron />
          </div>
        </FilterField>

        <FilterField label="Polarity">
          <div className="relative">
            <select
              className={selectClass}
              value={filters.polarity}
              onChange={set("polarity")}
            >
              <option value="any">Any</option>
              <option value="madurai">Madurai</option>
              <option value="vazarin">Vazarin</option>
              <option value="naramon">Naramon</option>
              <option value="zenurik">Zenurik</option>
              <option value="unairu">Unairu</option>
              <option value="penjaga">Penjaga</option>
            </select>
            <SelectChevron />
          </div>
        </FilterField>
      </div>

      <div className="p-4 border-t border-border">
        <button
          onClick={onSearch}
          disabled={isLoading}
          className="h-12 w-full rounded-md bg-primary text-primary-foreground font-medium text-sm flex items-center justify-center gap-2 transition-colors hover:bg-primary/90 active:scale-[0.98] disabled:opacity-60"
        >
          <Search size={18} />
          Search
        </button>
      </div>
    </aside>
  );
}
