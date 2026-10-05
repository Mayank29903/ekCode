import { motion } from "motion/react";
import { Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";

const variants = {
  primary: "bg-accent text-white shadow-[0_8px_24px_-8px_var(--accent)] hover:brightness-110",
  glass: "glass text-fg hover:bg-white/70 dark:hover:bg-white/10",
  ghost: "text-fg hover:bg-fg/5",
  success: "bg-ok text-white shadow-[0_8px_24px_-10px_var(--color-ok)] hover:brightness-110",
  danger: "bg-bad text-white shadow-[0_8px_24px_-10px_var(--color-bad)] hover:brightness-110",
  outline: "border border-line bg-transparent text-fg hover:bg-fg/5",
};
const sizes = { sm: "h-8 px-3 text-xs gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-12 px-6 text-base gap-2", icon: "size-10" };

export function Button({ variant = "primary", size = "md", loading = false, className, children, disabled, type = "button", ...props }) {
  return (
    <motion.button
      type={type}
      whileHover={{ y: -1 }}
      whileTap={{ scale: 0.97 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center rounded-xl font-medium transition-[filter,background-color] disabled:pointer-events-none disabled:opacity-50",
        variants[variant], sizes[size], className
      )}
      {...props}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </motion.button>
  );
}
