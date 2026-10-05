import { motion } from "motion/react";

export function EmptyState({ icon: Icon, title, text, action }) {
  return (
    <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} className="flex flex-col items-center gap-3 px-6 py-16 text-center">
      {Icon && (
        <div className="grid size-14 place-items-center rounded-2xl bg-accent/10 text-accent ring-1 ring-accent/20">
          <Icon className="size-6" aria-hidden />
        </div>
      )}
      <h3 className="text-lg font-semibold">{title}</h3>
      {text && <p className="max-w-sm text-sm text-muted">{text}</p>}
      {action}
    </motion.div>
  );
}
