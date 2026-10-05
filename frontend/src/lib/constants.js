import { LayoutDashboard, UploadCloud, GitCompareArrows, Boxes, Search, Share2, BarChart3, ScrollText, Plug, Settings } from "lucide-react";

export const ROLE_LABEL = { admin: "Admin", data_steward: "Data steward", cpse_user: "CPSE user", auditor: "Auditor" };
export const STEWARDS = ["admin", "data_steward"];
export const UPLOADERS = ["admin", "data_steward", "cpse_user"];
export const AUDIT_READERS = ["admin", "data_steward", "auditor"];

export const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/ingest", label: "Upload data", icon: UploadCloud, roles: UPLOADERS },
  { to: "/review", label: "Review matches", icon: GitCompareArrows, badge: "pending" },
  { to: "/materials", label: "National master", icon: Boxes },
  { to: "/search", label: "Find equivalent", icon: Search },
  { to: "/graph", label: "Knowledge graph", icon: Share2 },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/audit", label: "Audit trail", icon: ScrollText, roles: AUDIT_READERS },
  { to: "/integrations", label: "Integrations", icon: Plug },
  { to: "/settings", label: "Settings", icon: Settings, roles: AUDIT_READERS },
];

export const MATCH = {
  EXACT_DUPLICATE: { label: "Same material", tone: "ok" },
  NEAR_DUPLICATE: { label: "Probably same", tone: "accent" },
  FUNCTIONAL_EQUIVALENT: { label: "Works the same", tone: "warn" },
  DIFFERENT: { label: "Different", tone: "bad" },
};

export const PAIR_STATUS = {
  suggested: { label: "To review", tone: "accent" },
  blocked: { label: "Blocked by rule", tone: "bad" },
  approved: { label: "Approved", tone: "ok" },
  rejected: { label: "Rejected", tone: "muted" },
};

export const STAGES = [
  { key: "queued", label: "Queued" },
  { key: "parsing", label: "Reading file" },
  { key: "normalizing", label: "Reading descriptions" },
  { key: "embedding", label: "Understanding text" },
  { key: "matching", label: "Finding matches" },
  { key: "done", label: "Done" },
];

export const SAP_FIELDS = [
  { key: "MATNR", label: "Material code", required: true },
  { key: "MAKTX", label: "Description", required: true },
  { key: "LONG_TEXT", label: "Long text / specification" },
  { key: "MEINS", label: "Unit of measure" },
  { key: "MATKL", label: "Material group" },
  { key: "PRICE", label: "Unit price (₹)" },
  { key: "QTY", label: "Annual quantity" },
];

/** Attribute keys produced by the extractor (backend ekml/extract.py), in display order. */
export const ATTRIBUTES = {
  noun: "Material type",
  thread: "Thread (M)",
  length_mm: "Length (mm)",
  size_in: "Size (in)",
  size_mm: "Size (mm)",
  rating: "Pressure rating (#)",
  schedule: "Schedule",
  grade: "Grade / material",
  standard: "Standard",
  bearing_no: "Bearing no.",
  cores: "Cores",
  area_sqmm: "Area (sq mm)",
  voltage: "Voltage",
  conductor: "Conductor",
  coating: "Coating",
};

export const CHART_COLORS = ["#2451e6", "#ff9933", "#138808", "#7c3aed", "#0891b2", "#db2777", "#65a30d", "#ea580c"];
