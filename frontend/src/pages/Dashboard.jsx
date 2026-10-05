import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Boxes, Layers, GitCompareArrows, IndianRupee, UploadCloud, ArrowRight, Activity, FileSpreadsheet } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, PieChart, Pie, Cell, AreaChart, Area, Legend } from "recharts";
import { api } from "../lib/api";
import { fmtInr, fmtNum, timeAgo } from "../lib/format";
import { MATCH } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { PageHeader } from "../components/ui/PageHeader";
import { KpiCard } from "../components/dashboard/KpiCard";
import { ChartCard, ChartTooltip, axisProps, gridProps } from "../components/dashboard/ChartCard";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Badge } from "../components/ui/Badge";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";

const TYPE_COLOR = { EXACT_DUPLICATE: "#16a34a", NEAR_DUPLICATE: "#2451e6", FUNCTIONAL_EQUIVALENT: "#d97706", DIFFERENT: "#dc2626" };
const JOB_TONE = { done: "ok", error: "bad", running: "accent", queued: "accent", uploaded: "muted" };

export default function Dashboard() {
  const { user, can } = useAuth();
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api("/analytics/kpis"), refetchInterval: 30_000 });
  const byCpse = useQuery({ queryKey: ["analytics", "by-cpse"], queryFn: () => api("/analytics/by-cpse") });
  const types = useQuery({ queryKey: ["analytics", "match-types"], queryFn: () => api("/analytics/match-types") });
  const activity = useQuery({ queryKey: ["analytics", "activity", 30], queryFn: () => api("/analytics/activity?days=30") });
  const k = kpis.data;
  const empty = k && k.legacy_items === 0;

  const donut = (types.data?.by_type ?? []).map((t) => ({ key: t.match_type, name: MATCH[t.match_type]?.label ?? t.match_type, value: t.total }));

  return (
    <div>
      <PageHeader
        eyebrow="Overview"
        title={`Namaste, ${user?.name?.split(" ")[0] ?? ""}`}
        subtitle="The national material master at a glance: every number below is computed live from the database."
        actions={
          <>
            {can("admin", "data_steward", "cpse_user") && <Link to="/ingest"><Button variant="glass"><UploadCloud className="size-4" aria-hidden /> Upload data</Button></Link>}
            <Link to="/review"><Button><GitCompareArrows className="size-4" aria-hidden /> Review matches</Button></Link>
          </>
        }
      />

      {kpis.isError && <p role="alert" className="mb-4 rounded-2xl bg-bad/10 p-3 text-sm text-bad">Could not load figures: {kpis.error.message}</p>}

      {empty ? (
        <GlassCard>
          <EmptyState
            icon={FileSpreadsheet}
            title="No material data yet"
            text="Upload a CPSE material master export (CSV or Excel) to start finding duplicates and issuing national codes."
            action={can("admin", "data_steward", "cpse_user") && <Link to="/ingest"><Button><UploadCloud className="size-4" aria-hidden /> Upload the first file</Button></Link>}
          />
        </GlassCard>
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <KpiCard label="Legacy material codes" value={k?.legacy_items} icon={Layers} loading={kpis.isLoading}
              hint={k ? `${k.cpses_onboarded} CPSEs · ${k.mapped_pct}% mapped` : undefined} />
            <KpiCard label="National codes (NMC)" value={k?.national_codes} icon={Boxes} tone="ok" delay={0.04} loading={kpis.isLoading}
              hint={k ? `${fmtNum(k.codes_eliminated)} legacy codes consolidated` : undefined} />
            <KpiCard label="Waiting for review" value={k?.pending_review} icon={GitCompareArrows} tone="warn" delay={0.08} loading={kpis.isLoading}
              hint={k ? `${fmtNum(k.pairs.blocked)} blocked by rules` : undefined} />
            <KpiCard label="Aggregation value" value={k?.aggregation_value} format={fmtInr} icon={IndianRupee} tone="saffron" delay={0.12} loading={kpis.isLoading}
              hint={k ? `${fmtNum(k.aggregation_opportunities)} codes bought by 2+ CPSEs` : undefined} />
          </div>
          {k?.synthetic_items > 0 && (
            <p className="mt-3 text-xs text-muted"><Badge tone="warn">Synthetic</Badge> {fmtNum(k.synthetic_items)} of the legacy rows are generated demo data.</p>
          )}

          <div className="mt-6 grid gap-4 xl:grid-cols-3">
            <ChartCard className="xl:col-span-2" title="Materials by CPSE" subtitle="Legacy codes uploaded and how many already map to a national code"
              loading={byCpse.isLoading} empty={byCpse.data?.length === 0 && "No CPSE has uploaded data yet."}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byCpse.data ?? []} barGap={4}>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="code" {...axisProps} />
                  <YAxis {...axisProps} width={48} />
                  <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Bar dataKey="items" name="Legacy codes" fill="#2451e6" radius={[6, 6, 0, 0]} />
                  <Bar dataKey="mapped" name="Mapped to NMC" fill="#138808" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>

            <ChartCard title="Match types" subtitle="All candidate pairs found so far" delay={0.05}
              loading={types.isLoading} empty={donut.length === 0 && "No pairs yet. Upload files from two CPSEs."}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={donut} dataKey="value" nameKey="name" innerRadius="58%" outerRadius="85%" paddingAngle={3} stroke="none">
                    {donut.map((d) => <Cell key={d.key} fill={TYPE_COLOR[d.key] ?? "#94a3b8"} />)}
                  </Pie>
                  <Tooltip content={<ChartTooltip />} />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                </PieChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-3">
            <ChartCard className="xl:col-span-2" title="Activity" subtitle="Audited actions per day, last 30 days" height={220}
              loading={activity.isLoading} empty={activity.data && activity.data.series.every((d) => d.total === 0) && "No activity in the last 30 days."}>
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={activity.data?.series ?? []}>
                  <defs>
                    <linearGradient id="actFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#2451e6" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#2451e6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid {...gridProps} />
                  <XAxis dataKey="date" {...axisProps} tickFormatter={(d) => d.slice(5)} minTickGap={24} />
                  <YAxis {...axisProps} width={40} allowDecimals={false} />
                  <Tooltip content={<ChartTooltip />} />
                  <Area type="monotone" dataKey="total" name="Actions" stroke="#2451e6" strokeWidth={2} fill="url(#actFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </ChartCard>

            <GlassCard className="p-5" delay={0.05} spotlight={false}>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="flex items-center gap-2 text-base font-semibold"><Activity className="size-4 text-accent" aria-hidden /> Recent uploads</h2>
                <Link to="/ingest" className="text-xs text-accent hover:underline">All uploads</Link>
              </div>
              {activity.isLoading ? <SkeletonRows rows={4} /> : activity.data?.jobs.length ? (
                <ul className="space-y-2">
                  {activity.data.jobs.map((j) => (
                    <li key={j.id}>
                      <Link to={`/ingest?job=${j.id}`} className="flex items-center gap-3 rounded-xl p-2 hover:bg-fg/5">
                        <FileSpreadsheet className="size-4 shrink-0 text-muted" aria-hidden />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium">{j.filename}</p>
                          <p className="text-xs text-muted">{j.cpse} · {fmtNum(j.total_rows)} rows · {timeAgo(j.created_at)}</p>
                        </div>
                        <Badge tone={JOB_TONE[j.status] ?? "muted"}>{j.status}</Badge>
                      </Link>
                    </li>
                  ))}
                </ul>
              ) : <p className="text-sm text-muted">No uploads yet.</p>}
            </GlassCard>
          </div>

          <GlassCard className="mt-4 p-5" spotlight={false}>
            <h2 className="mb-3 text-base font-semibold">Latest changes</h2>
            {activity.isLoading ? <SkeletonRows rows={5} /> : activity.data?.recent.length ? (
              <ul className="divide-y divide-line">
                {activity.data.recent.map((a, i) => (
                  <li key={`${a.at}-${i}`} className="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 text-sm">
                    <Badge tone={a.action === "approve" ? "ok" : a.action === "reject" ? "bad" : "muted"}>{a.action}</Badge>
                    <span className="text-muted">{a.entity.replace("_", " ")}</span>
                    <span className="truncate font-mono text-xs">{a.entity_id}</span>
                    <span className="ml-auto text-xs text-muted">{a.actor_email} · {timeAgo(a.at)}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">Nothing has happened yet.</p>}
            <Link to="/review" className="mt-3 inline-flex items-center gap-1 text-sm font-medium text-accent hover:underline">
              Continue reviewing <ArrowRight className="size-4" aria-hidden />
            </Link>
          </GlassCard>
        </>
      )}
    </div>
  );
}
