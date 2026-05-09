import Link from "next/link";
import { Download, Filter } from "lucide-react";
import { exportManualReviewUrl, getManualReviewJournal } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";

export const dynamic = "force-dynamic";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

function short(value: unknown): string {
  try {
    const raw = JSON.stringify(value);
    if (!raw) return "—";
    return raw.length > 220 ? `${raw.slice(0, 220)}…` : raw;
  } catch {
    return "—";
  }
}

function sourceTone(source: "audit" | "search" | "analyze" | "semantic"): "neutral" | "warning" | "violet" {
  if (source === "search") return "violet";
  if (source === "analyze") return "warning";
  if (source === "semantic") return "violet";
  return "neutral";
}

export default async function ManualReviewPage({
  searchParams,
}: {
  searchParams?: Promise<{ source?: string; limit?: string }>;
}) {
  const sp = (await searchParams) ?? {};
  const source = (sp.source ?? "all") as "all" | "audit" | "search" | "analyze" | "semantic";
  const parsed = Number(sp.limit);
  const limit = Number.isFinite(parsed) ? Math.max(1, Math.min(500, parsed)) : 100;
  const data = await getManualReviewJournal(source, limit);

  const sourceOptions: Array<{ key: "all" | "audit" | "search" | "analyze" | "semantic"; label: string }> = [
    { key: "all", label: "Все" },
    { key: "audit", label: "Audit" },
    { key: "search", label: "Search" },
    { key: "analyze", label: "Analyze" },
    { key: "semantic", label: "Semantic" },
  ];

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Требует проверки</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Отдельный журнал случаев <code>needs_review</code> для сдачи и операционной диагностики.
        </p>
      </div>

      <Card>
        <CardTitle>Фильтры</CardTitle>
        <CardDescription>
          Текущий источник: <b>{data.source_filter}</b>, limit: <b>{data.limit}</b>
        </CardDescription>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <Filter className="size-4 text-zinc-500" />
          <span className="text-zinc-600">Источник:</span>
          {sourceOptions.map((opt) => (
            <Link
              key={opt.key}
              href={`/manual-review?source=${opt.key}&limit=${data.limit}`}
              className={`rounded-lg border px-2 py-1 ${
                opt.key === data.source_filter
                  ? "border-violet-400 bg-violet-50 text-violet-800"
                  : "border-zinc-300 text-zinc-700 hover:border-violet-300"
              }`}
            >
              {opt.label}
            </Link>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-600">Быстрый limit:</span>
          {[50, 100, 200, 500].map((n) => (
            <Link
              key={n}
              href={`/manual-review?source=${data.source_filter}&limit=${n}`}
              className={`rounded-lg border px-2 py-1 ${
                n === data.limit
                  ? "border-violet-400 bg-violet-50 text-violet-800"
                  : "border-zinc-300 text-zinc-700 hover:border-violet-300"
              }`}
            >
              {n}
            </Link>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <a href={exportManualReviewUrl("json", data.source_filter, data.limit)} download target="_blank" rel="noreferrer">
            <Button variant="secondary" className="w-full sm:w-auto">
              <Download className="size-4" />
              Экспорт JSON
            </Button>
          </a>
          <a href={exportManualReviewUrl("csv", data.source_filter, data.limit)} download target="_blank" rel="noreferrer">
            <Button variant="secondary" className="w-full sm:w-auto">
              <Download className="size-4" />
              Экспорт CSV
            </Button>
          </a>
        </div>
      </Card>

      <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
        <table className="min-w-full divide-y divide-zinc-200 text-sm">
          <thead className="bg-zinc-50 text-xs uppercase tracking-wide text-zinc-600">
            <tr>
              <th className="px-4 py-3 text-left">Время</th>
              <th className="px-4 py-3 text-left">Источник</th>
              <th className="px-4 py-3 text-left">Ссылка</th>
              <th className="px-4 py-3 text-left">Причина</th>
              <th className="px-4 py-3 text-left">Детали</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {data.items.map((item) => (
              <tr key={`${item.source}-${item.reference_id}`} className="align-top">
                <td className="px-4 py-3 text-zinc-700">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3">
                  <Badge tone={sourceTone(item.source)}>{item.source}</Badge>
                </td>
                <td className="px-4 py-3 text-zinc-700">
                  #{item.reference_id}
                  {item.status ? <p className="text-xs text-zinc-500">status: {item.status}</p> : null}
                </td>
                <td className="max-w-md px-4 py-3 text-zinc-800">{item.reason}</td>
                <td className="px-4 py-3">
                  <details>
                    <summary className="cursor-pointer text-violet-700 hover:text-violet-600">Открыть JSON</summary>
                    <pre className="mt-2 max-w-[42rem] overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700">
                      {JSON.stringify(item.details ?? {}, null, 2)}
                    </pre>
                  </details>
                  <p className="mt-1 break-all text-xs text-zinc-500">{short(item.details)}</p>
                </td>
              </tr>
            ))}
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-zinc-500">
                  Для выбранного фильтра записей пока нет.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
