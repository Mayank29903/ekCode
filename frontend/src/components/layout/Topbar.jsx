import { useState } from "react";
import { createPortal } from "react-dom";
import { Menu, Moon, Search, Sun, LogOut, KeyRound, X } from "lucide-react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { toast } from "sonner";
import { api } from "../../lib/api";
import { useTheme } from "../../hooks/useTheme";
import { useAuth } from "../../providers/AuthProvider";
import { ROLE_LABEL } from "../../lib/constants";
import { Kbd } from "../ui/Kbd";
import { Button } from "../ui/Button";
import { Input, Label } from "../ui/Input";

function PasswordDialog({ open, onClose }) {
  const [form, setForm] = useState({ current: "", next: "", confirm: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const mismatch = form.confirm && form.next !== form.confirm;
  const valid = form.current && form.next.length >= 10 && form.next === form.confirm;
  const close = () => { setForm({ current: "", next: "", confirm: "" }); setError(""); onClose(); };

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await api("/auth/password", { method: "POST", body: { current_password: form.current, new_password: form.next } });
      toast.success("Password changed. Other signed-in sessions have been signed out.");
      close();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  // Portal to <body>: inside the sticky top bar's stacking context the sidebar would paint over the backdrop.
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div className="fixed inset-0 z-50 grid place-items-center bg-black/30 p-4 backdrop-blur-sm"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={close}
          onKeyDown={(e) => e.key === "Escape" && close()}>
          <motion.form onSubmit={submit} onClick={(e) => e.stopPropagation()} noValidate
            initial={{ opacity: 0, scale: 0.96, y: -8 }} animate={{ opacity: 1, scale: 1, y: 0 }} exit={{ opacity: 0, scale: 0.97 }}
            className="glass-strong w-full max-w-sm space-y-4 rounded-3xl p-6" role="dialog" aria-modal="true" aria-labelledby="pw-title">
            <div className="flex items-center justify-between">
              <h2 id="pw-title" className="text-lg font-semibold">Change password</h2>
              <button type="button" onClick={close} className="rounded-lg p-1.5 hover:bg-fg/5" aria-label="Close"><X className="size-4" /></button>
            </div>
            <div><Label htmlFor="pw-current">Current password</Label><Input id="pw-current" type="password" autoComplete="current-password" autoFocus value={form.current} onChange={set("current")} /></div>
            <div><Label htmlFor="pw-next" hint="at least 10 characters">New password</Label><Input id="pw-next" type="password" autoComplete="new-password" value={form.next} onChange={set("next")} /></div>
            <div>
              <Label htmlFor="pw-confirm">Repeat the new password</Label>
              <Input id="pw-confirm" type="password" autoComplete="new-password" value={form.confirm} onChange={set("confirm")} aria-invalid={!!mismatch} />
              {mismatch && <p className="mt-1 text-xs text-bad">The two new passwords are different.</p>}
            </div>
            {error && <p role="alert" className="rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={close}>Cancel</Button>
              <Button type="submit" loading={busy} disabled={!valid}>Change password</Button>
            </div>
          </motion.form>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
}

export function Topbar({ onOpenPalette, onOpenNav }) {
  const { theme, toggle } = useTheme();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [pwOpen, setPwOpen] = useState(false);
  const initials = user?.name?.split(" ").map((p) => p[0]).slice(0, 2).join("") ?? "U";

  const signOut = async () => {
    try {
      await logout();
      toast.success("Signed out");
    } catch (err) {
      toast.error(err.message);
    }
    navigate("/login");
  };

  return (
    <header className="sticky top-0 z-20 px-4 pt-3 md:px-8">
      <div className="glass flex h-14 items-center gap-3 rounded-2xl px-3">
        <button onClick={onOpenNav} className="rounded-lg p-2 hover:bg-fg/5 lg:hidden" aria-label="Open menu"><Menu className="size-5" /></button>
        <button onClick={onOpenPalette} className="flex h-9 flex-1 items-center gap-2 rounded-xl border border-line bg-surface/50 px-3 text-left text-sm text-muted transition hover:border-accent/40 md:max-w-md">
          <Search className="size-4" aria-hidden />
          <span className="flex-1 truncate">Search codes, pages, actions…</span>
          <span className="hidden gap-1 sm:flex"><Kbd>Ctrl</Kbd><Kbd>K</Kbd></span>
        </button>
        <div className="ml-auto flex items-center gap-2">

          <button onClick={toggle} className="grid size-9 place-items-center rounded-xl hover:bg-fg/5" aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} theme`}>
            {theme === "dark" ? <Sun className="size-[18px]" /> : <Moon className="size-[18px]" />}
          </button>
          <div className="flex items-center gap-2 rounded-xl py-1 pl-1 pr-2">
            <div className="grid size-8 place-items-center rounded-full bg-gradient-to-br from-accent to-indgreen text-xs font-semibold text-white">{initials}</div>
            <div className="hidden leading-tight md:block">
              <div className="text-sm font-medium">{user?.name}</div>
              <div className="text-[11px] text-muted">{ROLE_LABEL[user?.role]}{user?.cpse ? ` · ${user.cpse}` : ""}</div>
            </div>
          </div>
          <button onClick={() => setPwOpen(true)} className="grid size-9 place-items-center rounded-xl text-muted hover:bg-fg/5 hover:text-fg" aria-label="Change password">
            <KeyRound className="size-[18px]" />
          </button>
          <button onClick={signOut} className="grid size-9 place-items-center rounded-xl text-muted hover:bg-bad/10 hover:text-bad" aria-label="Sign out">
            <LogOut className="size-[18px]" />
          </button>
        </div>
      </div>
      <PasswordDialog open={pwOpen} onClose={() => setPwOpen(false)} />
    </header>
  );
}
