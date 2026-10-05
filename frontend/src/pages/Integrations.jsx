import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileSpreadsheet, FileText, Server, KeyRound, Webhook, Copy, Trash2, Send, Plus, CheckCircle2, XCircle } from "lucide-react";
import { api, download } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useAuth } from "../providers/AuthProvider";
import { useJobStream } from "../hooks/useJobStream";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Input, Label } from "../components/ui/Input";
import { Select } from "../components/ui/Select";
import { Badge } from "../components/ui/Badge";
import { SkeletonRows } from "../components/ui/Skeleton";
import { StageStepper } from "../components/ingest/StageStepper";

const copy = async (text, what = "Copied") => {
  try { await navigator.clipboard.writeText(text); toast.success(what); } catch { toast.error("Copy not allowed by the browser"); }
};

function Section({ icon: Icon, title, text, children, delay }) {
  return (
    <GlassCard className="p-6" spotlight={false} delay={delay}>
      <div className="mb-4 flex items-start gap-3">
        <div className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent/10 text-accent ring-1 ring-accent/20"><Icon className="size-5" aria-hidden /></div>
        <div><h2 className="text-base font-semibold">{title}</h2><p className="text-sm text-muted">{text}</p></div>
      </div>
      {children}
    </GlassCard>
  );
}

function useCpseOptions() {
  const cpses = useQuery({ queryKey: ["cpses"], queryFn: () => api("/cpses"), staleTime: Infinity });
  return (cpses.data ?? []).map((c) => ({ value: c.code, label: `${c.code} · ${c.name}` }));
}

function ExportCard({ user }) {
  const own = user?.role === "cpse_user";
  const options = useCpseOptions();
  const [cpse, setCpse] = useState(own ? user.cpse ?? "" : "");
  const [busy, setBusy] = useState("");
  const get = async (fmt) => {
    setBusy(fmt);
    try {
      await download(`/integrations/export/${cpse}?format=${fmt}`, `NMC_mapping_${cpse}.${fmt}`);
      toast.success(`Mapping for ${cpse} downloaded`);
    } catch (err) {
      toast.error(err.message);
    } finally {
      setBusy("");
    }
  };
  return (
    <Section icon={FileSpreadsheet} title="SAP mapping export"
      text="Every legacy MATNR of a CPSE with its national code, standard description, UNSPSC and UN/ECE unit, ready to load into SAP.">
      <div className="flex flex-wrap items-end gap-2">
        <div className="min-w-56 flex-1">
          <Label htmlFor="exp-cpse">CPSE</Label>
          <Select id="exp-cpse" value={cpse} onChange={(e) => setCpse(e.target.value)} options={options} placeholder="Choose a CPSE…" disabled={own} />
        </div>
        <Button onClick={() => get("xlsx")} loading={busy === "xlsx"} disabled={!cpse || !!busy}><FileSpreadsheet className="size-4" aria-hidden /> Excel</Button>
        <Button variant="glass" onClick={() => get("csv")} loading={busy === "csv"} disabled={!cpse || !!busy}><FileText className="size-4" aria-hidden /> CSV</Button>
      </div>
      <p className="mt-3 font-mono text-[11px] text-muted">CPSE · MATNR · MAKTX · MEINS · NMC · NMC_DESCRIPTION · UNSPSC · UOM_UNECE · CONFIDENCE · NMC_STATUS</p>
    </Section>
  );
}

function SapCard() {
  const qc = useQueryClient();
  const options = useCpseOptions();
  const status = useQuery({ queryKey: ["sap"], queryFn: () => api("/integrations/sap") });
  const [cpse, setCpse] = useState("");
  const [top, setTop] = useState(200);
  const [jobId, setJobId] = useState(null);
  const job = useJobStream(jobId);
  const test = useMutation({ mutationFn: () => api("/integrations/sap/test", { method: "POST", body: {} }), onError: (err) => toast.error(err.message) });
  const pull = useMutation({
    mutationFn: () => api("/integrations/sap/pull", { method: "POST", body: { cpse_code: cpse, top: Number(top) } }),
    onSuccess: (j) => { setJobId(j.id); qc.invalidateQueries({ queryKey: ["jobs"] }); toast.success("SAP pull started"); },
    onError: (err) => toast.error(err.message),
  });
  const configured = status.data?.configured;

  return (
    <Section icon={Server} title="SAP S/4HANA · Product Master (OData)" delay={0.04}
      text="Pull products live from API_PRODUCT_SRV and run them through the same pipeline as a file upload.">
      {status.isLoading ? <SkeletonRows rows={2} /> : (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2 text-sm">
            {configured ? <Badge tone="ok" dot>configured</Badge> : <Badge tone="warn" dot>not configured</Badge>}
            <span className="truncate font-mono text-xs text-muted">{status.data?.base_url || "Set SAP_BASE_URL and SAP_API_KEY in .env"}</span>
          </div>
          <Button variant="glass" size="sm" onClick={() => test.mutate()} loading={test.isPending} disabled={!configured}>Test connection</Button>
          {test.data && (
            <div className={`rounded-2xl p-3 text-sm ring-1 ${test.data.ok ? "bg-ok/8 ring-ok/20" : "bg-bad/8 ring-bad/20"}`}>
              <p className="flex items-center gap-2 font-medium">
                {test.data.ok ? <CheckCircle2 className="size-4 text-ok" aria-hidden /> : <XCircle className="size-4 text-bad" aria-hidden />}
                {test.data.ok ? "Connected" : "Failed"}{test.data.status ? ` · HTTP ${test.data.status}` : ""}
              </p>
              <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] text-muted">
                {typeof test.data.sample === "string" ? test.data.sample : JSON.stringify(test.data.sample, null, 2)}
              </pre>
            </div>
          )}
          <div className="flex flex-wrap items-end gap-2 border-t border-line pt-4">
            <div className="min-w-48 flex-1">
              <Label htmlFor="sap-cpse">Load into CPSE</Label>
              <Select id="sap-cpse" value={cpse} onChange={(e) => setCpse(e.target.value)} options={options} placeholder="Choose a CPSE…" />
            </div>
            <div className="w-28">
              <Label htmlFor="sap-top">Products</Label>
              <Input id="sap-top" type="number" min={1} max={5000} value={top} onChange={(e) => setTop(e.target.value)} />
            </div>
            <Button onClick={() => pull.mutate()} loading={pull.isPending} disabled={!configured || !cpse || !(top >= 1 && top <= 5000)}>Pull from SAP</Button>
          </div>
          {jobId && <div className="border-t border-line pt-4">{job ? <StageStepper job={job} /> : <SkeletonRows rows={1} />}</div>}
        </div>
      )}
    </Section>
  );
}

function ApiKeysCard() {
  const qc = useQueryClient();
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: () => api("/integrations/api-keys") });
  const [name, setName] = useState("");
  const [created, setCreated] = useState(null);
  const create = useMutation({
    mutationFn: () => api("/integrations/api-keys", { method: "POST", body: { name: name.trim() } }),
    onSuccess: (k) => { setCreated(k); setName(""); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (err) => toast.error(err.message),
  });
  const revoke = useMutation({
    mutationFn: (id) => api(`/integrations/api-keys/${id}`, { method: "DELETE" }),
    onSuccess: () => { toast.success("Key revoked"); qc.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (err) => toast.error(err.message),
  });
  return (
    <Section icon={KeyRound} title="API keys" delay={0.08}
      text="For ERP jobs and BI tools. Keys are read-only (they can read and export mappings) and are sent in the X-API-Key header.">
      <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="flex gap-2">
        <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Key name, e.g. IOCL SAP PI" aria-label="Key name" />
        <Button type="submit" loading={create.isPending} disabled={name.trim().length < 2}><Plus className="size-4" aria-hidden /> Create</Button>
      </form>
      {created && (
        <div role="status" className="mt-3 rounded-2xl bg-warn/10 p-3 text-sm ring-1 ring-warn/25">
          <p className="font-medium">Copy this key now: it will not be shown again.</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg bg-surface px-2 py-1 font-mono text-xs">{created.key}</code>
            <Button size="sm" variant="glass" onClick={() => copy(created.key, "Key copied")}><Copy className="size-4" aria-hidden /></Button>
          </div>
        </div>
      )}
      <div className="mt-4">
        {keys.isLoading ? <SkeletonRows rows={2} /> : keys.data?.length ? (
          <ul className="divide-y divide-line">
            {keys.data.map((k) => (
              <li key={k.id} className="flex items-center gap-3 py-2 text-sm">
                <KeyRound className="size-4 text-muted" aria-hidden />
                <div className="min-w-0 flex-1"><p className="font-medium">{k.name}</p><p className="font-mono text-xs text-muted">{k.prefix}… · {timeAgo(k.created_at)}</p></div>
                <Button variant="ghost" size="sm" onClick={() => window.confirm(`Revoke "${k.name}"? Systems using it will stop working.`) && revoke.mutate(k.id)} aria-label={`Revoke ${k.name}`}><Trash2 className="size-4 text-bad" /></Button>
              </li>
            ))}
          </ul>
        ) : <p className="py-2 text-sm text-muted">No API keys yet.</p>}
      </div>
    </Section>
  );
}

function WebhooksCard() {
  const qc = useQueryClient();
  const hooks = useQuery({ queryKey: ["webhooks"], queryFn: () => api("/integrations/webhooks") });
  const [url, setUrl] = useState("");
  const [events, setEvents] = useState([]);
  const [secret, setSecret] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["webhooks"] });
  const create = useMutation({
    mutationFn: () => api("/integrations/webhooks", { method: "POST", body: { url: url.trim(), events } }),
    onSuccess: (h) => { setSecret(h.secret); setUrl(""); setEvents([]); refresh(); },
    onError: (err) => toast.error(err.message),
  });
  const patch = useMutation({ mutationFn: ({ id, body }) => api(`/integrations/webhooks/${id}`, { method: "PATCH", body }), onSuccess: refresh, onError: (err) => toast.error(err.message) });
  const remove = useMutation({ mutationFn: (id) => api(`/integrations/webhooks/${id}`, { method: "DELETE" }), onSuccess: () => { toast.success("Webhook deleted"); refresh(); }, onError: (err) => toast.error(err.message) });
  const test = useMutation({
    mutationFn: (id) => api(`/integrations/webhooks/${id}/test`, { method: "POST" }),
    onSuccess: (r) => (r.ok ? toast.success(`Delivered · HTTP ${r.status}`) : toast.error(r.status ? `Receiver answered HTTP ${r.status}` : "Receiver unreachable")),
    onSettled: refresh,
  });
  const all = [...(hooks.data?.events ?? []), "*"];
  const toggle = (e) => setEvents(events.includes(e) ? events.filter((x) => x !== e) : [...events, e]);

  return (
    <Section icon={Webhook} title="Webhooks" delay={0.12}
      text="Signed POSTs when codes change. Verify X-EkCode-Signature = sha256=HMAC-SHA256(secret, raw body).">
      <form onSubmit={(e) => { e.preventDefault(); create.mutate(); }} className="space-y-3">
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://erp.example.gov.in/ekcode-hook" aria-label="Webhook URL" />
        <fieldset className="flex flex-wrap gap-2">
          <legend className="sr-only">Events</legend>
          {all.map((e) => (
            <label key={e} className={`cursor-pointer rounded-full px-3 py-1 font-mono text-xs ring-1 ${events.includes(e) ? "bg-accent text-white ring-accent" : "bg-fg/5 text-muted ring-line"}`}>
              <input type="checkbox" className="sr-only" checked={events.includes(e)} onChange={() => toggle(e)} />{e === "*" ? "all events" : e}
            </label>
          ))}
        </fieldset>
        <Button type="submit" loading={create.isPending} disabled={!/^https?:\/\//i.test(url.trim()) || !events.length}><Plus className="size-4" aria-hidden /> Add webhook</Button>
      </form>
      {secret && (
        <div role="status" className="mt-3 rounded-2xl bg-warn/10 p-3 text-sm ring-1 ring-warn/25">
          <p className="font-medium">Signing secret (shown once)</p>
          <div className="mt-2 flex items-center gap-2">
            <code className="min-w-0 flex-1 truncate rounded-lg bg-surface px-2 py-1 font-mono text-xs">{secret}</code>
            <Button size="sm" variant="glass" onClick={() => copy(secret, "Secret copied")}><Copy className="size-4" aria-hidden /></Button>
          </div>
        </div>
      )}
      <div className="mt-4">
        {hooks.isLoading ? <SkeletonRows rows={2} /> : hooks.data?.items.length ? (
          <ul className="divide-y divide-line">
            {hooks.data.items.map((h) => (
              <li key={h.id} className="flex flex-wrap items-center gap-2 py-2.5 text-sm">
                <div className="min-w-0 flex-1">
                  <p className="truncate font-mono text-xs">{h.url}</p>
                  <p className="text-xs text-muted">{h.events.join(", ")} · last status {h.last_status ?? "never sent"}</p>
                </div>
                <label className="flex items-center gap-1.5 text-xs">
                  <input type="checkbox" checked={h.active} onChange={(e) => patch.mutate({ id: h.id, body: { active: e.target.checked } })} className="size-4 accent-[var(--accent)]" /> active
                </label>
                <Button variant="ghost" size="sm" onClick={() => test.mutate(h.id)} loading={test.isPending && test.variables === h.id} aria-label="Send a test event"><Send className="size-4" /></Button>
                <Button variant="ghost" size="sm" onClick={() => window.confirm("Delete this webhook?") && remove.mutate(h.id)} aria-label="Delete webhook"><Trash2 className="size-4 text-bad" /></Button>
              </li>
            ))}
          </ul>
        ) : <p className="py-2 text-sm text-muted">No webhooks yet.</p>}
      </div>
    </Section>
  );
}

export default function Integrations() {
  const { user, can } = useAuth();
  return (
    <div>
      <PageHeader eyebrow="Step 3 of 3" title="Integrations"
        subtitle="Send national codes back to SAP, pull materials from SAP, and connect other systems." />
      <div className="grid gap-4 xl:grid-cols-2">
        <ExportCard user={user} />
        {can("admin", "data_steward") && <SapCard />}
        {can("admin") && <ApiKeysCard />}
        {can("admin") && <WebhooksCard />}
      </div>
    </div>
  );
}
