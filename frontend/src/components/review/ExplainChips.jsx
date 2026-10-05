import { Check, X, Minus, AlertTriangle } from "lucide-react";
import { cn } from "../../lib/cn";

const KIND = {
  match: { cls: "bg-ok/10 text-ok ring-ok/25", icon: Check, title: "Same on both" },
  diff: { cls: "bg-warn/10 text-warn ring-warn/25", icon: AlertTriangle, title: "Different, not critical" },
  conflict: { cls: "bg-bad/10 text-bad ring-bad/30", icon: X, title: "Critical conflict: never merged" },
  missing: { cls: "bg-fg/5 text-muted ring-line", icon: Minus, title: "Stated on one side only" },
};

const val = (v) => (v === null || v === undefined || v === "" ? "—" : String(v));

/** The "why" behind a score: one chip per attribute plus the two similarity signals (backend ekml/explain.py). */
export function ExplainChips({ explanation = [], showSignals = true, className }) {
  const attrs = explanation.filter((c) => c.kind !== "signal" && c.key !== "noun");
  const signals = explanation.filter((c) => c.kind === "signal");
  const order = { conflict: 0, diff: 1, missing: 2, match: 3 };
  attrs.sort((a, b) => order[a.kind] - order[b.kind]);

  return (
    <div className={cn("space-y-3", className)}>
      <ul className="flex flex-wrap gap-1.5" aria-label="Why this score">
        {attrs.map((c) => {
          const k = KIND[c.kind] ?? KIND.missing;
          const Icon = k.icon;
          const text = c.kind === "match" ? val(c.a) : `${val(c.a)} ≠ ${val(c.b)}`;
          return (
            <li key={c.key} title={k.title} className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs ring-1 ring-inset", k.cls)}>
              <Icon className="size-3" aria-hidden />
              <span className="font-medium">{c.label}:</span>
              <span className="font-mono">{c.kind === "missing" ? `${val(c.a)} / ${val(c.b)}` : text}</span>
            </li>
          );
        })}
      </ul>
      {showSignals && signals.length > 0 && (
        <div className="grid gap-2 sm:grid-cols-2">
          {signals.map((s) => (
            <div key={s.label}>
              <div className="mb-1 flex justify-between text-[11px] text-muted">
                <span>{s.label}</span>
                <span className="tabular-nums">{Math.round((s.value ?? 0) * 100)}%</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-fg/5">
                <div className="h-full rounded-full bg-accent" style={{ width: `${Math.round((s.value ?? 0) * 100)}%` }} />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
