import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";
import { motion } from "motion/react";
import { toast } from "sonner";
import { LogIn, Mail, Lock, ShieldCheck, GitCompareArrows, Boxes, User, UserPlus } from "lucide-react";
import { useAuth } from "../providers/AuthProvider";
import { AuroraBackground } from "../components/layout/AuroraBackground";
import { GlassCard } from "../components/ui/GlassCard";
import { Button } from "../components/ui/Button";
import { Input, Label } from "../components/ui/Input";
import { FullScreenLoader } from "../components/ui/Skeleton";

const POINTS = [
  { icon: GitCompareArrows, title: "Finds the same material across CPSEs", text: "Meaning, wording and attributes are compared; critical differences such as M12 vs M16 are always blocked." },
  { icon: ShieldCheck, title: "People decide, everything is audited", text: "Every suggestion is approved by a data steward and every change is recorded." },
  { icon: Boxes, title: "One National Material Code", text: "Each approved material gets a checked NMC that maps back to every legacy code." },
];

export default function Login() {
  const { user, loading, login, register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [isRegister, setIsRegister] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const target = location.state?.from && location.state.from !== "/login" ? location.state.from : "/";

  if (loading) return <FullScreenLoader />;
  if (user) return <Navigate to={target} replace />;

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      if (isRegister) {
        const u = await register(name.trim(), email.trim(), password);
        toast.success(`Account created, welcome ${u.name}!`);
      } else {
        const u = await login(email.trim(), password);
        toast.success(`Welcome, ${u.name}`);
      }
      navigate(target, { replace: true });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="relative grid min-h-full place-items-center px-4 py-10">
      <AuroraBackground />
      <div className="grid w-full max-w-5xl items-center gap-10 lg:grid-cols-[1.1fr_1fr]">
        <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }} className="hidden lg:block">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-accent">Ministry of Petroleum &amp; Natural Gas · SIH 2026</p>
          <h1 className="mt-3 text-5xl font-extrabold leading-tight">
            One Nation.<br /><span className="text-gradient">One Material Code.</span>
          </h1>
          <p className="mt-4 max-w-md text-muted">
            EkCode brings the material masters of India&apos;s CPSEs together, finds duplicates and equivalents, and issues a
            single national code with full traceability.
          </p>
          <ul className="mt-8 space-y-4">
            {POINTS.map(({ icon: Icon, title, text }, i) => (
              <motion.li key={title} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.15 + i * 0.08 }} className="flex gap-3">
                <div className="grid size-10 shrink-0 place-items-center rounded-2xl bg-accent/10 text-accent ring-1 ring-accent/20"><Icon className="size-5" aria-hidden /></div>
                <div>
                  <p className="font-semibold">{title}</p>
                  <p className="text-sm text-muted">{text}</p>
                </div>
              </motion.li>
            ))}
          </ul>
        </motion.div>

        <GlassCard strong spotlight={false} className="mx-auto w-full max-w-md p-8">
          <div className="mb-6 flex items-center gap-3">
            <div className="relative grid size-11 place-items-center overflow-hidden rounded-2xl bg-white font-display text-lg font-bold text-black">
              <span className="relative z-10">E</span>
              <div className="absolute inset-x-0 top-0 h-1/3 bg-[#FF9933]" />
              <div className="absolute inset-x-0 bottom-0 h-1/3 bg-[#138808]" />
            </div>
            <div>
              <h2 className="text-xl font-bold">{isRegister ? "Create an Account" : "Sign in to EkCode"}</h2>
              <p className="text-xs text-muted">National Material Master for CPSEs</p>
            </div>
          </div>
          <form onSubmit={submit} className="space-y-4">
            {isRegister && (
              <div>
                <Label htmlFor="name">Full Name</Label>
                <Input id="name" icon={User} required minLength={1} maxLength={120} value={name} onChange={(e) => setName(e.target.value)} placeholder="Your Name" />
              </div>
            )}
            <div>
              <Label htmlFor="email">Email</Label>
              <Input id="email" icon={Mail} type="email" autoComplete="username" required pattern="^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$" title="Please enter a valid email address" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@cpse.gov.in" />
            </div>
            <div>
              <Label htmlFor="password">Password</Label>
              <Input id="password" icon={Lock} type="password" autoComplete={isRegister ? "new-password" : "current-password"} required pattern="^(?=.*[A-Za-z])(?=.*\d)(?=.*[@$!%*#?&])[A-Za-z\d@$!%*#?&]{8,}$" title="Minimum 8 characters, at least one letter, one number and one special character" value={password} onChange={(e) => setPassword(e.target.value)} />
            </div>
            {error && <p role="alert" className="rounded-xl bg-bad/10 px-3 py-2 text-sm text-bad">{error}</p>}
            <Button type="submit" size="lg" className="w-full" loading={busy} disabled={!email || !password || (isRegister && !name)}>
              {!busy && (isRegister ? <UserPlus className="size-4" aria-hidden /> : <LogIn className="size-4" aria-hidden />)} 
              {isRegister ? " Register" : " Sign in"}
            </Button>
          </form>
          <div className="mt-6 text-center text-sm">
            {isRegister ? (
              <p className="text-muted">Already have an account? <button type="button" onClick={() => setIsRegister(false)} className="text-accent hover:underline font-semibold">Sign in</button></p>
            ) : (
              <p className="text-muted">Don't have an account? <button type="button" onClick={() => setIsRegister(true)} className="text-accent hover:underline font-semibold">Register</button></p>
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}
