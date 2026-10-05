import { NavLink } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { X } from "lucide-react";
import { NAV } from "../../lib/constants";
import { api } from "../../lib/api";
import { useAuth } from "../../providers/AuthProvider";
import { cn } from "../../lib/cn";

function Brand() {
  return (
    <div className="flex items-center gap-3 px-3 py-2">
      <div className="relative grid size-10 place-items-center overflow-hidden rounded-2xl bg-white font-display text-lg font-bold text-black shadow-lg shadow-black/20">
        <span className="relative z-10">E</span>
        <div className="absolute inset-x-0 top-0 h-1/3 bg-[#FF9933]" />
        <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[#138808]" />
      </div>
      <div>
        <div className="font-display text-lg font-bold leading-none">EkCode</div>
        <div className="text-[11px] text-muted">One Nation · One Material Code</div>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }) {
  const { user } = useAuth();
  const kpis = useQuery({ queryKey: ["kpis"], queryFn: () => api("/analytics/kpis"), refetchInterval: 30_000 });
  const pending = kpis.data?.pending_review ?? 0;
  const items = NAV.filter((n) => !n.roles || n.roles.includes(user?.role));
  return (
    <nav className="mt-6 flex flex-col gap-1" aria-label="Main">
      {items.map(({ to, label, icon: Icon, end, badge }) => (
        <NavLink key={to} to={to} end={end} onClick={onNavigate} className="relative block rounded-xl">
          {({ isActive }) => (
            <div className={cn("relative flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-colors", isActive ? "text-fg" : "text-muted hover:bg-fg/5 hover:text-fg")}>
              {isActive && (
                <motion.div layoutId="nav-pill" className="absolute inset-0 rounded-xl bg-surface/90 shadow-sm ring-1 ring-line dark:bg-white/8" transition={{ type: "spring", stiffness: 500, damping: 38 }} />
              )}
              <Icon className={cn("relative size-[18px]", isActive && "text-accent")} aria-hidden />
              <span className="relative font-medium">{label}</span>
              {badge === "pending" && pending > 0 && (
                <span className="relative ml-auto rounded-full bg-accent px-2 py-0.5 text-[11px] font-semibold tabular-nums text-white" aria-label={`${pending} waiting`}>
                  {pending > 999 ? "999+" : pending}
                </span>
              )}
            </div>
          )}
        </NavLink>
      ))}
    </nav>
  );
}

export function Sidebar({ mobileOpen, onClose }) {
  return (
    <>
      <aside className="glass fixed inset-y-3 left-3 z-30 hidden w-66 flex-col rounded-3xl p-3 lg:flex">
        <Brand />
        <NavItems />
        <div className="mt-auto rounded-2xl bg-gradient-to-br from-saffron/15 via-accent/10 to-indgreen/15 p-4 text-xs text-muted ring-1 ring-line">
          Press <span className="font-semibold text-fg">Ctrl + K</span> anywhere to jump to a page or code.
        </div>
      </aside>
      <AnimatePresence>
        {mobileOpen && (
          <>
            <motion.div className="fixed inset-0 z-40 bg-black/30 backdrop-blur-sm lg:hidden" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
            <motion.aside
              className="glass-strong fixed inset-y-0 left-0 z-50 w-72 overflow-y-auto p-3 lg:hidden"
              initial={{ x: "-100%" }} animate={{ x: 0 }} exit={{ x: "-100%" }} transition={{ type: "spring", stiffness: 380, damping: 36 }}
            >
              <div className="flex items-center justify-between"><Brand /><button onClick={onClose} className="rounded-lg p-2 hover:bg-fg/5" aria-label="Close menu"><X className="size-5" /></button></div>
              <NavItems onNavigate={onClose} />
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
