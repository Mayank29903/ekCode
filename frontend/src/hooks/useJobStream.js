import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiUrl } from "../lib/api";

const FINISHED = ["done", "error", "uploaded"];     // "uploaded" = never started: nothing will change

/** Live ingest progress over Server-Sent Events, with automatic invalidation when done.
 *  If the stream cannot be opened (proxy, network), it falls back to polling the job every 1.5 s.
 *  Change `restartKey` to reconnect to the same job (after restarting it). */
export function useJobStream(jobId, restartKey = 0) {
  const [job, setJob] = useState(null);
  const qc = useQueryClient();
  useEffect(() => {
    setJob(null);                                          // never show the previous job under a new id
    if (!jobId) return;
    let closed = false;
    let timer = null;
    const finish = (data) => {
      if (closed) return true;
      setJob(data);
      if (FINISHED.includes(data.status)) {
        closed = true;
        if (data.status !== "uploaded") qc.invalidateQueries();
        return true;
      }
      return false;
    };
    const poll = async () => {
      if (closed) return;
      try {
        if (finish(await api(`/ingest/${jobId}`))) return;
      } catch (err) {
        if ([401, 403, 404].includes(err?.status)) return;   // gone or not allowed: stop
        /* otherwise keep trying: the API may be restarting */
      }
      timer = setTimeout(poll, 1500);
    };
    const es = new EventSource(apiUrl(`/ingest/${jobId}/events`), { withCredentials: true });
    es.onmessage = (ev) => {
      let data;
      try {
        data = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (finish(data)) es.close();
    };
    es.onerror = () => {
      es.close();
      if (!closed) poll();
    };
    return () => {
      closed = true;
      es.close();
      clearTimeout(timer);
    };
  }, [jobId, restartKey, qc]);
  return job;
}
