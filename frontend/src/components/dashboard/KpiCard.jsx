import { GlassCard } from "../ui/GlassCard";
import { AnimatedNumber } from "../ui/AnimatedNumber";
import { Skeleton } from "../ui/Skeleton";
import { cn } from "../../lib/cn";

const tones = {
  accent: "bg-accent/10 text-accent ring-accent/20",
  ok: "bg-ok/10 text-ok ring-ok/20",
  warn: "bg-warn/10 text-warn ring-warn/20",
  bad: "bg-bad/10 text-bad ring-bad/20",
  saffron: "bg-saffron/15 text-saffron ring-saffron/25",
};

/** One headline number, counted up from the API value. */
export function KpiCard({ label, value, format, icon: Icon, hint, tone = "accent", delay = 0, loading = false }) {
  return (
    <GlassCard delay={delay} className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-muted">{label}</p>
          {loading ? (
            <Skeleton className="mt-2 h-9 w-28" />
          ) : (
            <AnimatedNumber value={value ?? 0} format={format} className="mt-1 block font-display text-3xl font-bold" />
          )}
          {hint && <p className="mt-1 truncate text-xs text-muted">{hint}</p>}
        </div>
        {Icon && (
          <div className={cn("grid size-10 shrink-0 place-items-center rounded-2xl ring-1", tones[tone])}>
            <Icon className="size-5" aria-hidden />
          </div>
        )}
      </div>
    </GlassCard>
  );
}
