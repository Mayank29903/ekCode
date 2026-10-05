const inr = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 });
const num = new Intl.NumberFormat("en-IN");
export const fmtNum = (n) => num.format(Math.round(n ?? 0));
/** fraction (0.873) -> "87.3%" */
export const fmtPct = (n) => `${((n ?? 0) * 100).toFixed(1)}%`;
/** 0.873 -> 87 */
export const fmtScore = (n) => Math.round((n ?? 0) * 100);
export const fmtInr = (n) => {
  const v = n ?? 0;
  if (v >= 1e7) return `₹${(v / 1e7).toFixed(2)} Cr`;
  if (v >= 1e5) return `₹${(v / 1e5).toFixed(2)} L`;
  return inr.format(v);
};
export const timeAgo = (iso) => {
  if (!iso) return "";
  const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString("en-IN", { day: "numeric", month: "short" });
};
export const fmtDateTime = (iso) =>
  iso ? new Date(iso).toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "";
export const toCsv = (rows) => {
  if (!rows.length) return "";
  const keys = Object.keys(rows[0]);
  // A leading = + - @ would be run as a formula by Excel.
  const esc = (v) => {
    const s = String(v ?? "");
    return `"${(/^[=+\-@]/.test(s) ? `'${s}` : s).replaceAll('"', '""')}"`;
  };
  return [keys.join(","), ...rows.map((r) => keys.map((k) => esc(r[k])).join(","))].join("\n");
};
