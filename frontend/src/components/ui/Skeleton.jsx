import { motion } from "motion/react";
import { cn } from "../../lib/cn";

export function Skeleton({ className }) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-shimmer rounded-xl bg-[length:200%_100%] bg-[linear-gradient(90deg,rgb(15_23_42/.05)_0%,rgb(15_23_42/.10)_50%,rgb(15_23_42/.05)_100%)] dark:bg-[linear-gradient(90deg,rgb(255_255_255/.04)_0%,rgb(255_255_255/.09)_50%,rgb(255_255_255/.04)_100%)]",
        className
      )}
    />
  );
}

export function FullScreenLoader() {
  return (
    <div className="grid h-full min-h-[40vh] place-items-center">
      <motion.div
        className="size-12 rounded-2xl bg-[conic-gradient(from_0deg,var(--color-saffron),var(--accent),var(--color-indgreen),var(--color-saffron))]"
        animate={{ rotate: 360 }}
        transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
        role="status"
        aria-label="Loading"
      />
    </div>
  );
}

/** Placeholder rows while a real request is in flight (never a fake timer). */
export function SkeletonRows({ rows = 5, className }) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-10" />)}
    </div>
  );
}
