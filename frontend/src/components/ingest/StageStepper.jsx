import { motion } from "motion/react";
import { Check, AlertTriangle, Loader2 } from "lucide-react";
import { STAGES } from "../../lib/constants";
import { fmtNum } from "../../lib/format";
import { cn } from "../../lib/cn";

/** Live pipeline progress for one ingest job (values come from the SSE stream). */
export function StageStepper({ job }) {
  if (!job) return null;
  const failed = job.status === "error";
  const done = job.status === "done";
  const current = Math.max(0, STAGES.findIndex((s) => s.key === job.stage));
  const pct = Math.round((job.progress ?? 0) * 100);

  return (
    <div className="space-y-5">
      <ol className="grid grid-cols-3 gap-3 sm:grid-cols-6" aria-label="Processing stages">
        {STAGES.map((s, i) => {
          const state = done || i < current ? "done" : i === current ? (failed ? "error" : "active") : "todo";
          return (
            <li key={s.key} className="flex flex-col items-center gap-2 text-center" aria-current={state === "active" ? "step" : undefined}>
              <div
                className={cn(
                  "grid size-9 place-items-center rounded-full text-xs font-semibold ring-1 transition",
                  state === "done" && "bg-ok text-white ring-ok",
                  state === "active" && "bg-accent/15 text-accent ring-accent/40",
                  state === "error" && "bg-bad text-white ring-bad",
                  state === "todo" && "bg-fg/5 text-muted ring-line"
                )}
              >
                {state === "done" ? <Check className="size-4" aria-hidden /> : state === "error" ? <AlertTriangle className="size-4" aria-hidden /> : state === "active" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : i + 1}
              </div>
              <span className={cn("text-xs", state === "todo" ? "text-muted" : "font-medium")}>{s.label}</span>
            </li>
          );
        })}
      </ol>

      {!done && !failed && (
        <div>
          <div className="mb-1.5 flex justify-between text-xs text-muted">
            <span>{STAGES[current]?.label} · {pct}%</span>
            <span className="tabular-nums">{fmtNum(job.processed_rows)} / {fmtNum(job.total_rows)} rows</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-fg/5" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <motion.div className="h-full rounded-full bg-gradient-to-r from-saffron via-accent to-indgreen" animate={{ width: `${pct}%` }} transition={{ ease: [0.16, 1, 0.3, 1] }} />
          </div>
        </div>
      )}

      {failed && (
        <div role="alert" className="rounded-2xl bg-bad/10 p-4 text-sm text-bad ring-1 ring-bad/20">
          <p className="font-semibold">Processing stopped</p>
          <p className="mt-1 break-words">{job.report?.error ?? "Unknown error. Check the worker logs."}</p>
        </div>
      )}
    </div>
  );
}
