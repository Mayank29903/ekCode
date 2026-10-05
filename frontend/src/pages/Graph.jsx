import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ReactFlow, Background, Controls, Handle, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Boxes, Building2, FileText, BookOpen, Tag, Layers, Archive, Search as SearchIcon, Share2 } from "lucide-react";
import { api, qs } from "../lib/api";
import { fmtInr, fmtNum } from "../lib/format";
import { useTheme } from "../hooks/useTheme";
import { useDebounce } from "../hooks/useDebounce";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Input } from "../components/ui/Input";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { FullScreenLoader, SkeletonRows } from "../components/ui/Skeleton";
import { cn } from "../lib/cn";

const KIND = {
  nmc: { icon: Boxes, cls: "bg-accent text-white ring-accent", mono: true },
  deprecated: { icon: Archive, cls: "bg-surface text-muted ring-line line-through", mono: true },
  legacy: { icon: FileText, cls: "bg-surface text-fg ring-line", mono: true },
  cpse: { icon: Building2, cls: "bg-saffron/15 text-fg ring-saffron/40" },
  standard: { icon: BookOpen, cls: "bg-indgreen/12 text-fg ring-indgreen/35" },
  category: { icon: Layers, cls: "bg-navy/12 text-fg ring-navy/35" },
  unspsc: { icon: Tag, cls: "bg-purple-500/12 text-fg ring-purple-500/35" },
};
const EDGE = {
  maps_to: { stroke: "var(--accent)", width: 2 },
  owns: { stroke: "var(--muted)", width: 1 },
  succeeded_by: { stroke: "var(--accent)", width: 2, dash: "6 4" },
  possible_duplicate: { stroke: "var(--color-warn)", width: 2, dash: "5 5", animated: true },
  blocked: { stroke: "var(--color-bad)", width: 1.5, dash: "2 4" },
  conforms_to: { stroke: "var(--muted)", width: 1, dash: "1 4" },
  is_a: { stroke: "var(--muted)", width: 1, dash: "1 4" },
  classified_as: { stroke: "var(--muted)", width: 1, dash: "1 4" },
};

function EkNode({ data }) {
  const k = KIND[data.kind] ?? KIND.legacy;
  const Icon = k.icon;
  return (
    <div className={cn("max-w-[220px] rounded-2xl px-3 py-2 text-xs shadow-sm ring-1", k.cls, data.center && "px-4 py-3 text-sm shadow-lg ring-2")}>
      <Handle type="target" position={Position.Top} isConnectable={false} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1.5">
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span className={cn("truncate font-semibold", k.mono && "font-mono")}>{data.label}</span>
      </div>
      {data.sub && <div className="mt-0.5 line-clamp-2 text-[10px] opacity-80">{data.sub}</div>}
      <Handle type="source" position={Position.Bottom} isConnectable={false} className="!border-0 !bg-transparent" />
    </div>
  );
}
const nodeTypes = { ek: EkNode };

const polar = (r, a) => ({ x: r * Math.cos(a), y: r * Math.sin(a) });

/** Radial layout: members around the NMC, their CPSEs outside them, metadata above, neighbours on the rim. */
function layout(g) {
  const pos = { [g.center]: { x: 0, y: 0 } };
  const members = new Set(g.edges.filter((e) => e.type === "maps_to" && e.target === g.center).map((e) => e.source));
  const others = g.nodes.filter((n) => n.id !== g.center);
  const ring = (list, r, start = -Math.PI / 2, span = 2 * Math.PI) =>
    list.forEach((n, i) => { pos[n.id] = polar(r, start + (span * (i + 0.5)) / Math.max(list.length, 1)); });

  ring(others.filter((n) => members.has(n.id)), 240);
  ring(others.filter((n) => ["standard", "category", "unspsc"].includes(n.type)), 150, -Math.PI * 0.85, Math.PI * 0.7);
  const cpses = others.filter((n) => n.type === "cpse");
  cpses.forEach((n, i) => {
    const owned = g.edges.filter((e) => e.source === n.id && members.has(e.target)).map((e) => pos[e.target]).filter(Boolean);
    if (owned.length) {
      const a = Math.atan2(owned.reduce((s, p) => s + p.y, 0), owned.reduce((s, p) => s + p.x, 0));
      pos[n.id] = polar(430, a + i * 0.02);
    } else pos[n.id] = polar(430, (2 * Math.PI * i) / cpses.length);
  });
  ring(others.filter((n) => !pos[n.id]), 560, Math.PI / 6);
  return pos;
}

function toFlow(g) {
  const pos = layout(g);
  const nodes = g.nodes.map((n) => ({
    id: n.id,
    type: "ek",
    position: pos[n.id] ?? { x: 0, y: 0 },
    data: {
      kind: n.type, label: n.label, center: n.id === g.center, raw: n,
      sub: n.type === "legacy" ? `${n.data.cpse} · ${n.data.description}` : n.id === g.center ? n.data.description : undefined,
    },
  }));
  const edges = g.edges.map((e) => {
    const s = EDGE[e.type] ?? EDGE.owns;
    return {
      id: e.id, source: e.source, target: e.target, type: "straight", animated: !!s.animated,
      label: e.type === "possible_duplicate" || e.type === "blocked" ? `${Math.round((e.data.score ?? 0) * 100)}` : undefined,
      style: { stroke: s.stroke, strokeWidth: s.width, strokeDasharray: s.dash },
      labelStyle: { fontSize: 10, fill: "var(--fg)" },
      labelBgStyle: { fill: "var(--surface)" },
    };
  });
  return { nodes, edges };
}

function Start() {
  const [q, setQ] = useState("");
  const dq = useDebounce(q.trim(), 300);
  const list = useQuery({ queryKey: ["graph-start", dq], queryFn: () => api(`/graph${qs({ q: dq })}`) });
  return (
    <div>
      <PageHeader eyebrow="Knowledge graph" title="How a national code connects"
        subtitle="Pick a national code to see its legacy codes, the CPSEs that hold them, its standard and category, merged codes and open look-alikes." />
      <GlassCard className="mb-4 p-4" spotlight={false}>
        <Input icon={SearchIcon} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter by NMC or description…" aria-label="Filter national codes" />
      </GlassCard>
      {list.isLoading ? <GlassCard className="p-6"><SkeletonRows rows={6} /></GlassCard> : list.data?.items.length ? (
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          {list.data.items.map((m, i) => (
            <Link key={m.nmc} to={`/graph/${m.nmc}`}>
              <GlassCard className="h-full p-4" delay={i * 0.03}>
                <p className="font-mono text-sm font-semibold text-accent">{m.nmc}</p>
                <p className="mt-1 line-clamp-2 text-sm">{m.standard_description}</p>
                <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-muted">
                  <span>{fmtNum(m.legacy_count)} codes · {m.cpse_count} CPSEs</span>
                  <SyntheticBadge show={m.synthetic} />
                </div>
              </GlassCard>
            </Link>
          ))}
        </div>
      ) : (
        <GlassCard><EmptyState icon={Share2} title="No national codes yet" text="Approve a match on the Review page to create the first one."
          action={<Link to="/review"><Button variant="glass">Go to review</Button></Link>} /></GlassCard>
      )}
    </div>
  );
}

function GraphView({ nmc }) {
  const navigate = useNavigate();
  const { theme } = useTheme();
  const [selected, setSelected] = useState(null);
  const g = useQuery({ queryKey: ["graph", nmc], queryFn: () => api(`/graph/${nmc}`) });
  const flow = useMemo(() => (g.data ? toFlow(g.data) : null), [g.data]);

  if (g.isPending) return <FullScreenLoader />;             // isPending, not isLoading: also while offline/paused
  if (g.isError) return <GlassCard><EmptyState icon={Share2} title="Could not load the graph" text={g.error.message} action={<Link to="/graph"><Button variant="glass">Choose another code</Button></Link>} /></GlassCard>;
  const m = g.data.material;
  const sel = selected?.data?.raw;

  return (
    <div>
      <PageHeader eyebrow="Knowledge graph" title={<span className="font-mono">{m.nmc}</span>} subtitle={m.standard_description}
        actions={<><Link to={`/materials/${m.nmc}`}><Button variant="glass" size="sm">Open material</Button></Link><Link to="/graph"><Button variant="ghost" size="sm">Other codes</Button></Link></>} />
      <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
        <div className="glass h-[70vh] overflow-hidden rounded-3xl">
          <ReactFlow
            defaultNodes={flow.nodes} defaultEdges={flow.edges} nodeTypes={nodeTypes} colorMode={theme} fitView fitViewOptions={{ padding: 0.2 }}
            nodesConnectable={false} edgesFocusable={false} minZoom={0.2} proOptions={{ hideAttribution: true }}
            onNodeClick={(_, node) => {
              const raw = node.data.raw;
              if (["nmc", "deprecated"].includes(raw.type) && !node.data.center) navigate(`/graph/${raw.label}`);
              else setSelected(node);
            }}
          >
            <Background gap={24} size={1} />
            <Controls showInteractive={false} />
          </ReactFlow>
        </div>
        <GlassCard className="p-5" spotlight={false}>
          <h2 className="mb-3 text-sm font-semibold">Legend</h2>
          <ul className="mb-5 grid grid-cols-2 gap-2 text-xs">
            {Object.entries(KIND).map(([k, v]) => {
              const Icon = v.icon;
              return <li key={k} className="flex items-center gap-1.5"><Icon className="size-3.5 text-muted" aria-hidden />{k}</li>;
            })}
            <li className="col-span-2 text-muted"><span className="text-warn">- - -</span> open look-alike · <span className="text-bad">· · ·</span> blocked by rule</li>
          </ul>
          <h2 className="mb-2 text-sm font-semibold">Selected</h2>
          {!sel ? <p className="text-sm text-muted">Click a node. Clicking another national code opens its graph.</p> : (
            <div className="space-y-2 text-sm">
              <Badge tone="accent">{sel.type}</Badge>
              <p className={cn("font-semibold", ["legacy", "nmc"].includes(sel.type) && "font-mono")}>{sel.label}</p>
              {sel.data.cpse && <p className="text-muted">CPSE {sel.data.cpse}</p>}
              {sel.data.description && <p>{sel.data.description}</p>}
              {sel.data.source === "synthetic" && <SyntheticBadge />}
              {sel.type === "legacy" && <Link to={`/search${qs({ q: sel.data.description })}`} className="text-xs text-accent hover:underline">Find equivalents</Link>}
            </div>
          )}
          <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-line pt-4 text-sm">
            <div><dt className="text-xs text-muted">Legacy codes</dt><dd className="font-semibold tabular-nums">{fmtNum(m.legacy_count)}</dd></div>
            <div><dt className="text-xs text-muted">Annual spend</dt><dd className="font-semibold tabular-nums">{fmtInr(m.spend)}</dd></div>
          </dl>
        </GlassCard>
      </div>
    </div>
  );
}

export default function Graph() {
  const { nmc } = useParams();
  return nmc ? <GraphView key={nmc} nmc={nmc} /> : <Start />;
}
