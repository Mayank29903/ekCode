import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Play, RotateCcw, GitCompareArrows, FileSpreadsheet, CheckCircle2, Hourglass } from "lucide-react";
import { api } from "../lib/api";
import { fmtNum, timeAgo } from "../lib/format";
import { SAP_FIELDS } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { useJobStream } from "../hooks/useJobStream";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Select } from "../components/ui/Select";
import { Label } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { FullScreenLoader, SkeletonRows } from "../components/ui/Skeleton";
import { Dropzone } from "../components/ingest/Dropzone";
import { ColumnMapper } from "../components/ingest/ColumnMapper";
import { StageStepper } from "../components/ingest/StageStepper";

const JOB_TONE = { done: "ok", error: "bad", running: "accent", queued: "accent", uploaded: "muted" };
const clean = (m) => Object.fromEntries(Object.entries(m ?? {}).filter(([, v]) => v));
const where = (row) => (row == null ? "line" : `row ${row}`);

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl bg-surface/70 p-3 ring-1 ring-line">
      <p className="text-xs text-muted">{label}</p>
      <p className="font-display text-xl font-bold tabular-nums">{fmtNum(value)}</p>
    </div>
  );
}

function JobResult({ job, onAgain }) {
  const r = job.report ?? {};
  return (
    <div className="mt-6 space-y-4">
      <div className="flex items-center gap-2 text-ok"><CheckCircle2 className="size-5" aria-hidden /><p className="font-semibold">{job.filename} is processed</p></div>
      <div className="grid gap-3 sm:grid-cols-4">
        <Stat label="Valid rows" value={r.valid_rows ?? job.processed_rows} />
        <Stat label="New or changed" value={r.new_or_changed ?? 0} />
        <Stat label="Unchanged (skipped)" value={r.unchanged ?? 0} />
        <Stat label="Rows with errors" value={job.error_rows} />
      </div>
      {r.errors?.length > 0 && (
        <details className="rounded-2xl bg-bad/5 p-3 ring-1 ring-bad/20">
          <summary className="cursor-pointer text-sm font-medium text-bad">{r.errors.length} rows were skipped</summary>
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs">
            {r.errors.map((e, i) => <li key={i}><span className="font-mono">{where(e.row)}</span>: {e.error}</li>)}
          </ul>
        </details>
      )}
      {r.warnings?.length > 0 && (
        <details className="rounded-2xl bg-warn/5 p-3 ring-1 ring-warn/20">
          <summary className="cursor-pointer text-sm font-medium text-warn">{r.warnings.length} warnings</summary>
          <ul className="mt-2 max-h-48 space-y-1 overflow-y-auto text-xs">
            {r.warnings.map((w, i) => <li key={i}><span className="font-mono">{where(w.row)}</span>: {w.warning}</li>)}
          </ul>
        </details>
      )}
      <div className="flex flex-wrap gap-2">
        <Link to="/review"><Button><GitCompareArrows className="size-4" aria-hidden /> Review the matches</Button></Link>
        <Button variant="glass" onClick={onAgain}><RotateCcw className="size-4" aria-hidden /> Upload another file</Button>
      </div>
    </div>
  );
}

export default function Ingest() {
  const { user, can } = useAuth();
  const qc = useQueryClient();
  const [params, setParams] = useSearchParams();
  const jobId = params.get("job");
  const [restartKey, setRestartKey] = useState(0);
  const job = useJobStream(jobId, restartKey);
  const [cpse, setCpse] = useState(user?.role === "cpse_user" ? user.cpse ?? "" : "");
  const [upload, setUpload] = useState(null);
  const [mapping, setMapping] = useState({});

  const cpses = useQuery({ queryKey: ["cpses"], queryFn: () => api("/cpses"), staleTime: Infinity });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api("/ingest/jobs"),
    refetchInterval: (q) => (q.state.data?.some((j) => ["queued", "running"].includes(j.status) && !j.stale) ? 3000 : false),
  });

  const uploadMut = useMutation({
    mutationFn: (file) => {
      const form = new FormData();
      form.append("file", file);
      form.append("cpse_code", cpse);
      return api("/ingest/upload", { method: "POST", form });
    },
    onSuccess: (res) => {
      setUpload(res);
      setMapping(res.suggested_mapping ?? {});
      toast.success(`${res.job.filename}: ${fmtNum(res.job.total_rows)} rows read`);
      if (res.bad_lines > 0) {
        toast.warning(`${fmtNum(res.bad_lines)} lines could not be split into columns and will be skipped (listed in the report).`);
      }
    },
    onError: (err) => toast.error(err.message),
  });

  const start = useMutation({
    mutationFn: ({ id, map }) => api(`/ingest/${id}/start`, { method: "POST", body: { mapping: clean(map) } }),
    onSuccess: (j) => {
      setUpload(null);
      setParams({ job: j.id });
      setRestartKey((k) => k + 1);                       // reconnect the progress stream, also for the same job
      qc.invalidateQueries({ queryKey: ["jobs"] });
      toast.success("Processing started");
    },
    onError: (err) => toast.error(err.message),
  });

  const reset = () => { setUpload(null); setMapping({}); setParams({}); };
  const missing = SAP_FIELDS.filter((f) => f.required && !mapping[f.key]);
  const canUpload = can("admin", "data_steward", "cpse_user");
  const canRetry = job && job.column_map && (job.status === "error" || job.stale);

  if (!canUpload) {
    return <GlassCard><EmptyState icon={FileSpreadsheet} title="Uploads are for CPSE users and data stewards" text="Your role can browse and audit the master, but not upload files." /></GlassCard>;
  }

  return (
    <div>
      <PageHeader eyebrow="Step 1 of 3" title="Upload material data"
        subtitle="Add a CPSE's SAP/ERP material master export. Columns are mapped automatically; re-uploading the same file only processes rows that changed." />

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <GlassCard className="p-6" spotlight={false}>
          {jobId ? (
            <>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">Processing{job?.filename ? `: ${job.filename}` : ""}</h2>
                <div className="flex gap-2">
                  {canRetry && (
                    <Button size="sm" loading={start.isPending} onClick={() => start.mutate({ id: job.id, map: job.column_map })}>
                      <RotateCcw className="size-4" aria-hidden /> {job.stale ? "Restart" : "Try again"}
                    </Button>
                  )}
                  {job && job.status !== "done" && <Button variant="ghost" size="sm" onClick={reset}>Upload a different file</Button>}
                </div>
              </div>
              {job?.stale && (
                <p role="status" className="mb-4 flex items-start gap-2 rounded-2xl bg-warn/10 p-3 text-sm ring-1 ring-warn/25">
                  <Hourglass className="mt-0.5 size-4 shrink-0 text-warn" aria-hidden />
                  No progress for a long time: the background worker may have stopped. Check that it runs
                  (<span className="font-mono text-xs">docker compose ps worker</span>), then restart this job. Already processed rows are not repeated.
                </p>
              )}
              {!job ? <FullScreenLoader /> : job.status === "uploaded" ? (
                <EmptyState icon={FileSpreadsheet} title="This file was uploaded but never started"
                  text="Its columns were not confirmed. Upload it again to choose the columns and start processing."
                  action={<Button variant="glass" onClick={reset}>Upload again</Button>} />
              ) : <StageStepper job={job} />}
              {job?.status === "done" && <JobResult job={job} onAgain={reset} />}
            </>
          ) : upload ? (
            <>
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold">Check the columns</h2>
                  <p className="text-sm text-muted">{upload.job.filename} · {fmtNum(upload.job.total_rows)} rows · for {cpse}</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={reset}>Cancel</Button>
                  <Button onClick={() => start.mutate({ id: upload.job.id, map: mapping })} loading={start.isPending} disabled={missing.length > 0}>
                    {!start.isPending && <Play className="size-4" aria-hidden />} Start processing
                  </Button>
                </div>
              </div>
              {missing.length > 0 && <p role="alert" className="mb-4 text-sm text-bad">Choose a column for: {missing.map((f) => f.label).join(", ")}</p>}
              <ColumnMapper columns={upload.columns} mapping={mapping} suggested={upload.suggested_mapping} onChange={setMapping} preview={upload.preview} />
            </>
          ) : (
            <div className="space-y-5">
              <div className="max-w-xs">
                <Label htmlFor="cpse">CPSE this file belongs to</Label>
                <Select id="cpse" value={cpse} onChange={(e) => setCpse(e.target.value)} disabled={user?.role === "cpse_user"}
                  placeholder="Choose a CPSE…" options={(cpses.data ?? []).map((c) => ({ value: c.code, label: `${c.code} · ${c.name}` }))} />
              </div>
              <Dropzone onFile={(f) => uploadMut.mutate(f)} disabled={!cpse} busy={uploadMut.isPending} />
              {!cpse && <p className="text-sm text-muted">Choose the CPSE first.</p>}
            </div>
          )}
        </GlassCard>

        <GlassCard className="p-5" spotlight={false} delay={0.05}>
          <h2 className="mb-3 text-base font-semibold">Recent uploads</h2>
          {jobs.isLoading ? <SkeletonRows rows={5} /> : jobs.data?.length ? (
            <ul className="space-y-1">
              {jobs.data.map((j) => (
                <li key={j.id}>
                  <button onClick={() => { setUpload(null); setParams({ job: j.id }); }} aria-current={j.id === jobId ? "true" : undefined}
                    className={`flex w-full items-center gap-3 rounded-xl p-2 text-left hover:bg-fg/5 ${j.id === jobId ? "bg-accent/8 ring-1 ring-accent/20" : ""}`}>
                    <FileSpreadsheet className="size-4 shrink-0 text-muted" aria-hidden />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{j.filename}</p>
                      <p className="text-xs text-muted">{fmtNum(j.total_rows)} rows · {timeAgo(j.created_at)}</p>
                    </div>
                    <Badge tone={j.stale ? "warn" : JOB_TONE[j.status] ?? "muted"}>{j.stale ? "stalled" : j.status}</Badge>
                  </button>
                </li>
              ))}
            </ul>
          ) : <p className="text-sm text-muted">No uploads yet.</p>}
        </GlassCard>
      </div>
    </div>
  );
}
