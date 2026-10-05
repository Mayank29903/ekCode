import { useRef } from "react";
import { motion } from "motion/react";
import { cn } from "../../lib/cn";

/** Frosted card with a cursor-following spotlight. */
export function GlassCard({ className, children, spotlight = true, strong = false, delay = 0, ...props }) {
  const ref = useRef(null);
  const onMove = (e) => {
    if (!spotlight || !ref.current) return;
    const r = ref.current.getBoundingClientRect();
    ref.current.style.setProperty("--mx", `${e.clientX - r.left}px`);
    ref.current.style.setProperty("--my", `${e.clientY - r.top}px`);
  };
  return (
    <motion.div
      ref={ref}
      onMouseMove={onMove}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1], delay }}
      className={cn(strong ? "glass-strong" : "glass", "group relative overflow-hidden rounded-3xl", className)}
      {...props}
    >
      {spotlight && (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-300 group-hover:opacity-100"
          style={{ background: "radial-gradient(380px circle at var(--mx, 50%) var(--my, 50%), color-mix(in oklab, var(--accent) 14%, transparent), transparent 65%)" }}
        />
      )}
      <div className="relative">{children}</div>
    </motion.div>
  );
}
