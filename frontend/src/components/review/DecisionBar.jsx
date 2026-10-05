import { Check, X, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "../ui/Button";
import { Kbd } from "../ui/Kbd";

/** Approve / reject / navigate, with the keyboard shortcuts shown (G5: decide in under 10 s). */
export function DecisionBar({ onApprove, onReject, onPrev, onNext, canDecide = true, busy = false, position, total }) {
  return (
    <div className="glass-strong sticky bottom-4 z-10 flex flex-wrap items-center gap-2 rounded-2xl p-2">
      <Button variant="ghost" size="sm" onClick={onPrev} aria-label="Previous pair (K)"><ChevronLeft className="size-4" aria-hidden /> <Kbd>K</Kbd></Button>
      <span className="text-xs tabular-nums text-muted">{total ? `${position + 1} / ${total}` : "0 / 0"}</span>
      <Button variant="ghost" size="sm" onClick={onNext} aria-label="Next pair (J)"><Kbd>J</Kbd> <ChevronRight className="size-4" aria-hidden /></Button>
      <div className="ml-auto flex gap-2">
        {canDecide ? (
          <>
            <Button variant="danger" onClick={onReject} disabled={busy || !total} aria-keyshortcuts="R">
              <X className="size-4" aria-hidden /> Different <Kbd>R</Kbd>
            </Button>
            <Button variant="success" onClick={onApprove} disabled={busy || !total} aria-keyshortcuts="A">
              <Check className="size-4" aria-hidden /> Same material <Kbd>A</Kbd>
            </Button>
          </>
        ) : (
          <span className="px-2 text-xs text-muted">Read-only: only data stewards can decide.</span>
        )}
      </div>
    </div>
  );
}
