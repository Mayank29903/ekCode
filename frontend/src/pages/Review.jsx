import { useState } from "react";
import { Link } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCheck, Keyboard, PartyPopper, Stamp, UploadCloud, ShieldAlert } from "lucide-react";
import { api, qs } from "../lib/api";
import { fmtInr, fmtNum } from "../lib/format";
import { MATCH, PAIR_STATUS } from "../lib/constants";
import { useAuth } from "../providers/AuthProvider";
import { useHotkeys } from "../hooks/useHotkeys";
import { PageHeader } from "../components/ui/PageHeader";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Badge, SyntheticBadge } from "../components/ui/Badge";
import { Kbd } from "../components/ui/Kbd";
import { EmptyState } from "../components/ui/EmptyState";
import { SkeletonRows } from "../components/ui/Skeleton";
import { PairDiff } from "../components/review/PairDiff";
import { DecisionBar } from "../components/review/DecisionBar";
import { cn } from "../lib/cn";

const STATUSES = ["suggested", "blocked", "approved", "rejected"];
const card = {
  enter: { opacity: 0, y: 16, scale: 0.98 },
  center: { opacity: 1, y: 0, scale: 1, x: 0, rotate: 0 },
  // approve flies left, reject flies right, plain navigation fades
  exit: (dir) => ({ opacity: 0, x: dir * 360, rotate: dir * 5, transition: { duration: 0.32, ease: [0.16, 1, 0.3, 1] } }),
};

export default function Review() {
  const { can } = useAuth();
  const isSteward = can("admin", "data_steward");
  const qc = useQueryClient();
  const [status, setStatus] = useState("suggested");
  const [type, setType] = useState("");
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState(0);
  const [help, setHelp] = useState(false);

  const key = ["review", status, type];
  const queue = useQuery({ queryKey: key, queryFn: () => api(`/review/queue${qs({ status, type, limit: 50 })}`), placeholderData: keepPreviousData });
  const items = queue.data?.items ?? [];
  const i = Math.min(index, Math.max(items.length - 1, 0));
  const pair = items[i];
  // While a new tab loads, the previous tab's list is still on screen: never decide on it.
  const canDecide = isSteward && status === "suggested" && !queue.isPlaceholderData;

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["review"] });
    qc.invalidateQueries({ queryKey: ["kpis"] });
  };

  const decide = useMutation({
    mutationFn: ({ id, decision }) => api(`/review/${id}/decision`, { method: "POST", body: { decision } }),
    onMutate: async ({ id }) => {
      await qc.cancelQueries({ queryKey: key });
      const prev = qc.getQueryData(key);
      qc.setQueryData(key, (old) => old && { ...old, items: old.items.filter((p) => p.id !== id) });   // optimistic
      return { prev };
    },
    onError: (err, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(key, ctx.prev);
      toast.error(err.message);
    },
    onSuccess: (res, { decision }) => {
      if (decision === "approve") toast.success(<span>Approved · <span className="font-mono">{res.nmc}</span></span>);
      else toast("Marked as different");
    },
    onSettled: refresh,
  });

  const bulk = useMutation({
    mutationFn: (ids) => api("/review/bulk", { method: "POST", body: { ids, decision: "approve" } }),
    onSuccess: (r) => toast.success(`${r.done} approved${r.failed.length ? `, ${r.failed.length} skipped (conflicts)` : ""}`),
    onError: (err) => toast.error(err.message),
    onSettled: refresh,
  });

  const promote = useMutation({
    mutationFn: () => api("/review/promote-singletons", { method: "POST" }),
    onSuccess: (r) => toast.success(r.created ? `${fmtNum(r.created)} national codes issued for unique materials` : "Every processed material already has a code or an open suggestion"),
    onError: (err) => toast.error(err.message),
    onSettled: () => { refresh(); qc.invalidateQueries({ queryKey: ["materials"] }); },
  });

  const act = (decision) => {
    if (!pair || !canDecide || decide.isPending) return;
    setDir(decision === "approve" ? -1 : 1);
    decide.mutate({ id: pair.id, decision });
  };
  const next = () => { setDir(0); setIndex(Math.min(i + 1, Math.max(items.length - 1, 0))); };
  const prev = () => { setDir(0); setIndex(Math.max(i - 1, 0)); };
  const switchTo = (s, t = "") => { setStatus(s); setType(t); setIndex(0); setDir(0); };

  useHotkeys({ a: () => act("approve"), r: () => act("reject"), j: next, k: prev, arrowright: next, arrowleft: prev, "?": () => setHelp((h) => !h) });

  const exact = items.filter((p) => p.match_type === "EXACT_DUPLICATE");
  const counts = queue.data?.counts ?? {};
  const byType = queue.data?.by_type ?? {};

  return (
    <div>
      <PageHeader
        eyebrow="Step 2 of 3"
        title="Review matches"
        subtitle="Decide whether two legacy codes are the same material. Highest-spend, least-certain pairs come first."
        actions={
          <>
            <Button variant="ghost" size="sm" onClick={() => setHelp((h) => !h)}><Keyboard className="size-4" aria-hidden /> Shortcuts <Kbd>?</Kbd></Button>
            {isSteward && status === "suggested" && exact.length > 0 && (
              <Button variant="glass" size="sm" loading={bulk.isPending}
                onClick={() => window.confirm(`Approve all ${exact.length} "Same material" pairs on this page?`) && bulk.mutate(exact.map((p) => p.id))}>
                <CheckCheck className="size-4" aria-hidden /> Approve {exact.length} exact duplicates
              </Button>
            )}
            {isSteward && (
              <Button variant="glass" size="sm" loading={promote.isPending}
                onClick={() => window.confirm("Issue a national code for every processed material that has no match and no open suggestion?") && promote.mutate()}>
                <Stamp className="size-4" aria-hidden /> Issue codes for unique materials
              </Button>
            )}
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2" role="tablist" aria-label="Pair status">
        {STATUSES.map((s) => (
          <button key={s} role="tab" aria-selected={status === s} onClick={() => switchTo(s)}
            className={cn("rounded-xl px-3 py-1.5 text-sm font-medium transition", status === s ? "bg-surface shadow-sm ring-1 ring-line" : "text-muted hover:bg-fg/5")}>
            {PAIR_STATUS[s].label} <span className="ml-1 tabular-nums text-muted">{fmtNum(counts[s] ?? 0)}</span>
          </button>
        ))}
        {status === "suggested" && Object.keys(byType).length > 0 && (
          <div className="ml-auto flex flex-wrap gap-1.5">
            <button onClick={() => switchTo("suggested", "")} className={cn("rounded-full px-2.5 py-1 text-xs", !type ? "bg-accent text-white" : "bg-fg/5 text-muted")}>All</button>
            {Object.entries(byType).map(([t, n]) => (
              <button key={t} onClick={() => switchTo("suggested", t)} className={cn("rounded-full px-2.5 py-1 text-xs", type === t ? "bg-accent text-white" : "bg-fg/5 text-muted")}>
                {MATCH[t]?.label ?? t} · {n}
              </button>
            ))}
          </div>
        )}
      </div>

      <AnimatePresence>
        {help && (
          <motion.div initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="mb-4 overflow-hidden">
            <GlassCard className="flex flex-wrap gap-x-6 gap-y-2 p-4 text-sm" spotlight={false}>
              <span><Kbd>A</Kbd> same material (approve)</span>
              <span><Kbd>R</Kbd> different (reject)</span>
              <span><Kbd>J</Kbd> / <Kbd>→</Kbd> next</span>
              <span><Kbd>K</Kbd> / <Kbd>←</Kbd> previous</span>
              <span><Kbd>Ctrl</Kbd>+<Kbd>K</Kbd> jump anywhere</span>
            </GlassCard>
          </motion.div>
        )}
      </AnimatePresence>

      {queue.isLoading ? (
        <GlassCard className="p-6"><SkeletonRows rows={6} /></GlassCard>
      ) : queue.isError ? (
        <p role="alert" className="rounded-2xl bg-bad/10 p-4 text-sm text-bad">Could not load the queue: {queue.error.message}</p>
      ) : !pair ? (
        <GlassCard>
          {status === "suggested" ? (
            <EmptyState icon={PartyPopper} title="Nothing waiting for review"
              text="Every suggested pair has been decided. Upload another CPSE's file to find more, or issue codes for the materials that are unique."
              action={<Link to="/ingest"><Button variant="glass"><UploadCloud className="size-4" aria-hidden /> Upload data</Button></Link>} />
          ) : (
            <EmptyState icon={status === "blocked" ? ShieldAlert : CheckCheck} title={`No ${PAIR_STATUS[status].label.toLowerCase()} pairs`}
              text={status === "blocked" ? "Look-alike pairs with a critical difference (size, rating, grade…) will appear here. They are never merged." : undefined} />
          )}
        </GlassCard>
      ) : (
        <div className="grid gap-4 xl:grid-cols-[1fr_320px]">
          <div className="space-y-4">
            <div className="relative">
              <AnimatePresence mode="popLayout" custom={dir} initial={false}>
                <motion.div key={pair.id} custom={dir} variants={card} initial="enter" animate="center" exit="exit" transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}>
                  <GlassCard className="p-5 md:p-6" spotlight={false}>
                    <div className="mb-4 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <Badge tone={PAIR_STATUS[pair.status].tone}>{PAIR_STATUS[pair.status].label}</Badge>
                      <span>Pair #{pair.id}</span>
                      <span>· impact {fmtInr(pair.impact)}</span>
                    </div>
                    <PairDiff pair={pair} />
                  </GlassCard>
                </motion.div>
              </AnimatePresence>
            </div>
            {status === "suggested" && (
              <DecisionBar onApprove={() => act("approve")} onReject={() => act("reject")} onPrev={prev} onNext={next}
                canDecide={isSteward} busy={decide.isPending} position={i} total={items.length} />
            )}
            {status !== "suggested" && (
              <div className="flex items-center gap-2">
                <Button variant="ghost" size="sm" onClick={prev}>Previous</Button>
                <span className="text-xs tabular-nums text-muted">{i + 1} / {items.length}</span>
                <Button variant="ghost" size="sm" onClick={next}>Next</Button>
              </div>
            )}
          </div>

          <GlassCard className="max-h-[calc(100vh-10rem)] overflow-y-auto p-3" spotlight={false}>
            <h2 className="px-2 pb-2 text-sm font-semibold">In this list ({items.length}{counts[status] > items.length ? ` of ${fmtNum(counts[status])}` : ""})</h2>
            <ul className="space-y-1">
              {items.map((p, n) => (
                <li key={p.id}>
                  <button onClick={() => { setDir(0); setIndex(n); }}
                    className={cn("w-full rounded-xl p-2.5 text-left text-xs transition", n === i ? "bg-accent/10 ring-1 ring-accent/25" : "hover:bg-fg/5")}>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="font-semibold tabular-nums">{Math.round(p.score * 100)}</span>
                      <Badge tone={MATCH[p.match_type]?.tone ?? "muted"} className="px-2 py-0 text-[10px]">{MATCH[p.match_type]?.label ?? p.match_type}</Badge>
                      <SyntheticBadge show={p.a.source === "synthetic" || p.b.source === "synthetic"} />
                    </div>
                    <p className="truncate"><span className="text-muted">{p.a.cpse}</span> {p.a.description}</p>
                    <p className="truncate"><span className="text-muted">{p.b.cpse}</span> {p.b.description}</p>
                  </button>
                </li>
              ))}
            </ul>
          </GlassCard>
        </div>
      )}
    </div>
  );
}
