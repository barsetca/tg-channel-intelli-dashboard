import Link from "next/link";
import { Download } from "lucide-react";
import { exportDataShowcaseUrl, getDataShowcase } from "@/lib/api-client";
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

function shortJson(value: unknown): string {
  try {
    const s = JSON.stringify(value);
    if (!s) return "—";
    return s.length > 180 ? `${s.slice(0, 180)}…` : s;
  } catch {
    return "—";
  }
}

export default async function DataShowcasePage({
  searchParams,
}: {
  searchParams?: Promise<{ limit?: string }>;
}) {
  const sp = (await searchParams) ?? {};
  const parsed = Number(sp.limit);
  const limit = Number.isFinite(parsed) ? Math.max(1, Math.min(500, parsed)) : 100;
  const data = await getDataShowcase(limit);

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Витрина данных</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Таблица нормализованных записей из внешнего источника: каждая строка содержит record JSON, время сбора и
          источник.
        </p>
      </div>

      <Card>
        <CardTitle>Параметры</CardTitle>
        <CardDescription>Текущий limit: {data.limit}</CardDescription>
        <div className="mt-3 flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-600">Быстрый limit:</span>
          {[50, 100, 200, 500].map((n) => (
            <Link
              key={n}
              href={`/showcase?limit=${n}`}
              className={`rounded-lg border px-2 py-1 ${n === data.limit ? "border-violet-400 bg-violet-50 text-violet-800" : "border-zinc-300 text-zinc-700 hover:border-violet-300"}`}
            >
              {n}
            </Link>
          ))}
        </div>
        <div className="mt-4 flex flex-wrap gap-3">
          <a href={exportDataShowcaseUrl("json", data.limit)} download target="_blank" rel="noreferrer">
            <Button variant="secondary" className="w-full sm:w-auto">
              <Download className="size-4" />
              Экспорт JSON
            </Button>
          </a>
          <a href={exportDataShowcaseUrl("csv", data.limit)} download target="_blank" rel="noreferrer">
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
              <th className="px-4 py-3 text-left">Время сбора</th>
              <th className="px-4 py-3 text-left">Источник</th>
              <th className="px-4 py-3 text-left">Audit Run</th>
              <th className="px-4 py-3 text-left">Record JSON</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100">
            {data.items.map((item) => (
              <tr key={item.item_id} className="align-top">
                <td className="px-4 py-3 text-zinc-700">{formatDate(item.created_at)}</td>
                <td className="px-4 py-3 text-zinc-700">{item.source ?? "—"}</td>
                <td className="px-4 py-3 text-zinc-700">#{item.audit_run_id}</td>
                <td className="px-4 py-3">
                  <details>
                    <summary className="cursor-pointer text-violet-700 hover:text-violet-600">Открыть JSON</summary>
                    <pre className="mt-2 max-w-[44rem] overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-700">
                      {JSON.stringify(item.record_json ?? {}, null, 2)}
                    </pre>
                  </details>
                  <p className="mt-1 break-all text-xs text-zinc-500">{shortJson(item.record_json)}</p>
                </td>
              </tr>
            ))}
            {data.items.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-8 text-center text-zinc-500">
                  В витрине пока нет записей.
                </td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </div>
  );
}
