import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Search as SearchIcon, Sparkles, Boxes, FileText } from "lucide-react";
import { api, qs } from "../lib/api";
import { fmtInr } from "../lib/format";
import { ATTRIBUTES, MATCH } from "../lib/constants";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Textarea } from "../components/ui/Input";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { ScoreRing } from "../components/ui/ScoreRing";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { ExplainChips } from "../components/review/ExplainChips";

const EXAMPLES = ["HEX BOLT M12X50 SS304", 'GATE VALVE 2" 150# A105 API 600', "SPIRAL WOUND GASKET 4 IN 300# SS316"];

function Hit({ hit, children, delay }) {
  const m = MATCH[hit.match_type] ?? MATCH.DIFFERENT;
  return (
    <GlassCard className="p-5" delay={delay}>
      <div className="flex gap-4">
        <ScoreRing score={hit.score} size={60} stroke={6} />
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={hit.gate_failures.length ? "bad" : m.tone} dot>{hit.gate_failures.length ? "Conflicts with your text" : m.label}</Badge>
          </div>
          {children}
          <ExplainChips explanation={hit.explanation} showSignals={false} />
        </div>
      </div>
    </GlassCard>
  );
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const [text, setText] = useState(q);
  useEffect(() => setText(q), [q]);
  const res = useQuery({ queryKey: ["search", q], queryFn: () => api(`/search${qs({ q, limit: 12 })}`), enabled: q.length >= 2 });
  const submit = (e) => { e?.preventDefault(); if (text.trim().length >= 2) setParams({ q: text.trim() }); };
  const d = res.data;

  return (
    <div>
      <PageHeader eyebrow="Find equivalent" title="Is this material already coded?"
        subtitle="Paste any description, in any CPSE's style. EkCode reads the attributes and ranks national codes and uncoded legacy items, with the reasons." />

      <GlassCard className="mb-6 p-5" spotlight={false}>
        <form onSubmit={submit} className="space-y-3">
          <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} aria-label="Material description"
            placeholder="e.g. SS HX BLT M12 L50" onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) submit(e); }} />
          <div className="flex flex-wrap items-center gap-2">
            <Button type="submit" loading={res.isFetching} disabled={text.trim().length < 2}>{!res.isFetching && <SearchIcon className="size-4" aria-hidden />} Find equivalents</Button>
            <span className="text-xs text-muted">Try:</span>
            {EXAMPLES.map((ex) => (
              <button key={ex} type="button" onClick={() => setParams({ q: ex })} className="rounded-full bg-fg/5 px-2.5 py-1 font-mono text-xs text-muted hover:bg-accent/10 hover:text-accent">{ex}</button>
            ))}
          </div>
        </form>
      </GlassCard>

      {!q ? (
        <GlassCard><EmptyState icon={SearchIcon} title="Type a description to begin" text="The first search after a restart takes a few seconds while the language model loads." /></GlassCard>
      ) : res.isLoading ? (
        <GlassCard className="p-6"><SkeletonRows rows={6} /></GlassCard>
      ) : res.isError ? (
        <p role="alert" className="rounded-2xl bg-bad/10 p-4 text-sm text-bad">{res.error.message}</p>
      ) : d && (
        <div className="space-y-6">
          <GlassCard className="p-5" spotlight={false}>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-accent" aria-hidden /> How EkCode read your text</h2>
            <p className="font-mono text-sm">{d.query.standard_description}</p>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {Object.entries(d.query.attributes).map(([k, v]) => <Badge key={k} tone="accent">{ATTRIBUTES[k] ?? k}: {v}</Badge>)}
              {!Object.keys(d.query.attributes).length && <span className="text-xs text-muted">No attributes recognised; matching uses meaning and wording only.</span>}
            </div>
          </GlassCard>

          {d.exact.length > 0 && (
            <section>
              <h2 className="mb-2 text-base font-semibold">Exact code match</h2>
              <div className="flex flex-wrap gap-2">
                {d.exact.map((x) => x.kind === "nmc" ? (
                  <Link key={x.nmc} to={`/materials/${x.nmc}`}><Badge tone="ok"><Boxes className="size-3" aria-hidden /> {x.nmc}</Badge></Link>
                ) : (
                  <Link key={x.id} to={x.nmc ? `/materials/${x.nmc}` : "#"}><Badge tone="accent">{x.cpse} {x.legacy_code} → {x.nmc ?? "not mapped"}</Badge></Link>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-base font-semibold">National codes ({d.national.length})</h2>
            {d.national.length ? (
              <div className="grid gap-3 lg:grid-cols-2">
                {d.national.map((h, n) => (
                  <Hit key={h.nmc} hit={h} delay={n * 0.03}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Link to={`/materials/${h.nmc}`} className="font-mono text-sm font-semibold text-accent hover:underline">{h.nmc}</Link>
                      <SyntheticBadge show={h.synthetic} />
                    </div>
                    <p className="font-medium">{h.standard_description}</p>
                    <p className="text-xs text-muted">
                      {h.legacy_count} legacy codes · {h.cpses.join(", ")}{h.spend ? ` · ${fmtInr(h.spend)}/yr` : ""}
                    </p>
                    <p className="truncate text-xs text-muted" title={h.matched.description}>Closest: {h.matched.cpse} {h.matched.legacy_code}, “{h.matched.description}”</p>
                  </Hit>
                ))}
              </div>
            ) : <p className="text-sm text-muted">No national code is close to this description yet.</p>}
          </section>

          <section>
            <h2 className="mb-3 text-base font-semibold">Legacy items not yet coded ({d.legacy.length})</h2>
            {d.legacy.length ? (
              <div className="grid gap-3 lg:grid-cols-2">
                {d.legacy.map((h, n) => (
                  <Hit key={h.id} hit={h} delay={n * 0.03}>
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge>{h.cpse}</Badge>
                      <span className="font-mono text-xs">{h.legacy_code}</span>
                      <SyntheticBadge show={h.source === "synthetic"} />
                    </div>
                    <p className="flex items-start gap-1.5 font-medium"><FileText className="mt-0.5 size-4 shrink-0 text-muted" aria-hidden />{h.description}</p>
                  </Hit>
                ))}
              </div>
            ) : <p className="text-sm text-muted">No uncoded legacy item is close to this description.</p>}
          </section>
        </div>
      )}
    </div>
  );
}
