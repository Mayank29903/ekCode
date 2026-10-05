import { cn } from "../../lib/cn";

export function Input({ className, icon: Icon, ...props }) {
  return (
    <div className="relative">
      {Icon && <Icon className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted" aria-hidden />}
      <input
        className={cn(
          "h-10 w-full rounded-xl border border-line bg-surface/70 px-3 text-sm text-fg placeholder:text-muted/70 transition focus:border-accent/50 focus:bg-surface focus:outline-none focus:ring-4 focus:ring-accent/15",
          Icon && "pl-9", className
        )}
        {...props}
      />
    </div>
  );
}

export function Textarea({ className, ...props }) {
  return (
    <textarea
      className={cn("w-full rounded-xl border border-line bg-surface/70 p-3 text-sm text-fg transition focus:border-accent/50 focus:outline-none focus:ring-4 focus:ring-accent/15", className)}
      {...props}
    />
  );
}

export function Label({ children, htmlFor, hint }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline justify-between text-xs font-medium text-muted">
      <span>{children}</span>
      {hint && <span className="font-normal opacity-80">{hint}</span>}
    </label>
  );
}
