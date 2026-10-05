import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Search as SearchIcon, Boxes, ChevronLeft, ChevronRight } from "lucide-react";
import { api, qs } from "../lib/api";
import { fmtInr, fmtNum, timeAgo } from "../lib/format";
import { useDebounce } from "../hooks/useDebounce";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { cn } from "../lib/cn";

const PAGE = 25;

function Pager({ page, total, onPage }) {
  if (!total) return null;
  const from = page * PAGE + 1;
  const to = Math.min(total, (page + 1) * PAGE);
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm">
      <span className="text-muted tabular-nums">{fmtNum(from)}–{fmtNum(to)} of {fmtNum(total)}</span>
      <div className="flex gap-1">
        <Button variant="ghost" size="sm" onClick={() => onPage(page - 1)} disabled={page === 0} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
        <Button variant="ghost" size="sm" onClick={() => onPage(page + 1)} disabled={to >= total} aria-label="Next page"><ChevronRight className="size-4" /></Button>
      </div>
    </div>
  );
}

const th = "whitespace-nowrap px-4 py-2.5 text-left text-xs font-medium uppercase tracking-wider text-muted";
const td = "px-4 py-3 align-top";

export default function Materials() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "legacy" ? "legacy" : "national";
  const [q, setQ] = useState(params.get("q") ?? "");
  const dq = useDebounce(q.trim(), 300);
  const [status, setStatus] = useState("active");
  const [noun, setNoun] = useState("");
  const [cpse, setCpse] = useState("");
  const [sort, setSort] = useState("recent");
  const [state, setState] = useState("all");
  const [page, setPage] = useState(0);
  const set = (fn) => (e) => { fn(e.target.value); setPage(0); };

  const cpses = useQuery({ queryKey: ["cpses"], queryFn: () => api("/cpses"), staleTime: Infinity });
  const national = useQuery({
    queryKey: ["materials", { dq, status, noun, cpse, sort, page }],
    queryFn: () => api(`/materials${qs({ q: dq, status, noun, cpse, sort, limit: PAGE, offset: page * PAGE })}`),
    placeholderData: keepPreviousData,
    enabled: tab === "national",
  });
  const legacy = useQuery({
    queryKey: ["legacy", { dq, cpse, state, page }],
    queryFn: () => api(`/legacy${qs({ q: dq, cpse, state, limit: PAGE, offset: page * PAGE })}`),
    placeholderData: keepPreviousData,
    enabled: tab === "legacy",
  });
  const cpseOptions = (cpses.data ?? []).map((c) => ({ value: c.code, label: c.code }));
  const current = tab === "national" ? national : legacy;

  return (
    <div>
      <PageHeader eyebrow="National master" title="Materials"
        subtitle="Every national code (NMC) with the legacy codes it replaces, and every legacy code with its mapping." />

      <div className="mb-4 flex gap-2" role="tablist" aria-label="Which codes">
        {[["national", "National codes"], ["legacy", "Legacy codes"]].map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => { setParams(k === "legacy" ? { tab: "legacy" } : {}); setPage(0); }}
            className={cn("rounded-xl px-3 py-1.5 text-sm font-medium", tab === k ? "bg-surface shadow-sm ring-1 ring-line" : "text-muted hover:bg-fg/5")}>
            {label}
          </button>
        ))}
      </div>

      <GlassCard className="mb-4 p-4" spotlight={false}>
        <div className="grid gap-3 md:grid-cols-[2fr_repeat(3,1fr)]">
          <Input icon={SearchIcon} value={q} onChange={set(setQ)} placeholder={tab === "national" ? "NMC, description or legacy code…" : "Legacy code or description…"} aria-label="Filter" />
          <Select value={cpse} onChange={set(setCpse)} options={cpseOptions} placeholder="All CPSEs" aria-label="CPSE" />
          {tab === "national" ? (
            <>
              <Select value={noun} onChange={set(setNoun)} options={(national.data?.nouns ?? []).map((n) => ({ value: n, label: n }))} placeholder="All material types" aria-label="Material type" />
              <div className="grid grid-cols-2 gap-2">
                <Select value={status} onChange={set(setStatus)} aria-label="Status"
                  options={[{ value: "active", label: "Active" }, { value: "deprecated", label: "Deprecated" }, { value: "all", label: "All" }]} />
                <Select value={sort} onChange={set(setSort)} aria-label="Sort"
                  options={[{ value: "recent", label: "Newest" }, { value: "spend", label: "Spend" }, { value: "legacy", label: "Most codes" }, { value: "nmc", label: "Code" }]} />
              </div>
            </>
          ) : (
            <Select value={state} onChange={set(setState)} aria-label="Mapping"
              options={[{ value: "all", label: "Mapped and unmapped" }, { value: "mapped", label: "Mapped to an NMC" }, { value: "unmapped", label: "Not yet mapped" }]} />
          )}
        </div>
      </GlassCard>

      <div className="overflow-hidden rounded-3xl border border-line bg-surface">
        {current.isLoading ? <div className="p-4"><SkeletonRows rows={8} /></div> : current.isError ? (
          <p role="alert" className="p-4 text-sm text-bad">{current.error.message}</p>
        ) : !current.data?.items.length ? (
          <EmptyState icon={Boxes} title={dq || cpse || noun ? "Nothing matches these filters" : tab === "national" ? "No national codes yet" : "No legacy codes yet"}
            text={tab === "national" && !dq ? "Codes are issued when a steward approves a match, or with “Issue codes for unique materials” on the Review page." : undefined}
            action={tab === "national" && !dq && <Link to="/review"><Button variant="glass">Go to review</Button></Link>} />
        ) : (
          <div className={cn("overflow-x-auto transition-opacity", current.isFetching && "opacity-70")}>
            {tab === "national" ? (
              <table className="w-full text-sm">
                <thead className="bg-fg/[0.03]"><tr>
                  <th scope="col" className={th}>NMC</th><th scope="col" className={th}>Standard description</th>
                  <th scope="col" className={th}>CPSEs</th><th scope="col" className={cn(th, "text-right")}>Legacy codes</th>
                  <th scope="col" className={cn(th, "text-right")}>Annual spend</th><th scope="col" className={th}>Created</th>
                </tr></thead>
                <tbody className="divide-y divide-line">
                  {national.data.items.map((m) => (
                    <tr key={m.nmc} onClick={() => navigate(`/materials/${m.nmc}`)} className="cursor-pointer hover:bg-accent/5">
                      <td className={td}>
                        <Link to={`/materials/${m.nmc}`} onClick={(e) => e.stopPropagation()} className="font-mono text-xs font-medium text-accent hover:underline">{m.nmc}</Link>
                        <div className="mt-1 flex gap-1">
                          {m.status === "deprecated" && <Badge tone="bad">deprecated</Badge>}
                          <SyntheticBadge show={m.synthetic} />
                        </div>
                      </td>
                      <td className={cn(td, "max-w-md")}>
                        <p className="font-medium">{m.standard_description}</p>
                        {m.noun && <p className="text-xs text-muted">{m.noun}</p>}
                      </td>
                      <td className={td}><div className="flex flex-wrap gap-1">{m.cpses.map((c) => <Badge key={c}>{c}</Badge>)}</div></td>
                      <td className={cn(td, "text-right tabular-nums")}>{fmtNum(m.legacy_count)}</td>
                      <td className={cn(td, "text-right tabular-nums")}>{m.spend ? fmtInr(m.spend) : "—"}</td>
                      <td className={cn(td, "whitespace-nowrap text-muted")}>{timeAgo(m.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <table className="w-full text-sm">
                <thead className="bg-fg/[0.03]"><tr>
                  <th scope="col" className={th}>CPSE</th><th scope="col" className={th}>Legacy code</th>
                  <th scope="col" className={th}>Description</th><th scope="col" className={th}>Unit</th>
                  <th scope="col" className={cn(th, "text-right")}>Annual spend</th><th scope="col" className={th}>National code</th>
                </tr></thead>
                <tbody className="divide-y divide-line">
                  {legacy.data.items.map((r) => (
                    <tr key={r.id} className="hover:bg-accent/5">
                      <td className={td}><Badge>{r.cpse}</Badge></td>
                      <td className={cn(td, "font-mono text-xs")}>{r.legacy_code} <SyntheticBadge show={r.source === "synthetic"} /></td>
                      <td className={cn(td, "max-w-md")}>{r.description}</td>
                      <td className={td}>{r.uom ?? "—"}</td>
                      <td className={cn(td, "text-right tabular-nums")}>{r.spend ? fmtInr(r.spend) : "—"}</td>
                      <td className={td}>
                        {r.nmc ? (
                          <Link to={`/materials/${r.nmc}`} className="font-mono text-xs text-accent hover:underline">{r.nmc}</Link>
                        ) : (
                          <Link to={`/search${qs({ q: r.description })}`} className="text-xs text-muted hover:text-accent hover:underline">Not mapped · find equivalent</Link>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <Pager page={page} total={current.data.total} onPage={setPage} />
          </div>
        )}
      </div>
    </div>
  );
}
