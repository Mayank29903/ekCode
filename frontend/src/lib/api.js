const BASE = import.meta.env.VITE_API_URL ?? "";

/** Absolute API URL, for the few callers that cannot go through api() (EventSource). */
export const apiUrl = (path) => `${BASE}/api/v1${path}`;

function messageFor(status, data) {
  if (typeof data?.detail === "string") return data.detail;
  if (Array.isArray(data?.detail)) return data.detail.map((d) => d.msg).join(", ");
  if (status === 0) return "Cannot reach the EkCode server. Check your connection and try again.";
  if (status === 502 || status === 503 || status === 504) return "The EkCode server is starting or busy. Try again in a moment.";
  if (status === 413) return "The file is too large.";
  return `Request failed (${status})`;
}

export class ApiError extends Error {
  constructor(status, data) {
    super(messageFor(status, data));
    this.status = status;
    this.data = data;
  }
}

/** @param {string} path @param {{method?:string, body?:any, form?:FormData, signal?:AbortSignal, raw?:boolean}} [opts] */
export async function api(path, { method = "GET", body, form, signal, raw } = {}) {
  let res;
  try {
    res = await fetch(apiUrl(path), {
      method,
      signal,
      credentials: "include",
      headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
      body: form ?? (body !== undefined ? JSON.stringify(body) : undefined),
    });
  } catch (err) {
    if (err?.name === "AbortError") throw err;
    throw new ApiError(0, null);                        // network down, DNS, CORS, server not running
  }
  if (res.status === 401 && !path.startsWith("/auth/login")) window.dispatchEvent(new Event("ek:unauthorized"));
  if (raw && res.ok) return res;
  const type = res.headers.get("content-type") || "";
  let data = null;
  if (res.status !== 204) {
    try {
      data = type.includes("application/json") ? await res.json() : await res.text();
    } catch {
      data = null;                                        // empty or broken body
    }
  }
  if (!res.ok) throw new ApiError(res.status, typeof data === "object" ? data : null);
  return data;
}

export const qs = (params) => {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && p.set(k, String(v)));
  const s = p.toString();
  return s ? `?${s}` : "";
};

export async function download(path, filename) {
  const res = await api(path, { raw: true });
  const blob = await res.blob();
  saveBlob(blob, filename);
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename, rel: "noopener" });
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);   // revoking at once can cancel the download in Firefox
}
