import { GlassCard } from "../ui/GlassCard";
import { Skeleton } from "../ui/Skeleton";
import { cn } from "../../lib/cn";
import { fmtNum } from "../../lib/format";

/** Card frame for a chart: title, optional action, fixed-height body, loading and empty states. */
export function ChartCard({ title, subtitle, action, children, className, delay = 0, height = 280, loading = false, empty }) {
  return (
    <GlassCard className={cn("p-5", className)} delay={delay} spotlight={false}>
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold">{title}</h2>
          {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
        </div>
        {action}
      </div>
      <div style={{ height }}>
        {loading ? (
          <Skeleton className="h-full" />
        ) : empty ? (
          <div className="grid h-full place-items-center px-6 text-center text-sm text-muted">{empty}</div>
        ) : (
          children
        )}
      </div>
    </GlassCard>
  );
}

/** Recharts tooltip in the glass style. Use as <Tooltip content={<ChartTooltip formatter={fmtInr} />} />. */
export function ChartTooltip({ active, payload, label, formatter = fmtNum, labelFormatter }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="glass-strong rounded-xl px-3 py-2 text-xs shadow-lg">
      {label !== undefined && label !== "" && <div className="mb-1 font-semibold">{labelFormatter ? labelFormatter(label) : label}</div>}
      {payload.map((p) => (
        <div key={`${p.dataKey ?? p.name}`} className="flex items-center gap-2">
          <span className="size-2 rounded-full" style={{ background: p.color ?? p.payload?.fill }} aria-hidden />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto font-medium tabular-nums">{formatter(p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Shared axis/grid styling so every chart follows the theme. */
export const axisProps = { tick: { fill: "var(--muted)", fontSize: 12 }, tickLine: false, axisLine: false };
export const gridProps = { stroke: "var(--line)", strokeDasharray: "3 3", vertical: false };
