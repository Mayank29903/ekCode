import { motion } from "motion/react";

export function ScoreRing({ score = 0, size = 96, stroke = 8, label = "match" }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const color = score >= 0.88 ? "var(--color-ok)" : score >= 0.7 ? "var(--color-warn)" : "var(--color-bad)";
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }} role="img" aria-label={`${Math.round(score * 100)} percent ${label}`}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none" className="stroke-fg/10" />
        <motion.circle
          cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} fill="none" stroke={color} strokeLinecap="round"
          strokeDasharray={c} initial={{ strokeDashoffset: c }} animate={{ strokeDashoffset: c * (1 - score) }}
          transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
          style={{ filter: `drop-shadow(0 0 6px ${color})` }}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className={`font-display font-semibold tabular-nums leading-none ${size < 72 ? "text-base" : "text-2xl"}`}>{Math.round(score * 100)}</div>
          {size >= 72 && <div className="mt-0.5 text-[10px] uppercase tracking-wider text-muted">{label}</div>}
        </div>
      </div>
    </div>
  );
}
