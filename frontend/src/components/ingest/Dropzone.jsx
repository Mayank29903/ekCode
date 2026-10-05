import { useDropzone } from "react-dropzone";
import { motion } from "motion/react";
import { FileSpreadsheet, UploadCloud, Loader2 } from "lucide-react";
import { cn } from "../../lib/cn";

const MAX_MB = 100;
const ACCEPT = {
  "text/csv": [".csv"],
  "text/plain": [".txt", ".tsv"],
  "text/tab-separated-values": [".tsv"],
  "application/vnd.ms-excel": [".xls", ".csv"],
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
};

/** Drop a SAP/ERP material export (CSV, TSV, XLSX, XLS). */
export function Dropzone({ onFile, disabled = false, busy = false }) {
  const { getRootProps, getInputProps, isDragActive, fileRejections } = useDropzone({
    onDrop: (files) => files[0] && onFile(files[0]),
    accept: ACCEPT,
    multiple: false,
    maxFiles: 1,
    maxSize: MAX_MB * 1024 * 1024,
    disabled: disabled || busy,
  });
  const rejection = fileRejections[0]?.errors[0];

  return (
    <div>
      <div
        {...getRootProps()}
        className={cn(
          "relative flex cursor-pointer flex-col items-center justify-center gap-3 overflow-hidden rounded-3xl border-2 border-dashed px-6 py-14 text-center transition",
          isDragActive ? "border-accent bg-accent/8" : "border-line bg-surface/40 hover:border-accent/50 hover:bg-accent/5",
          (disabled || busy) && "cursor-not-allowed opacity-60"
        )}
      >
        <input {...getInputProps()} aria-label="Material export file" />
        <motion.div
          animate={isDragActive ? { scale: 1.1, rotate: -4 } : { scale: 1, rotate: 0 }}
          className="grid size-16 place-items-center rounded-2xl bg-accent/10 text-accent ring-1 ring-accent/20"
        >
          {busy ? <Loader2 className="size-7 animate-spin" aria-hidden /> : isDragActive ? <FileSpreadsheet className="size-7" aria-hidden /> : <UploadCloud className="size-7" aria-hidden />}
        </motion.div>
        <div>
          <p className="font-semibold">{busy ? "Uploading and reading columns…" : isDragActive ? "Drop the file here" : "Drop your material master export here"}</p>
          <p className="mt-1 text-sm text-muted">or click to choose · CSV, TSV, XLSX or XLS · up to {MAX_MB} MB</p>
        </div>
      </div>
      {rejection && (
        <p role="alert" className="mt-2 text-sm text-bad">
          {rejection.code === "file-too-large" ? `The file is larger than ${MAX_MB} MB.` : rejection.code === "file-invalid-type" ? "Choose a CSV, TSV or Excel file." : rejection.message}
        </p>
      )}
    </div>
  );
}
