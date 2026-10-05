import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { SlidersHorizontal, BookA, BrainCircuit, Users, Lock, Plus, Trash2, RotateCcw, Save, Play, Power, Search as SearchIcon, KeySquare } from "lucide-react";
import { api, qs } from "../lib/api";
import { fmtDateTime, fmtNum, timeAgo } from "../lib/format";
import { ATTRIBUTES, AUDIT_READERS, ROLE_LABEL } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { useDebounce } from "../hooks/useDebounce";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Input, Label } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { cn } from "../lib/cn";

const THRESHOLDS = [
  { key: "review_floor", label: "Review floor", help: "Pairs scoring below this are not shown to stewards at all." },
  { key: "equivalent", label: "Works the same", help: "From here a pair can be classed as a functional equivalent." },
  { key: "near", label: "Probably same", help: "From here a pair is classed as a near duplicate." },
  { key: "auto_suggest", label: "Auto-approve floor", help: "Exact duplicates at or above this are approved automatically, if auto-approve is on." },
];
const BAND = ["bg-fg/10", "bg-bad/40", "bg-warn/50", "bg-accent/60", "bg-ok/70"];
const MIN = 0.3;
const onError = (err) => toast.error(err.message);

/* ---------------------------------------------------------------- matching */

function MatchingForm({ data, isAdmin }) {
  const qc = useQueryClient();
  const [th, setTh] = useState(data.thresholds);
  const [flags, setFlags] = useState(data.flags);
  const ordered = th.review_floor <= th.equivalent && th.equivalent <= th.near && th.near <= th.auto_suggest;
  const changed = JSON.stringify({ th, flags }) !== JSON.stringify({ th: data.thresholds, flags: data.flags });
  const rescore = useMutation({
    mutationFn: () => api("/admin/rescore", { method: "POST" }),
    onSuccess: () => toast.success("Re-scoring open suggestions in the background"),
    onError,
  });
  const save = useMutation({
    mutationFn: () => api("/admin/settings", { method: "PUT", body: { thresholds: th, flags } }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "settings"] });
      toast.success("Settings saved. New uploads use them now.", { action: { label: "Re-score open pairs", onClick: () => rescore.mutate() } });
    },
    onError,
  });
  const pct = (v) => ((v - MIN) / (1 - MIN)) * 100;
  const cuts = [MIN, th.review_floor, th.equivalent, th.near, th.auto_suggest, 1];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex h-3 overflow-hidden rounded-full" aria-hidden>
          {BAND.map((b, i) => <div key={i} className={b} style={{ width: `${Math.max(0, pct(cuts[i + 1]) - pct(cuts[i]))}%` }} />)}
        </div>
        <div className="mt-1 flex justify-between text-[11px] text-muted"><span>{MIN}</span><span>score</span><span>1.00</span></div>
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        {THRESHOLDS.map(({ key, label, help }) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-sm">
              <label htmlFor={`th-${key}`} className="font-medium">{label}</label>
              <span className="font-mono tabular-nums">{th[key].toFixed(2)}</span>
            </div>
            <input id={`th-${key}`} type="range" min={MIN} max={1} step={0.01} value={th[key]} disabled={!isAdmin}
              onChange={(e) => setTh({ ...th, [key]: Number(e.target.value) })} className="w-full accent-[var(--accent)]" />
            <p className="text-xs text-muted">{help}</p>
          </div>
        ))}
      </div>
      {!ordered && <p role="alert" className="text-sm text-bad">Keep the order: review floor ≤ works the same ≤ probably same ≤ auto-approve floor.</p>}

      <div className="space-y-3 border-t border-line pt-5">
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={flags.auto_approve_exact} disabled={!isAdmin}
            onChange={(e) => setFlags({ ...flags, auto_approve_exact: e.target.checked })} />
          <span><span className="font-medium">Auto-approve exact duplicates</span><br />
            <span className="text-muted">Only pairs with the same words, the same attributes, no unit conflict and no rule conflict. Audited as “system”. Off by default (ADR-19).</span></span>
        </label>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-0.5 size-4 accent-[var(--accent)]" checked={flags.use_llm} disabled={!isAdmin}
            onChange={(e) => setFlags({ ...flags, use_llm: e.target.checked })} />
          <span><span className="font-medium">Use the language model to fill missing attributes</span><br />
            <span className="text-muted">
              Provider: <span className="font-mono">{data.llm_provider}</span>
              {data.llm_provider === "noop" ? " (none configured: this switch has no effect until LLM_PROVIDER is set)" : ". Every answer is validated; it never decides a match."}
            </span></span>
        </label>
        <p className="text-xs text-muted">Embedding model: <span className="font-mono">{data.embed_model}</span></p>
      </div>

      {isAdmin ? (
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => save.mutate()} loading={save.isPending} disabled={!ordered || !changed}><Save className="size-4" aria-hidden /> Save</Button>
          <Button variant="glass" onClick={() => rescore.mutate()} loading={rescore.isPending}><RotateCcw className="size-4" aria-hidden /> Re-score open pairs</Button>
        </div>
      ) : <p className="text-sm text-muted">Read-only: only administrators can change matching settings.</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- dictionary */

function Preview() {
  const [text, setText] = useState("");
  const d = useDebounce(text.trim(), 350);
  const p = useQuery({ queryKey: ["admin", "preview", d], queryFn: () => api(`/admin/preview${qs({ text: d })}`), enabled: d.length >= 2 });
  return (
    <div className="rounded-2xl bg-surface/60 p-4 ring-1 ring-line">
      <Label htmlFor="try">Try it (uses the saved dictionary)</Label>
      <Input id="try" icon={SearchIcon} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. SS HX BLT M12 L50" />
      {p.data && (
        <div className="mt-3 space-y-2 text-sm">
          <p><span className="text-muted">Normalized:</span> <span className="font-mono">{p.data.normalized}</span></p>
          <p><span className="text-muted">Standard:</span> <span className="font-mono">{p.data.standard_description}</span></p>
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(p.data.attributes).map(([k, v]) => <Badge key={k} tone="accent">{ATTRIBUTES[k] ?? k}: {v} · {Math.round((p.data.confidence[k] ?? 0) * 100)}%</Badge>)}
          </div>
        </div>
      )}
    </div>
  );
}

function DictionaryEditor({ data, isAdmin }) {
  const qc = useQueryClient();
  const nextId = useRef(Object.keys(data.abbreviations).length);
  const [rows, setRows] = useState(() => Object.entries(data.abbreviations).map(([k, v], id) => ({ id, k, v })));
  const [filter, setFilter] = useState("");
  const f = filter.trim().toLowerCase();
  const visible = rows.filter((r) => !f || r.k.includes(f) || r.v.includes(f));
  const keys = rows.map((r) => r.k.trim().toLowerCase()).filter(Boolean);
  const dupes = [...new Set(keys.filter((k, i) => keys.indexOf(k) !== i))];
  const invalid = rows.some((r) => (r.k.trim() && !r.v.trim()) || /\s/.test(r.k.trim()));
  const done = () => qc.invalidateQueries({ queryKey: ["admin", "dictionary"] });
  const save = useMutation({
    mutationFn: () => api("/admin/dictionary", {
      method: "PUT",
      body: { abbreviations: Object.fromEntries(rows.filter((r) => r.k.trim() && r.v.trim()).map((r) => [r.k.trim().toLowerCase(), r.v.trim().toLowerCase()])) },
    }),
    onSuccess: () => { toast.success("Dictionary saved. It applies to the next upload."); done(); },
    onError,
  });
  const reset = useMutation({
    mutationFn: () => api("/admin/dictionary/reset", { method: "POST" }),
    onSuccess: () => { toast.success("Dictionary reset to the shipped version"); done(); },
    onError,
  });
  const update = (id, field, value) => setRows(rows.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

  return (
    <div className="grid gap-5 xl:grid-cols-[1fr_360px]">
      <div>
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <div className="min-w-56 flex-1"><Input icon={SearchIcon} value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter abbreviations…" aria-label="Filter abbreviations" /></div>
          <Badge tone={data.custom ? "accent" : "muted"}>{data.custom ? "customised" : "shipped version"} · {fmtNum(rows.length)} entries</Badge>
        </div>
        {isAdmin && (
          <div className="mb-3 flex flex-wrap gap-2">
            <Button variant="glass" size="sm" onClick={() => { setRows([{ id: nextId.current++, k: "", v: "" }, ...rows]); setFilter(""); }}><Plus className="size-4" aria-hidden /> Add</Button>
            <Button size="sm" onClick={() => save.mutate()} loading={save.isPending} disabled={dupes.length > 0 || invalid}><Save className="size-4" aria-hidden /> Save dictionary</Button>
            {data.custom && <Button variant="ghost" size="sm" loading={reset.isPending} onClick={() => window.confirm("Replace your changes with the shipped dictionary?") && reset.mutate()}><RotateCcw className="size-4" aria-hidden /> Reset</Button>}
          </div>
        )}
        {dupes.length > 0 && <p role="alert" className="mb-2 text-sm text-bad">Listed twice: {dupes.join(", ")}</p>}
        {invalid && <p role="alert" className="mb-2 text-sm text-bad">Every abbreviation needs an expansion, and abbreviations are single words.</p>}
        <div className="max-h-[60vh] overflow-y-auto rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-surface text-xs uppercase tracking-wider text-muted"><tr>
              <th scope="col" className="px-3 py-2 text-left font-medium">Written as</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Means</th>
              {isAdmin && <th scope="col" className="w-10 px-3 py-2"><span className="sr-only">Remove</span></th>}
            </tr></thead>
            <tbody className="divide-y divide-line">
              {visible.slice(0, 400).map((r) => (
                <tr key={r.id}>
                  <td className="px-3 py-1.5">
                    {isAdmin ? <Input value={r.k} onChange={(e) => update(r.id, "k", e.target.value)} className="h-8 font-mono" aria-label="Abbreviation" /> : <span className="font-mono">{r.k}</span>}
                  </td>
                  <td className="px-3 py-1.5">
                    {isAdmin ? <Input value={r.v} onChange={(e) => update(r.id, "v", e.target.value)} className="h-8" aria-label="Expansion" /> : r.v}
                  </td>
                  {isAdmin && (
                    <td className="px-3 py-1.5">
                      <button onClick={() => setRows(rows.filter((x) => x.id !== r.id))} className="rounded-lg p-1.5 text-muted hover:bg-bad/10 hover:text-bad" aria-label={`Remove ${r.k}`}><Trash2 className="size-4" /></button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
          {visible.length > 400 && <p className="p-3 text-xs text-muted">Showing 400 of {fmtNum(visible.length)}. Use the filter to find others.</p>}
        </div>
      </div>
      <div className="space-y-3">
        <Preview />
        <p className="text-xs text-muted">Abbreviations are expanded before attributes are read, e.g. “blt” → “bolt”, “ss” → “stainless steel”. Changes apply to new uploads; existing rows keep their current reading until they are uploaded again.</p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- learning model */

function Readiness({ label, have, need }) {
  const pct = Math.min(100, Math.round((have / Math.max(need, 1)) * 100));
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs"><span className="text-muted">{label}</span><span className="tabular-nums">{fmtNum(have)} / {fmtNum(need)}</span></div>
      <div className="h-2 overflow-hidden rounded-full bg-fg/5"><div className={cn("h-full rounded-full", pct >= 100 ? "bg-ok" : "bg-accent")} style={{ width: `${pct}%` }} /></div>
    </div>
  );
}

function ModelPanel({ isAdmin }) {
  const qc = useQueryClient();
  const models = useQuery({ queryKey: ["admin", "models"], queryFn: () => api("/admin/models") });
  const [jobId, setJobId] = useState(null);
  const job = useQuery({
    queryKey: ["admin", "job", jobId],
    queryFn: () => api(`/admin/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q) => (["finished", "failed", "stopped", "canceled"].includes(q.state.data?.status) ? false : 1500),
  });
  const status = job.data?.status;
  useEffect(() => {
    if (status === "finished") {
      toast.success(`Model ${job.data.result?.version ?? ""} trained. Review its metrics, then activate it.`);
      qc.invalidateQueries({ queryKey: ["admin", "models"] });
      setJobId(null);
    } else if (status === "failed" || status === "stopped" || status === "canceled") {
      toast.error(`Training ${status}: ${(job.data.error ?? "").trim().split("\n").pop() || "see the worker log"}`);
      setJobId(null);
    }
  }, [status]); // eslint-disable-line react-hooks/exhaustive-deps

  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin", "models"] }); qc.invalidateQueries({ queryKey: ["kpis"] }); };
  const retrain = useMutation({ mutationFn: () => api("/admin/retrain", { method: "POST" }), onSuccess: (r) => { setJobId(r.job_id); toast("Training started"); }, onError });
  const activate = useMutation({ mutationFn: (v) => api(`/admin/models/${v}/activate`, { method: "POST" }), onSuccess: (r) => { toast.success(`${r.active} is now scoring new pairs`); refresh(); }, onError });
  const deactivate = useMutation({ mutationFn: () => api("/admin/models/deactivate", { method: "POST" }), onSuccess: () => { toast.success("Back to the weighted formula"); refresh(); }, onError });

  if (models.isPending) return <SkeletonRows rows={5} />;
  if (models.isError) return <p role="alert" className="text-sm text-bad">{models.error.message}</p>;
  const { items, active, labels } = models.data;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
        <Readiness label="Labelled pairs" have={labels.positives + labels.negatives} need={labels.min_rows} />
        <Readiness label={`Smaller class (${labels.positives <= labels.negatives ? "approved" : "rejected + blocked"})`} have={Math.min(labels.positives, labels.negatives)} need={labels.min_per_class} />
        {isAdmin && (
          <Button onClick={() => retrain.mutate()} loading={retrain.isPending || !!jobId} disabled={!labels.ready}>
            {!(retrain.isPending || jobId) && <Play className="size-4" aria-hidden />} {jobId ? `Training… (${status ?? "queued"})` : "Retrain now"}
          </Button>
        )}
      </div>
      <p className="text-xs text-muted">
        Labels come from steward decisions: {fmtNum(labels.approved)} approved, {fmtNum(labels.rejected)} rejected, and {fmtNum(labels.blocked)} blocked by rules.
        Hard gates always run before the model, whichever scorer is active.
      </p>

      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="text-muted">Active scorer:</span>
        <Badge tone={active === "weighted-v1" ? "muted" : "ok"} dot>{active === "weighted-v1" ? "weighted formula (cold start)" : active}</Badge>
        {isAdmin && active !== "weighted-v1" && (
          <Button variant="ghost" size="sm" loading={deactivate.isPending} onClick={() => deactivate.mutate()}><Power className="size-4" aria-hidden /> Use weighted formula</Button>
        )}
      </div>

      {items.length ? (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted"><tr>
              <th scope="col" className="px-4 py-2 text-left font-medium">Version</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Precision</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Recall</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">F1</th>
              <th scope="col" className="px-3 py-2 text-right font-medium">Pairs</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Trained</th>
              <th scope="col" className="px-4 py-2"><span className="sr-only">Actions</span></th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {items.map((m) => (
                <tr key={m.version}>
                  <td className="px-4 py-2.5 font-mono text-xs">{m.version} {m.active && <Badge tone="ok" className="ml-1">active</Badge>}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{m.metrics.precision?.toFixed(3)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{m.metrics.recall?.toFixed(3)}</td>
                  <td className="px-3 py-2.5 text-right font-semibold tabular-nums">{m.metrics.f1?.toFixed(3)}</td>
                  <td className="px-3 py-2.5 text-right tabular-nums">{fmtNum(m.metrics.n)}</td>
                  <td className="px-3 py-2.5 text-xs text-muted" title={fmtDateTime(m.created_at)}>{timeAgo(m.created_at)}</td>
                  <td className="px-4 py-2.5 text-right">
                    {isAdmin && !m.active && <Button variant="glass" size="sm" loading={activate.isPending && activate.variables === m.version} onClick={() => activate.mutate(m.version)}>Activate</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-sm text-muted">No trained models yet. Metrics are 5-fold cross-validated on steward decisions.</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- users */

const ROLE_OPTIONS = Object.entries(ROLE_LABEL).map(([value, label]) => ({ value, label }));

function UsersPanel() {
  const qc = useQueryClient();
  const users = useQuery({ queryKey: ["admin", "users"], queryFn: () => api("/admin/users") });
  const cpses = useQuery({ queryKey: ["cpses"], queryFn: () => api("/cpses"), staleTime: Infinity });
  const cpseOptions = (cpses.data ?? []).map((c) => ({ value: c.code, label: c.code }));
  const blank = { email: "", name: "", role: "data_steward", cpse_code: "", password: "" };
  const [form, setForm] = useState(blank);
  const [pw, setPw] = useState({ id: null, value: "" });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "users"] });
  const create = useMutation({
    mutationFn: () => api("/admin/users", { method: "POST", body: { ...form, email: form.email.trim(), cpse_code: form.cpse_code || null } }),
    onSuccess: (u) => { toast.success(`${u.email} can now sign in`); setForm(blank); refresh(); },
    onError,
  });
  const patch = useMutation({
    mutationFn: ({ id, body }) => api(`/admin/users/${id}`, { method: "PATCH", body }),
    onSuccess: (_u, { body }) => { toast.success(body.password ? "Password changed" : "User updated"); setPw({ id: null, value: "" }); refresh(); },
    onError,
  });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const formOk = /^[^@\s]+@[^@\s]+$/.test(form.email.trim()) && form.name.trim().length >= 2 && form.password.length >= 10 && (form.role !== "cpse_user" || form.cpse_code);

  return (
    <div className="space-y-6">
      <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="grid gap-3 rounded-2xl bg-surface/60 p-4 ring-1 ring-line md:grid-cols-3 xl:grid-cols-6 xl:items-end">
        <div className="xl:col-span-2"><Label htmlFor="u-email">Email</Label><Input id="u-email" type="email" value={form.email} onChange={set("email")} autoComplete="off" /></div>
        <div><Label htmlFor="u-name">Name</Label><Input id="u-name" value={form.name} onChange={set("name")} /></div>
        <div><Label htmlFor="u-role">Role</Label><Select id="u-role" value={form.role} onChange={set("role")} options={ROLE_OPTIONS} /></div>
        <div><Label htmlFor="u-cpse" hint={form.role === "cpse_user" ? "required" : "optional"}>CPSE</Label><Select id="u-cpse" value={form.cpse_code} onChange={set("cpse_code")} options={cpseOptions} placeholder="None" /></div>
        <div><Label htmlFor="u-pw" hint="min 10">Password</Label><Input id="u-pw" type="password" value={form.password} onChange={set("password")} autoComplete="new-password" /></div>
        <div className="md:col-span-3 xl:col-span-6"><Button type="submit" loading={create.isPending} disabled={!formOk}><Plus className="size-4" aria-hidden /> Add user</Button></div>
      </form>

      {users.isLoading ? <SkeletonRows rows={4} /> : (
        <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
          <table className="w-full text-sm">
            <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted"><tr>
              <th scope="col" className="px-4 py-2 text-left font-medium">User</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Role</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">CPSE</th>
              <th scope="col" className="px-3 py-2 text-left font-medium">Since</th>
              <th scope="col" className="px-4 py-2 text-left font-medium">Password</th>
            </tr></thead>
            <tbody className="divide-y divide-line">
              {(users.data ?? []).map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-2.5"><p className="font-medium">{u.name}</p><p className="text-xs text-muted">{u.email}</p></td>
                  <td className="px-3 py-2.5 min-w-40"><Select value={u.role} options={ROLE_OPTIONS} aria-label={`Role of ${u.email}`} onChange={(e) => patch.mutate({ id: u.id, body: { role: e.target.value } })} /></td>
                  <td className="px-3 py-2.5 min-w-32"><Select value={u.cpse ?? ""} options={cpseOptions} placeholder="None" aria-label={`CPSE of ${u.email}`} onChange={(e) => patch.mutate({ id: u.id, body: { cpse_code: e.target.value } })} /></td>
                  <td className="px-3 py-2.5 text-xs text-muted">{timeAgo(u.created_at)}</td>
                  <td className="px-4 py-2.5">
                    {pw.id === u.id ? (
                      <form onSubmit={(e) => { e.preventDefault(); patch.mutate({ id: u.id, body: { password: pw.value } }); }} className="flex gap-1.5">
                        <Input type="password" value={pw.value} onChange={(e) => setPw({ id: u.id, value: e.target.value })} className="h-8 w-40" aria-label="New password" autoComplete="new-password" autoFocus />
                        <Button type="submit" size="sm" disabled={pw.value.length < 10}>Set</Button>
                        <Button size="sm" variant="ghost" onClick={() => setPw({ id: null, value: "" })}>Cancel</Button>
                      </form>
                    ) : <Button variant="ghost" size="sm" onClick={() => setPw({ id: u.id, value: "" })}><KeySquare className="size-4" aria-hidden /> Reset</Button>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted">CPSE users only upload, see jobs and export for their own CPSE. Auditors can read everything, including the audit trail, and change nothing. At least one admin always remains.</p>
    </div>
  );
}

/* ---------------------------------------------------------------- page */

export default function Settings() {
  const { can } = useAuth();
  const isAdmin = can("admin");
  const allowed = can(...AUDIT_READERS);
  const [tab, setTab] = useState("matching");
  const settings = useQuery({ queryKey: ["admin", "settings"], queryFn: () => api("/admin/settings"), enabled: allowed });
  const dict = useQuery({ queryKey: ["admin", "dictionary"], queryFn: () => api("/admin/dictionary"), enabled: allowed && tab === "dictionary" });

  if (!allowed) return <GlassCard><EmptyState icon={Lock} title="Settings are for stewards, auditors and admins" /></GlassCard>;

  const tabs = [
    ["matching", "Matching", SlidersHorizontal],
    ["dictionary", "Dictionary", BookA],
    ["model", "Learning model", BrainCircuit],
    ...(isAdmin ? [["users", "Users", Users]] : []),
  ];

  return (
    <div>
      <PageHeader eyebrow="Settings" title="How EkCode matches and learns"
        subtitle={isAdmin ? "Changes are audited and apply to the next upload." : "You can see the settings; only administrators can change them."} />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist" aria-label="Settings sections">
        {tabs.map(([k, label, Icon]) => (
          <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
            className={cn("flex items-center gap-2 rounded-xl px-3 py-1.5 text-sm font-medium", tab === k ? "bg-surface shadow-sm ring-1 ring-line" : "text-muted hover:bg-fg/5")}>
            <Icon className="size-4" aria-hidden /> {label}
          </button>
        ))}
      </div>
      <GlassCard className="p-6" spotlight={false} key={tab}>
        {tab === "matching" && (settings.isLoading ? <SkeletonRows rows={6} /> : settings.isError ? <p role="alert" className="text-sm text-bad">{settings.error.message}</p>
          : <MatchingForm key={JSON.stringify(settings.data)} data={settings.data} isAdmin={isAdmin} />)}
        {tab === "dictionary" && (dict.isLoading ? <SkeletonRows rows={8} /> : dict.isError ? <p role="alert" className="text-sm text-bad">{dict.error.message}</p>
          : <DictionaryEditor key={dict.dataUpdatedAt} data={dict.data} isAdmin={isAdmin} />)}
        {tab === "model" && <ModelPanel isAdmin={isAdmin} />}
        {tab === "users" && isAdmin && <UsersPanel />}
      </GlassCard>
    </div>
  );
}
