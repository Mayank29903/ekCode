import { Fragment, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { ScrollText, Download, ChevronDown, ChevronLeft, ChevronRight, Lock } from "lucide-react";
import { api, download, qs } from "../lib/api";
import { fmtDateTime, fmtNum } from "../lib/format";
import { AUDIT_READERS } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { useDebounce } from "../hooks/useDebounce";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Input } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { cn } from "../lib/cn";

const PAGE = 50;
const TONE = { approve: "ok", create: "ok", map: "accent", remap: "accent", merge: "warn", reject: "bad", revoke: "bad", delete: "bad" };

function Json({ value }) {
  if (value === null || value === undefined) return <span className="text-muted">—</span>;
  return <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-fg/[0.04] p-3 font-mono text-[11px]">{JSON.stringify(value, null, 2)}</pre>;
}

export default function Audit() {
  const { can } = useAuth();
  const [f, setF] = useState({ entity: "", action: "", actor: "", q: "", since: "", until: "" });
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState(null);
  const dActor = useDebounce(f.actor, 300);
  const dQ = useDebounce(f.q, 300);
  const params = {
    entity: f.entity, action: f.action, actor: dActor, q: dQ,
    since: f.since && `${f.since}T00:00:00`, until: f.until && `${f.until}T23:59:59`,
  };
  const allowed = can(...AUDIT_READERS);
  const trail = useQuery({
    queryKey: ["audit", params, page],
    queryFn: () => api(`/audit${qs({ ...params, limit: PAGE, offset: page * PAGE })}`),
    placeholderData: keepPreviousData,
    enabled: allowed,
  });
  const set = (k) => (e) => { setF({ ...f, [k]: e.target.value }); setPage(0); };

  if (!allowed) return <GlassCard><EmptyState icon={Lock} title="The audit trail is for stewards and auditors" text="Ask an administrator if you need access." /></GlassCard>;

  const d = trail.data;
  const exportCsv = async () => {
    try { await download(`/audit/export${qs(params)}`, "ekcode_audit.csv"); } catch (err) { toast.error(err.message); }
  };

  return (
    <div>
      <PageHeader eyebrow="Audit trail" title="Every change, who made it and why"
        subtitle="Append-only. Each row was written in the same transaction as the change it records."
        actions={<Button variant="glass" size="sm" onClick={exportCsv}><Download className="size-4" aria-hidden /> Export CSV</Button>} />

      <GlassCard className="mb-4 p-4" spotlight={false}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          <Select value={f.entity} onChange={set("entity")} aria-label="Entity" placeholder="All entities" options={(d?.entities ?? []).map((e) => ({ value: e, label: e.replace("_", " ") }))} />
          <Select value={f.action} onChange={set("action")} aria-label="Action" placeholder="All actions" options={(d?.actions ?? []).map((a) => ({ value: a, label: a }))} />
          <Input value={f.actor} onChange={set("actor")} placeholder="Actor email" aria-label="Actor" />
          <Input value={f.q} onChange={set("q")} placeholder="Code, reason…" aria-label="Search" />
          <Input type="date" value={f.since} onChange={set("since")} aria-label="From date" />
          <Input type="date" value={f.until} onChange={set("until")} aria-label="To date" />
        </div>
      </GlassCard>

      <div className="overflow-hidden rounded-3xl border border-line bg-surface">
        {trail.isLoading ? <div className="p-4"><SkeletonRows rows={10} /></div> : trail.isError ? (
          <p role="alert" className="p-4 text-sm text-bad">{trail.error.message}</p>
        ) : !d.items.length ? (
          <EmptyState icon={ScrollText} title="No entries match" text="Change the filters, or come back after the first upload or decision." />
        ) : (
          <div className={cn("overflow-x-auto", trail.isFetching && "opacity-70")}>
            <table className="w-full text-sm">
              <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted"><tr>
                <th scope="col" className="px-4 py-2 text-left font-medium">When</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">Who</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">Action</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">What</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">Reason</th>
                <th scope="col" className="px-4 py-2"><span className="sr-only">Details</span></th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {d.items.map((a) => (
                  <Fragment key={a.id}>
                    <tr className="hover:bg-accent/5">
                      <td className="whitespace-nowrap px-4 py-2.5 text-xs text-muted">{fmtDateTime(a.at)}</td>
                      <td className="px-3 py-2.5 text-xs">{a.actor_email}</td>
                      <td className="px-3 py-2.5"><Badge tone={TONE[a.action] ?? "muted"}>{a.action}</Badge></td>
                      <td className="px-3 py-2.5"><span className="text-muted">{a.entity.replace("_", " ")}</span> <span className="font-mono text-xs">{a.entity_id}</span></td>
                      <td className="max-w-xs truncate px-3 py-2.5 text-xs text-muted" title={a.reason ?? ""}>{a.reason ?? ""}</td>
                      <td className="px-4 py-2.5 text-right">
                        <button onClick={() => setOpen(open === a.id ? null : a.id)} aria-expanded={open === a.id} className="rounded-lg p-1.5 hover:bg-fg/5" aria-label="Show before and after">
                          <ChevronDown className={cn("size-4 transition", open === a.id && "rotate-180")} />
                        </button>
                      </td>
                    </tr>
                    {open === a.id && (
                      <tr className="bg-fg/[0.02]">
                        <td colSpan={6} className="px-4 py-3">
                          <div className="grid gap-3 md:grid-cols-2">
                            <div><p className="mb-1 text-xs font-semibold text-muted">Before</p><Json value={a.before} /></div>
                            <div><p className="mb-1 text-xs font-semibold text-muted">After</p><Json value={a.after} /></div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between border-t border-line px-4 py-3 text-sm">
              <span className="tabular-nums text-muted">{fmtNum(page * PAGE + 1)}–{fmtNum(Math.min(d.total, (page + 1) * PAGE))} of {fmtNum(d.total)}</span>
              <div className="flex gap-1">
                <Button variant="ghost" size="sm" onClick={() => setPage(page - 1)} disabled={page === 0} aria-label="Previous page"><ChevronLeft className="size-4" /></Button>
                <Button variant="ghost" size="sm" onClick={() => setPage(page + 1)} disabled={(page + 1) * PAGE >= d.total} aria-label="Next page"><ChevronRight className="size-4" /></Button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
