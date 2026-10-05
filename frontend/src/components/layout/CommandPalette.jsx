import { useState } from "react";
import { Command } from "cmdk";
import { AnimatePresence, motion } from "motion/react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { Boxes, CornerDownLeft, Search, Moon, Sun } from "lucide-react";
import { NAV } from "../../lib/constants";
import { api, qs } from "../../lib/api";
import { useDebounce } from "../../hooks/useDebounce";
import { useTheme } from "../../hooks/useTheme";
import { useAuth } from "../../providers/AuthProvider";
import { Kbd } from "../ui/Kbd";

const groupCls = "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-2 [&_[cmdk-group-heading]]:text-xs [&_[cmdk-group-heading]]:text-muted";
const itemCls = "flex cursor-pointer items-center gap-3 rounded-xl px-3 py-2.5 text-sm data-[selected=true]:bg-accent/10";

export function CommandPalette({ open, onClose }) {
  const [q, setQ] = useState("");
  const dq = useDebounce(q.trim(), 200);
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const { user } = useAuth();
  const results = useQuery({
    queryKey: ["palette", dq],
    queryFn: () => api(`/materials${qs({ q: dq, limit: 6, status: "all" })}`),
    enabled: open && dq.length >= 2,
  });
  const close = () => { onClose(); setQ(""); };
  const go = (to) => { close(); navigate(to); };
  const needle = q.trim().toLowerCase();
  const pages = NAV.filter((n) => (!n.roles || n.roles.includes(user?.role)) && (!needle || n.label.toLowerCase().includes(needle)));

  return (
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 flex items-start justify-center bg-black/25 p-4 pt-[12vh] backdrop-blur-sm" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={close}>
          <motion.div
            onClick={(e) => e.stopPropagation()}
            initial={{ opacity: 0, scale: 0.96, y: -8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97 }}
            transition={{ type: "spring", stiffness: 420, damping: 32 }}
            className="glass-strong w-full max-w-xl overflow-hidden rounded-3xl"
            role="dialog" aria-modal="true" aria-label="Command palette"
          >
            <Command shouldFilter={false} onKeyDown={(e) => e.key === "Escape" && close()}>
              <Command.Input autoFocus value={q} onValueChange={setQ} placeholder="Type a page, NMC code or description…" className="h-14 w-full border-b border-line bg-transparent px-5 text-base outline-none placeholder:text-muted" />
              <Command.List className="max-h-[60vh] overflow-y-auto p-2">
                <Command.Empty className="p-6 text-center text-sm text-muted">No results.</Command.Empty>

                {needle.length >= 2 && (
                  <Command.Group heading="Find equivalent" className={groupCls}>
                    <Command.Item value={`search:${q}`} onSelect={() => go(`/search${qs({ q: q.trim() })}`)} className={itemCls}>
                      <Search className="size-4 text-accent" aria-hidden />
                      <span className="truncate">Search the national master for “{q.trim()}”</span>
                    </Command.Item>
                  </Command.Group>
                )}

                {results.data?.items?.length > 0 && (
                  <Command.Group heading="National materials" className={groupCls}>
                    {results.data.items.map((m) => (
                      <Command.Item key={m.nmc} value={m.nmc} onSelect={() => go(`/materials/${m.nmc}`)} className={itemCls}>
                        <Boxes className="size-4 text-accent" aria-hidden />
                        <span className="font-mono text-xs">{m.nmc}</span>
                        <span className="truncate text-muted">{m.standard_description}</span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}

                {pages.length > 0 && (
                  <Command.Group heading="Pages" className={groupCls}>
                    {pages.map(({ to, label, icon: Icon }) => (
                      <Command.Item key={to} value={`page:${to}`} onSelect={() => go(to)} className={itemCls}>
                        <Icon className="size-4 text-muted" aria-hidden />
                        <span>{label}</span>
                      </Command.Item>
                    ))}
                  </Command.Group>
                )}

                {(!needle || "theme dark light".includes(needle)) && (
                  <Command.Group heading="Actions" className={groupCls}>
                    <Command.Item value="action:theme" onSelect={() => { toggle(); close(); }} className={itemCls}>
                      {theme === "dark" ? <Sun className="size-4 text-muted" aria-hidden /> : <Moon className="size-4 text-muted" aria-hidden />}
                      <span>Switch to {theme === "dark" ? "light" : "dark"} theme</span>
                    </Command.Item>
                  </Command.Group>
                )}
              </Command.List>
              <div className="flex items-center justify-between border-t border-line px-4 py-2 text-[11px] text-muted">
                <span className="flex items-center gap-1.5"><CornerDownLeft className="size-3" aria-hidden /> to open</span>
                <span className="flex items-center gap-1.5"><Kbd>Esc</Kbd> to close</span>
              </div>
            </Command>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
