"use client";

import { useMemo, useState } from "react";
import { analyzeChannel, ApiError } from "@/lib/api-client";
import type { AnalyzeChannelResponse, ChannelDetail } from "@/lib/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";
import { ActivityBars } from "@/components/charts/activity-bars";
import { TrendArea } from "@/components/charts/trend-area";
import { AnalysisReportView } from "@/components/channel-analysis-report-view";

export function ChannelAnalyzePanel({ channel }: { channel: ChannelDetail }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeChannelResponse | null>(null);

  const stubBars = useMemo(
    () => [
      { name: "Частота", value: Math.min(100, (channel.posts_per_week_estimate ?? 2) * 8) },
      { name: "Охват", value: Math.min(100, Math.log10((channel.subscriber_count ?? 100) + 10) * 18) },
      { name: "Актуальность", value: channel.last_post_at ? 72 : 20 },
    ],
    [channel],
  );

  const stubTrend = useMemo(() => {
    const base = channel.posts_per_week_estimate ?? 3;
    return ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((t, i) => ({
      t,
      v: Math.max(1, Math.round(base * (6 + Math.sin(i)))),
    }));
  }, [channel.posts_per_week_estimate]);

  async function onAnalyze(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const res = await analyzeChannel(channel.id);
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Ошибка запроса");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardTitle>Запуск AI-анализа</CardTitle>
        <CardDescription>
          Сценарий 2: автоматически запускает анализ канала и сохраняет отчёт. Если в локальной базе нет постов, система
          попробует подтянуть последние 10 постов из Telegram.
        </CardDescription>
        <form onSubmit={onAnalyze} className="mt-4 space-y-4">
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner /> : null}
            Анализировать канал
          </Button>
        </form>
        {error ? (
          <div className="mt-4">
            <Alert variant="error" title="Ошибка анализа">
              {error}
            </Alert>
          </div>
        ) : null}
        {result ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
            <p>
              <span className="text-zinc-500">Анализ #</span> {result.analysis_id}{" "}
              <span className="text-zinc-500">· Статус:</span> {result.status}
            </p>
            <p className="mt-2 text-zinc-700">{result.message}</p>
            {result.report ? <AnalysisReportView report={result.report} /> : null}
          </div>
        ) : null}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Индикаторы канала</CardTitle>
          <CardDescription>Нормализованная оценка по открытым метаданным канала.</CardDescription>
          <div className="mt-4">
            <ActivityBars data={stubBars} />
          </div>
        </Card>
        <Card>
          <CardTitle>Ритм публикаций</CardTitle>
          <CardDescription>Оценочная недельная кривая на основе текущей частоты постинга.</CardDescription>
          <div className="mt-4">
            <TrendArea data={stubTrend} />
          </div>
        </Card>
      </div>
    </div>
  );
}
