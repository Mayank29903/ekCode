import { Link } from "react-router";
import { Building2, ArrowLeftRight } from "lucide-react";
import { ScoreRing } from "../ui/ScoreRing";
import { Badge, SyntheticBadge } from "../ui/Badge";
import { ExplainChips } from "./ExplainChips";
import { MATCH, ATTRIBUTES } from "../../lib/constants";
import { fmtInr } from "../../lib/format";
import { cn } from "../../lib/cn";

function Side({ side, label }) {
  return (
    <div className="min-w-0 rounded-2xl bg-surface/70 p-4 ring-1 ring-line">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-muted">{label}</span>
        <Badge tone="accent"><Building2 className="size-3" aria-hidden />{side.cpse}</Badge>
        <SyntheticBadge show={side.source === "synthetic"} />
      </div>
      <p className="font-mono text-xs text-muted">{side.legacy_code}</p>
      <p className="mt-1 break-words font-medium leading-snug">{side.description}</p>
      <dl className="mt-3 grid grid-cols-2 gap-2 text-xs">
        <div><dt className="text-muted">Unit</dt><dd className="font-medium">{side.uom || "—"}</dd></div>
        <div><dt className="text-muted">Annual spend</dt><dd className="font-medium tabular-nums">{side.spend ? fmtInr(side.spend) : "—"}</dd></div>
      </dl>
      {side.nmc && (
        <p className="mt-3 text-xs text-muted">
          Already coded as <Link to={`/materials/${side.nmc}`} className="font-mono text-accent hover:underline">{side.nmc}</Link>
        </p>
      )}
    </div>
  );
}

const rowTone = { conflict: "bg-bad/8 text-bad", diff: "bg-warn/8", missing: "", match: "" };

/** Side-by-side comparison of one candidate pair with the attribute diff underneath. */
export function PairDiff({ pair }) {
  const m = MATCH[pair.match_type] ?? MATCH.DIFFERENT;
  const attrs = (pair.explanation ?? []).filter((c) => c.kind !== "signal");
  const byKey = Object.fromEntries(attrs.map((c) => [c.key, c]));
  const keys = Object.keys(ATTRIBUTES).filter((k) => byKey[k]);

  return (
    <div className="space-y-5">
      <div className="grid items-center gap-4 md:grid-cols-[1fr_auto_1fr]">
        <Side side={pair.a} label="A" />
        <div className="flex flex-row items-center justify-center gap-3 md:flex-col">
          <ScoreRing score={pair.score} />
          <Badge tone={m.tone} dot>{m.label}</Badge>
          <ArrowLeftRight className="hidden size-4 text-muted md:block" aria-hidden />
        </div>
        <Side side={pair.b} label="B" />
      </div>

      {keys.length > 0 && (
        <div className="overflow-hidden rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <caption className="sr-only">Attributes of A and B</caption>
            <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted">
              <tr>
                <th scope="col" className="px-3 py-2 text-left font-medium">Attribute</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">A</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">B</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-line">
              {keys.map((k) => {
                const c = byKey[k];
                return (
                  <tr key={k} className={cn(rowTone[c.kind])}>
                    <th scope="row" className="px-3 py-2 text-left font-medium">{ATTRIBUTES[k]}</th>
                    <td className="px-3 py-2 font-mono text-xs">{c.a ?? "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{c.b ?? "—"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <ExplainChips explanation={pair.explanation ?? []} />

      {pair.gate_failures?.length > 0 && (
        <p role="note" className="rounded-2xl bg-bad/10 p-3 text-sm text-bad ring-1 ring-bad/20">
          Blocked by rule: {pair.gate_failures.map((g) => ATTRIBUTES[g] ?? g).join(", ")} differ. These two can never be merged.
        </p>
      )}
    </div>
  );
}
