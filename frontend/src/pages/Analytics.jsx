import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Download, IndianRupee, Layers, Scissors, PiggyBank } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from "recharts";
import { api, saveBlob } from "../lib/api";
import { fmtInr, fmtNum, toCsv } from "../lib/format";
import { ATTRIBUTES, MATCH } from "../lib/constants";
import { PageHeader } from "../components/ui/PageHeader";
import { KpiCard } from "../components/dashboard/KpiCard";
import { ChartCard, ChartTooltip, axisProps, gridProps } from "../components/dashboard/ChartCard";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { SkeletonRows } from "../components/ui/Skeleton";

const STATUS_COLOR = { suggested: "#2451e6", approved: "#16a34a", rejected: "#94a3b8", blocked: "#dc2626" };

export default function Analytics() {
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api("/analytics/kpis") });
  const byCpse = useQuery({ queryKey: ["analytics", "by-cpse"], queryFn: () => api("/analytics/by-cpse") });
  const cats = useQuery({ queryKey: ["analytics", "categories"], queryFn: () => api("/analytics/categories?limit=12") });
  const types = useQuery({ queryKey: ["analytics", "match-types"], queryFn: () => api("/analytics/match-types") });
  const agg = useQuery({ queryKey: ["analytics", "aggregation"], queryFn: () => api("/analytics/aggregation?limit=25") });
  const k = kpis.data;

  const typeRows = (types.data?.by_type ?? []).map((t) => ({ ...t, name: MATCH[t.match_type]?.label ?? t.match_type }));
  const gateRows = (types.data?.blocked_by_gate ?? []).map((g) => ({ ...g, name: ATTRIBUTES[g.gate] ?? g.gate }));
  const hist = (types.data?.score_histogram ?? []).map((b) => ({ ...b, name: `${Math.round(b.from * 100)}–${Math.round(b.to * 100)}` }));

  const exportAgg = () => {
    const rows = (agg.data?.items ?? []).map((r) => ({
      NMC: r.nmc, Description: r.standard_description, CPSEs: r.cpses.join(" "), Legacy_codes: r.legacy_count,
      Annual_qty: r.annual_qty, Annual_value_INR: Math.round(r.annual_value), Lowest_unit_price: r.min_price,
      Highest_unit_price: r.max_price, Savings_potential_INR: Math.round(r.savings_potential), Synthetic: r.synthetic ? "yes" : "no",
    }));
    saveBlob(new Blob(["﻿" + toCsv(rows)], { type: "text/csv" }), "ekcode_aggregation_opportunities.csv");
  };

  return (
    <div>
      <PageHeader eyebrow="Analytics" title="Where the duplicates and the savings are"
        subtitle="Spend is unit price × annual quantity from the uploaded files; rows without both are left out." />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiCard label="Annual spend covered" value={k?.total_spend} format={fmtInr} icon={IndianRupee} loading={kpis.isLoading}
          hint={k ? `${fmtInr(k.mapped_spend)} already mapped to NMCs` : undefined} />
        <KpiCard label="Legacy codes consolidated" value={k?.codes_eliminated} icon={Scissors} tone="ok" delay={0.04} loading={kpis.isLoading}
          hint={k ? `${fmtNum(k.duplicate_items)} items share an NMC` : undefined} />
        <KpiCard label="Bought by 2+ CPSEs" value={agg.data?.total_value} format={fmtInr} icon={Layers} tone="saffron" delay={0.08} loading={agg.isLoading}
          hint={agg.data ? `${fmtNum(agg.data.total_opportunities)} national codes` : undefined} />
        <KpiCard label="Savings at best price" value={agg.data?.total_savings_potential} format={fmtInr} icon={PiggyBank} tone="warn" delay={0.12} loading={agg.isLoading}
          hint="If every CPSE paid the lowest unit price paid by any of them" />
      </div>

      <div className="mt-6 grid gap-4 xl:grid-cols-2">
        <ChartCard title="Duplicates by CPSE" subtitle="Legacy codes, codes mapped to an NMC, and codes that share an NMC with another"
          loading={byCpse.isLoading} empty={byCpse.data?.length === 0 && "No data uploaded yet."}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={byCpse.data ?? []}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="code" {...axisProps} />
              <YAxis {...axisProps} width={48} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="items" name="Legacy codes" fill="#2451e6" radius={[6, 6, 0, 0]} />
              <Bar dataKey="mapped" name="Mapped" fill="#138808" radius={[6, 6, 0, 0]} />
              <Bar dataKey="duplicates" name="Duplicates" fill="#ff9933" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Material categories" subtitle="Legacy codes per material type (from attribute extraction)" delay={0.04}
          loading={cats.isLoading} empty={cats.data?.length === 0 && "No data uploaded yet."}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={cats.data ?? []} layout="vertical" margin={{ left: 24 }}>
              <CartesianGrid {...gridProps} vertical horizontal={false} />
              <XAxis type="number" {...axisProps} />
              <YAxis type="category" dataKey="noun" {...axisProps} width={120} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
              <Bar dataKey="items" name="Legacy codes" fill="#2451e6" radius={[0, 6, 6, 0]} />
              <Bar dataKey="mapped" name="Mapped" fill="#138808" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Match types and decisions" subtitle="Every candidate pair, by type and what happened to it"
          loading={types.isLoading} empty={typeRows.length === 0 && "No pairs yet."}>
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={typeRows}>
              <CartesianGrid {...gridProps} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis {...axisProps} width={48} />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {Object.entries(STATUS_COLOR).map(([s, c]) => <Bar key={s} dataKey={s} name={s} stackId="s" fill={c} />)}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-1 2xl:grid-cols-2">
          <ChartCard title="Score distribution" subtitle="Pairs not blocked, by score" height={220} delay={0.04}
            loading={types.isLoading} empty={hist.every((b) => !b.count) && "No scored pairs yet."}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hist}>
                <XAxis dataKey="name" {...axisProps} interval={1} />
                <YAxis {...axisProps} width={40} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
                <Bar dataKey="count" name="Pairs" fill="#7c3aed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
          <ChartCard title="Blocked by rule" subtitle="Which critical attribute stopped a look-alike" height={220} delay={0.06}
            loading={types.isLoading} empty={gateRows.length === 0 && "No blocked pairs yet."}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={gateRows} layout="vertical">
                <XAxis type="number" {...axisProps} allowDecimals={false} />
                <YAxis type="category" dataKey="name" {...axisProps} width={110} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "var(--line)" }} />
                <Bar dataKey="count" name="Pairs" fill="#dc2626" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </ChartCard>
        </div>
      </div>

      <GlassCard className="mt-4 overflow-hidden" spotlight={false}>
        <div className="flex flex-wrap items-center justify-between gap-3 px-6 pt-5">
          <div>
            <h2 className="text-base font-semibold">Demand aggregation opportunities</h2>
            <p className="text-xs text-muted">The same national code bought by two or more CPSEs, largest combined value first.</p>
          </div>
          <Button variant="glass" size="sm" onClick={exportAgg} disabled={!agg.data?.items.length}><Download className="size-4" aria-hidden /> CSV</Button>
        </div>
        {agg.isLoading ? <div className="p-6"><SkeletonRows rows={5} /></div> : agg.data?.items.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted"><tr>
                <th scope="col" className="px-6 py-2 text-left font-medium">NMC</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">Material</th>
                <th scope="col" className="px-3 py-2 text-left font-medium">CPSEs</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Annual qty</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Unit price range</th>
                <th scope="col" className="px-3 py-2 text-right font-medium">Combined value</th>
                <th scope="col" className="px-6 py-2 text-right font-medium">Savings potential</th>
              </tr></thead>
              <tbody className="divide-y divide-line">
                {agg.data.items.map((r) => (
                  <tr key={r.nmc}>
                    <td className="px-6 py-2.5"><Link to={`/materials/${r.nmc}`} className="font-mono text-xs text-accent hover:underline">{r.nmc}</Link> <SyntheticBadge show={r.synthetic} /></td>
                    <td className="max-w-sm px-3 py-2.5">{r.standard_description}</td>
                    <td className="px-3 py-2.5"><div className="flex flex-wrap gap-1">{r.cpses.map((c) => <Badge key={c}>{c}</Badge>)}</div></td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{fmtNum(r.annual_qty)}</td>
                    <td className="px-3 py-2.5 text-right tabular-nums">{r.min_price != null ? `${fmtInr(r.min_price)} – ${fmtInr(r.max_price)}` : "—"}</td>
                    <td className="px-3 py-2.5 text-right font-medium tabular-nums">{fmtInr(r.annual_value)}</td>
                    <td className="px-6 py-2.5 text-right font-semibold tabular-nums text-ok">{fmtInr(r.savings_potential)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <p className="px-6 py-6 text-sm text-muted">No national code is shared by two CPSEs yet. Approve cross-CPSE matches to see opportunities.</p>}
      </GlassCard>
    </div>
  );
}
