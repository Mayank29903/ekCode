import { ChevronDown } from "lucide-react";
import { cn } from "../../lib/cn";

export function Select({ className, options = [], placeholder, ...props }) {
  return (
    <div className="relative">
      <select
        className={cn("h-10 w-full appearance-none rounded-xl border border-line bg-surface/70 pl-3 pr-9 text-sm text-fg transition focus:border-accent/50 focus:outline-none focus:ring-4 focus:ring-accent/15", className)}
        {...props}
      >
        {placeholder !== undefined && <option value="">{placeholder}</option>}
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />
    </div>
  );
}
