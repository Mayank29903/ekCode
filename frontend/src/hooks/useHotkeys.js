import { useEffect, useRef } from "react";

/** map: { "a": fn, "mod+k": fn } — single keys are ignored while typing in inputs or while a modal dialog is open
 *  (so "A" in the password dialog can never approve the pair behind it). */
export function useHotkeys(map, enabled = true) {
  const ref = useRef(map);
  useEffect(() => { ref.current = map; });
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e) => {
      if (e.repeat && !e.metaKey && !e.ctrlKey) return;     // holding a key down must not decide many pairs
      const el = e.target;
      const typing = el instanceof HTMLElement && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
      const key = `${e.metaKey || e.ctrlKey ? "mod+" : ""}${(e.key ?? "").toLowerCase()}`;
      const fn = ref.current[key];
      const modal = !key.startsWith("mod+") && document.querySelector('[aria-modal="true"]');
      if (!fn || modal || (typing && !key.startsWith("mod+"))) return;
      e.preventDefault();
      fn(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}
