import { cn } from "../../lib/cn";
const tones = {
  ok: "bg-ok/12 text-ok ring-ok/25",
  warn: "bg-warn/12 text-warn ring-warn/25",
  bad: "bg-bad/12 text-bad ring-bad/25",
  accent: "bg-accent/12 text-accent ring-accent/25",
  muted: "bg-fg/5 text-muted ring-line",
};
export function Badge({ tone = "muted", className, children, dot }) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", tones[tone], className)}>
      {dot && <span className="size-1.5 rounded-full bg-current" aria-hidden />}
      {children}
    </span>
  );
}

/** Rule 5: synthetic seed rows are always labelled. */
export function SyntheticBadge({ show = true }) {
  if (!show) return null;
  return <Badge tone="warn" className="px-2 text-[10px] uppercase tracking-wide">Synthetic</Badge>;
}
