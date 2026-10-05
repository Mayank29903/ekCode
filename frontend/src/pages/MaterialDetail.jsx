import { useState } from "react";
import { Link, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Copy, Share2, Pencil, ShieldCheck, ShieldAlert, ArrowRight, Plus, Trash2, Boxes, History, Tags } from "lucide-react";
import { api } from "../lib/api";
import { fmtInr, fmtNum, fmtDateTime } from "../lib/format";
import { ATTRIBUTES, MATCH, PAIR_STATUS } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { Input, Label, Textarea } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { EmptyState } from "../components/ui/EmptyState";
import { FullScreenLoader } from "../components/ui/Skeleton";

const ATTR_OPTIONS = Object.entries(ATTRIBUTES).map(([value, label]) => ({ value, label }));

function EditForm({ m, onDone }) {
  const qc = useQueryClient();
  const [description, setDescription] = useState(m.standard_description);
  const [rows, setRows] = useState(Object.entries(m.attributes ?? {}));
  const [regenerate, setRegenerate] = useState(false);
  const [reason, setReason] = useState("");
  const save = useMutation({
    mutationFn: () => api(`/materials/${m.nmc}`, {
      method: "PATCH",
      body: {
        attributes: Object.fromEntries(rows.filter(([k]) => k)),
        standard_description: regenerate ? undefined : description,
        regenerate_description: regenerate,
        reason: reason || undefined,
      },
    }),
    onSuccess: (r) => {
      toast.success(r.changed ? `Saved · version ${r.version}` : "Nothing changed");
      qc.invalidateQueries({ queryKey: ["material", m.nmc] });
      qc.invalidateQueries({ queryKey: ["materials"] });
      onDone();
    },
    onError: (err) => toast.error(err.message),
  });
  const setRow = (i, pos, v) => setRows(rows.map((r, n) => (n === i ? (pos === 0 ? [v, r[1]] : [r[0], v]) : r)));

  return (
    <form onSubmit={(e) => { e.preventDefault(); save.mutate(); }} className="space-y-4">
      <div>
        <Label htmlFor="desc" hint="noun first, then attributes">Standard description</Label>
        <Textarea id="desc" rows={2} value={description} onChange={(e) => setDescription(e.target.value)} disabled={regenerate} />
        <label className="mt-2 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={regenerate} onChange={(e) => setRegenerate(e.target.checked)} className="size-4 accent-[var(--accent)]" />
          Rebuild the description from the attributes
        </label>
      </div>
      <div>
        <Label>Attributes</Label>
        <div className="space-y-2">
          {rows.map(([k, v], i) => (
            <div key={i} className="grid grid-cols-[1fr_1fr_auto] gap-2">
              <Select value={k} onChange={(e) => setRow(i, 0, e.target.value)} options={ATTR_OPTIONS} placeholder="Attribute…" aria-label="Attribute" />
              <Input value={v} onChange={(e) => setRow(i, 1, e.target.value)} aria-label="Value" placeholder="e.g. 12, 150#, SS316" />
              <Button variant="ghost" size="icon" onClick={() => setRows(rows.filter((_, n) => n !== i))} aria-label="Remove attribute"><Trash2 className="size-4" /></Button>
            </div>
          ))}
        </div>
        <Button variant="ghost" size="sm" className="mt-2" onClick={() => setRows([...rows, ["", ""]])}><Plus className="size-4" aria-hidden /> Add attribute</Button>
        <p className="mt-1 text-xs text-muted">Values are checked and written the same way the extractor writes them (e.g. “316” becomes “SS316”), so hard gates keep working.</p>
      </div>
      <div>
        <Label htmlFor="reason">Reason (kept in the audit trail)</Label>
        <Input id="reason" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. grade confirmed with IOCL stores" />
      </div>
      <div className="flex gap-2">
        <Button type="submit" loading={save.isPending}>Save changes</Button>
        <Button variant="ghost" onClick={onDone}>Cancel</Button>
      </div>
    </form>
  );
}

export default function MaterialDetail() {
  const { nmc } = useParams();
  const { can } = useAuth();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const q = useQuery({ queryKey: ["material", nmc], queryFn: () => api(`/materials/${nmc}`) });
  const applyUnspsc = useMutation({
    mutationFn: (code) => api(`/materials/${nmc}`, { method: "PATCH", body: { unspsc: code, reason: "UNSPSC suggestion accepted" } }),
    onSuccess: () => { toast.success("UNSPSC class saved"); qc.invalidateQueries({ queryKey: ["material", nmc] }); },
    onError: (err) => toast.error(err.message),
  });

  if (q.isPending) return <FullScreenLoader />;
  if (q.isError) {
    return (
      <GlassCard>
        <EmptyState icon={Boxes} title={q.error.status === 404 ? `${nmc} does not exist` : "Could not load this code"} text={q.error.message}
          action={<Link to="/materials"><Button variant="glass">Back to the national master</Button></Link>} />
      </GlassCard>
    );
  }
  const m = q.data;
  const isSteward = can("admin", "data_steward");
  const copy = async () => {
    try { await navigator.clipboard.writeText(m.nmc); toast.success("Code copied"); } catch { toast.error("Copy not allowed by the browser"); }
  };

  return (
    <div>
      <PageHeader
        eyebrow="National material"
        title={<span className="font-mono">{m.nmc}</span>}
        subtitle={m.standard_description}
        actions={
          <>
            <Button variant="glass" size="sm" onClick={copy}><Copy className="size-4" aria-hidden /> Copy code</Button>
            <Link to={`/graph/${m.nmc}`}><Button variant="glass" size="sm"><Share2 className="size-4" aria-hidden /> Graph</Button></Link>
            {isSteward && m.status === "active" && !editing && <Button size="sm" onClick={() => setEditing(true)}><Pencil className="size-4" aria-hidden /> Edit</Button>}
          </>
        }
      />

      {m.status === "deprecated" && (
        <div role="note" className="mb-4 flex flex-wrap items-center gap-2 rounded-2xl bg-warn/10 p-4 text-sm ring-1 ring-warn/25">
          This code was merged and is deprecated. It still resolves to the active code:
          <Link to={`/materials/${m.active_nmc}`} className="inline-flex items-center gap-1 font-mono font-semibold text-accent hover:underline">{m.active_nmc} <ArrowRight className="size-4" aria-hidden /></Link>
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-3">
        <GlassCard className="p-6 xl:col-span-2" spotlight={false}>
          {editing ? <EditForm m={m} onDone={() => setEditing(false)} /> : (
            <>
              <div className="mb-4 flex flex-wrap items-center gap-2">
                <Badge tone={m.status === "active" ? "ok" : "bad"} dot>{m.status}</Badge>
                {m.valid_check_digit
                  ? <Badge tone="ok"><ShieldCheck className="size-3" aria-hidden /> check digit valid</Badge>
                  : <Badge tone="bad"><ShieldAlert className="size-3" aria-hidden /> check digit invalid</Badge>}
                {m.noun && <Badge tone="accent">{m.noun}</Badge>}
                <SyntheticBadge show={m.synthetic} />
                <span className="text-xs text-muted">version {m.version}</span>
              </div>
              <h2 className="mb-2 text-sm font-semibold">Attributes</h2>
              {Object.keys(m.attributes).length ? (
                <dl className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                  {Object.entries(m.attributes).map(([k, v]) => (
                    <div key={k} className="rounded-2xl bg-surface/70 p-3 ring-1 ring-line">
                      <dt className="text-xs text-muted">{ATTRIBUTES[k] ?? k}</dt>
                      <dd className="font-mono text-sm font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
              ) : <p className="text-sm text-muted">No attributes were extracted for this material.</p>}
            </>
          )}
        </GlassCard>

        <GlassCard className="p-6" spotlight={false} delay={0.05}>
          <dl className="grid grid-cols-2 gap-4 text-sm">
            <div><dt className="text-xs text-muted">Legacy codes</dt><dd className="font-display text-2xl font-bold tabular-nums">{fmtNum(m.legacy_count)}</dd></div>
            <div><dt className="text-xs text-muted">CPSEs</dt><dd className="font-display text-2xl font-bold tabular-nums">{fmtNum(m.cpse_count)}</dd></div>
            <div><dt className="text-xs text-muted">Annual spend</dt><dd className="font-semibold tabular-nums">{fmtInr(m.spend)}</dd></div>
            <div><dt className="text-xs text-muted">Unit (UN/ECE)</dt><dd className="font-mono">{m.uom_code ?? "—"}</dd></div>
            <div className="col-span-2"><dt className="text-xs text-muted">UNSPSC</dt><dd className="font-mono">{m.unspsc ?? "not classified"}</dd></div>
          </dl>
          {m.unspsc_suggestions?.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-muted"><Tags className="size-3.5" aria-hidden /> UNSPSC suggestions</h3>
              <ul className="space-y-1.5">
                {m.unspsc_suggestions.map((s) => (
                  <li key={s.code} className="flex items-center gap-2 text-sm">
                    <span className="font-mono text-xs">{s.code}</span>
                    <span className="min-w-0 flex-1 truncate" title={s.title}>{s.title}</span>
                    {isSteward && m.status === "active" && s.code !== m.unspsc && (
                      <Button variant="ghost" size="sm" onClick={() => applyUnspsc.mutate(s.code)} loading={applyUnspsc.isPending && applyUnspsc.variables === s.code}>Use</Button>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
          {m.predecessors?.length > 0 && (
            <div className="mt-5">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Replaces merged codes</h3>
              <div className="flex flex-wrap gap-1.5">{m.predecessors.map((p) => <Link key={p} to={`/materials/${p}`}><Badge>{p}</Badge></Link>)}</div>
            </div>
          )}
        </GlassCard>
      </div>

      <GlassCard className="mt-4 overflow-hidden" spotlight={false}>
        <h2 className="px-6 pt-5 text-base font-semibold">Legacy codes mapped to this NMC</h2>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted"><tr>
              <th scope="col" className="px-6 py-2 text-left font-medium">CPSE</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Code</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Their description</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Unit</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Unit price</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Annual qty</th>
              <th scope="col" className="px-6 py-2 text-right font-medium">Confidence</th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {m.legacy.map((r) => (
                <tr key={r.id}>
                  <td className="px-6 py-2.5"><Badge>{r.cpse}</Badge></td>
                  <td className="px-3 py-2.5 font-mono text-xs">{r.legacy_code} <SyntheticBadge show={r.source === "synthetic"} /></td>
                  <td className="px-3 py-2.5">{r.description}</td>
                  <td className="px-3 py-2.5">{r.uom ?? "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{r.unit_price != null ? fmtInr(r.unit_price) : "—"}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{r.annual_qty != null ? fmtNum(r.annual_qty) : "—"}</td>
                  <td className="px-6 py-2.5 text-right tabular-nums">{r.confidence != null ? `${Math.round(r.confidence * 100)}%` : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </GlassCard>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <GlassCard className="p-6" spotlight={false}>
          <h2 className="mb-3 text-base font-semibold">Related pairs</h2>
          {m.pairs.length ? (
            <ul className="divide-y divide-line">
              {m.pairs.map((p) => (
                <li key={p.id} className="flex items-start gap-3 py-2.5 text-sm">
                  <span className="w-8 shrink-0 font-semibold tabular-nums">{Math.round(p.score * 100)}</span>
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap gap-1.5">
                      <Badge tone={PAIR_STATUS[p.status]?.tone}>{PAIR_STATUS[p.status]?.label ?? p.status}</Badge>
                      <Badge tone={MATCH[p.match_type]?.tone}>{MATCH[p.match_type]?.label ?? p.match_type}</Badge>
                    </div>
                    <p className="truncate"><span className="text-muted">{p.a.cpse}</span> {p.a.description}</p>
                    <p className="truncate"><span className="text-muted">{p.b.cpse}</span> {p.b.description}</p>
                  </div>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No pairs involve these legacy codes.</p>}
        </GlassCard>

        <GlassCard className="p-6" spotlight={false}>
          <h2 className="mb-3 flex items-center gap-2 text-base font-semibold"><History className="size-4 text-accent" aria-hidden /> History</h2>
          {m.history.length ? (
            <ol className="relative space-y-4 border-l border-line pl-5">
              {m.history.map((h) => (
                <li key={h.id} className="relative">
                  <span className="absolute -left-[25px] top-1.5 size-2.5 rounded-full bg-accent ring-4 ring-bg" aria-hidden />
                  <p className="text-sm"><span className="font-medium">{h.action}</span> <span className="text-muted">{h.entity.replace("_", " ")}</span> <span className="font-mono text-xs">{h.entity_id}</span></p>
                  <p className="text-xs text-muted">{h.actor_email} · {fmtDateTime(h.at)}{h.reason ? ` · “${h.reason}”` : ""}</p>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted">No history yet.</p>}
        </GlassCard>
      </div>
    </div>
  );
}
