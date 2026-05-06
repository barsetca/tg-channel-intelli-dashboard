import { AlertTriangle } from "lucide-react";
import type { ManualReviewFlags } from "@/lib/types/api";
import { Alert } from "@/components/ui/alert";

export function ManualReviewBanner({ flags }: { flags: ManualReviewFlags }) {
  return (
    <Alert variant="warning" title="Требуется ручная проверка">
      <div className="flex gap-3">
        <AlertTriangle className="mt-0.5 size-5 shrink-0 text-amber-600" />
        <div>
          <p>{flags.reason}</p>
          {flags.hints?.length ? (
            <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-amber-900/90">
              {flags.hints.map((h) => (
                <li key={h}>{h}</li>
              ))}
            </ul>
          ) : null}
        </div>
      </div>
    </Alert>
  );
}
