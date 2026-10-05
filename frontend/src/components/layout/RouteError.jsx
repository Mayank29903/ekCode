import { isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { AuroraBackground } from "./AuroraBackground";
import { cn } from "../../lib/cn";

/** Shown when a page crashes while rendering, or its code cannot be loaded (e.g. an old tab after a new release).
 *  Without it React Router shows a developer error page. `inline` keeps the app shell (sidebar, top bar) around it. */
export function RouteError({ inline = false }) {
  const error = useRouteError();
  const message = String(error?.message ?? "");
  const chunkFailed = /dynamically imported module|Importing a module script failed|Failed to fetch/i.test(message);
  const title = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : chunkFailed ? "EkCode was updated" : "Something went wrong on this page";
  const text = chunkFailed
    ? "A newer version is available. Reload to continue; your data is safe."
    : "Nothing was changed. Reload the page; if it happens again, note what you clicked and tell your administrator.";

  return (
    <div className={cn("relative grid place-items-center p-6", inline ? "min-h-[50vh]" : "min-h-full")}>
      {!inline && <AuroraBackground />}
      <div className="glass-strong max-w-md rounded-3xl p-8 text-center" role="alert">
        <div className="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-warn/12 text-warn ring-1 ring-warn/25">
          <AlertTriangle className="size-6" aria-hidden />
        </div>
        <h1 className="text-xl font-bold">{title}</h1>
        <p className="mt-2 text-sm text-muted">{text}</p>
        {import.meta.env.DEV && message && (
          <pre className="mt-4 max-h-40 overflow-auto rounded-xl bg-fg/5 p-3 text-left text-[11px]">{message}</pre>
        )}
        <div className="mt-6 flex justify-center gap-2">
          <button onClick={() => window.location.reload()}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-accent px-4 text-sm font-medium text-white hover:brightness-110">
            <RotateCcw className="size-4" aria-hidden /> Reload
          </button>
          <a href="/" className="inline-flex h-10 items-center rounded-xl px-4 text-sm font-medium hover:bg-fg/5">Dashboard</a>
        </div>
      </div>
    </div>
  );
}
