import { Sparkles } from "lucide-react";
import { SAP_FIELDS } from "../../lib/constants";
import { Select } from "../ui/Select";
import { Badge } from "../ui/Badge";

/** Map the file's columns to SAP material fields. `suggested` is the backend's fuzzy auto-mapping. */
export function ColumnMapper({ columns = [], mapping, suggested = {}, onChange, preview = [] }) {
  const options = columns.map((c) => ({ value: c, label: c }));
  const mapped = SAP_FIELDS.filter((f) => mapping[f.key]);

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {SAP_FIELDS.map((f) => {
          const id = `map-${f.key}`;
          const auto = suggested[f.key] && suggested[f.key] === mapping[f.key];
          return (
            <div key={f.key}>
              <label htmlFor={id} className="mb-1.5 flex items-center justify-between gap-2 text-xs font-medium text-muted">
                <span>
                  {f.label} <span className="font-mono text-[10px] opacity-70">{f.key}</span>
                  {f.required && <span className="text-bad"> *</span>}
                </span>
                {auto && <Badge tone="accent" className="px-2 py-0 text-[10px]"><Sparkles className="size-3" aria-hidden /> auto</Badge>}
              </label>
              <Select
                id={id}
                value={mapping[f.key] ?? ""}
                onChange={(e) => onChange({ ...mapping, [f.key]: e.target.value || undefined })}
                options={options}
                placeholder={f.required ? "Choose a column…" : "Not in this file"}
                aria-invalid={f.required && !mapping[f.key]}
              />
            </div>
          );
        })}
      </div>

      {preview.length > 0 && mapped.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Preview with this mapping</h3>
          <div className="overflow-x-auto rounded-2xl border border-line bg-surface">
            <table className="w-full text-left text-sm">
              <thead className="bg-fg/[0.03] text-xs uppercase tracking-wider text-muted">
                <tr>{mapped.map((f) => <th key={f.key} scope="col" className="whitespace-nowrap px-3 py-2 font-medium">{f.label}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-line">
                {preview.slice(0, 6).map((row, i) => (
                  <tr key={i}>
                    {mapped.map((f) => (
                      <td key={f.key} className={`max-w-[28ch] truncate px-3 py-2 ${f.key === "MATNR" ? "font-mono text-xs" : ""}`} title={String(row[mapping[f.key]] ?? "")}>
                        {String(row[mapping[f.key]] ?? "")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
