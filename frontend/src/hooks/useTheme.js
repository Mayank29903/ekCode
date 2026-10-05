import { useSyncExternalStore, useCallback } from "react";

const listeners = new Set();
const read = () => (document.documentElement.classList.contains("dark") ? "dark" : "light");
const subscribe = (cb) => { listeners.add(cb); return () => listeners.delete(cb); };

export function useTheme() {
  const theme = useSyncExternalStore(subscribe, read, () => "light");
  const toggle = useCallback(() => {
    const next = read() === "dark" ? "light" : "dark";
    const apply = () => {
      document.documentElement.classList.toggle("dark", next === "dark");
      try { localStorage.setItem("ek-theme", next); } catch { /* storage blocked */ }
      listeners.forEach((l) => l());
    };
    if (document.startViewTransition && !matchMedia("(prefers-reduced-motion: reduce)").matches) document.startViewTransition(apply);
    else apply();
  }, []);
  return { theme, toggle };
}
