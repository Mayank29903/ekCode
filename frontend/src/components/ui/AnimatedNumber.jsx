import { useEffect, useRef } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";
import { fmtNum } from "../../lib/format";

export function AnimatedNumber({ value = 0, format = fmtNum, className }) {
  const ref = useRef(null);
  const from = useRef(0);
  const inView = useInView(ref, { once: true });
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el || !inView) return;
    if (reduce) { el.textContent = format(value); from.current = value; return; }
    const controls = animate(from.current, value, {
      duration: 1.2, ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => { el.textContent = format(v); },
    });
    from.current = value;
    return () => controls.stop();
  }, [value, inView, reduce]); // eslint-disable-line react-hooks/exhaustive-deps
  return <span ref={ref} className={`tabular-nums ${className ?? ""}`}>{format(0)}</span>;
}
