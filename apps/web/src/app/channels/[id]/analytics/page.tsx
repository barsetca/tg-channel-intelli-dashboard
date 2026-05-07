import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import {
  ApiError,
  getChannel,
  getRecommendations,
  getSavedChannelAnalysis,
  listChannelAnalyses,
} from "@/lib/api-client";
import { ChannelAnalyzePanel } from "@/components/channel-analyze-panel";
import { AnalysisReportView } from "@/components/channel-analysis-report-view";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Alert } from "@/components/ui/alert";
import { ActivityBars } from "@/components/charts/activity-bars";
import { TrendArea } from "@/components/charts/trend-area";
import { Badge } from "@/components/ui/badge";

function fmtDate(value: string | null) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return value;
  }
}

export default async function ChannelAnalyticsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) notFound();

  let channel;
  try {
    channel = await getChannel(numericId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  const engagementBars = [
    { name: "Плотность контента", value: Math.min(100, (channel.posts_per_week_estimate ?? 1) * 9) },
    { name: "Потенциал охвата", value: Math.min(100, Math.log10((channel.subscriber_count ?? 100) + 10) * 18) },
    { name: "Актуальность", value: channel.last_post_at ? 78 : 20 },
  ];
  const trendSeries = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((label, i) => {
    const base = channel.posts_per_week_estimate ?? 3;
    return { t: label, v: Math.max(1, Math.round(base * (5.5 + Math.sin(i)))) };
  });

  let recommendations = null;
  try {
    recommendations = await getRecommendations(channel.id, 5);
  } catch {
    recommendations = null;
  }

  let latestAnalysis = null;
  try {
    const history = await listChannelAnalyses(channel.id);
    const latest = [...history].sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
    )[0];
    if (latest) {
      latestAnalysis = await getSavedChannelAnalysis(latest.id);
    }
  } catch {
    latestAnalysis = null;
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <Link
        href={`/channels/${channel.id}`}
        className="inline-flex items-center gap-1 text-sm text-zinc-600 hover:text-zinc-900"
      >
        <ChevronLeft className="size-4" />
        Назад к карточке канала
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Аналитика канала</h1>
        <p className="mt-2 text-sm text-zinc-600">
          {channel.title ?? channel.username ?? `Канал #${channel.id}`} {channel.username ? `(@${channel.username})` : ""}
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardTitle>Подписчики</CardTitle>
          <p className="mt-2 text-2xl font-semibold text-zinc-900">{channel.subscriber_count?.toLocaleString() ?? "—"}</p>
        </Card>
        <Card>
          <CardTitle>Постов в неделю</CardTitle>
          <p className="mt-2 text-2xl font-semibold text-zinc-900">{channel.posts_per_week_estimate?.toFixed(1) ?? "—"}</p>
        </Card>
        <Card>
          <CardTitle>Последний пост</CardTitle>
          <p className="mt-2 text-sm text-zinc-700">{fmtDate(channel.last_post_at)}</p>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Сводные индикаторы</CardTitle>
          <CardDescription>Быстрый обзор активности и потенциала канала по доступным метаданным.</CardDescription>
          <div className="mt-4">
            <ActivityBars data={engagementBars} />
          </div>
        </Card>
        <Card>
          <CardTitle>Оценочный ритм публикаций</CardTitle>
          <CardDescription>Недельный паттерн, построенный из текущей частоты публикаций.</CardDescription>
          <div className="mt-4">
            <TrendArea data={trendSeries} />
          </div>
        </Card>
      </div>

      <Card>
        <CardTitle>Паспорт канала</CardTitle>
        <CardDescription>Доступные поля профиля и состояние синхронизации.</CardDescription>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <p className="text-sm text-zinc-700">Тема: <span className="font-medium text-zinc-900">{channel.primary_topic ?? "—"}</span></p>
          <p className="text-sm text-zinc-700">Язык: <span className="font-medium text-zinc-900">{channel.language_hint ?? "—"}</span></p>
          <p className="text-sm text-zinc-700">Регион: <span className="font-medium text-zinc-900">{channel.region_country ?? "—"}</span></p>
          <p className="text-sm text-zinc-700">Синхронизация: <span className="font-medium text-zinc-900">{channel.sync_status ?? "—"}</span></p>
          <p className="text-sm text-zinc-700">Обновлено: <span className="font-medium text-zinc-900">{fmtDate(channel.last_sync_at)}</span></p>
          <p className="text-sm text-zinc-700">
            Публичный доступ: <span className="font-medium text-zinc-900">{channel.is_public_accessible === false ? "ограничен" : "доступен"}</span>
          </p>
        </div>
        <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
          <p className="text-xs text-zinc-500">Описание канала</p>
          <p className="mt-1 whitespace-pre-wrap text-sm text-zinc-800">{channel.description ?? "Описание не заполнено."}</p>
        </div>
      </Card>

      <Card>
        <CardTitle>Похожие каналы</CardTitle>
        <CardDescription>Краткий срез сценария 6 прямо на странице аналитики.</CardDescription>
        {recommendations?.quality_notes?.length ? (
          <div className="mt-4 space-y-2">
            {recommendations.quality_notes.map((note) => (
              <p key={note} className="text-xs text-zinc-600">{note}</p>
            ))}
          </div>
        ) : null}
        {recommendations?.results?.length ? (
          <div className="mt-4 space-y-3">
            {recommendations.results.slice(0, 3).map((item) => (
              <div key={item.channel_id} className="rounded-xl border border-zinc-200 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-zinc-900">{item.title ?? item.channel_username ?? `Канал ${item.channel_id}`}</p>
                  <Badge tone="violet">{`${Math.round(item.score * 100)}%`}</Badge>
                </div>
                {item.reasons.slice(0, 2).map((reason) => (
                  <p key={reason} className="mt-1 text-sm text-zinc-700">{reason}</p>
                ))}
              </div>
            ))}
            <Link href={`/channels/${channel.id}/recommendations`} className="text-sm text-violet-700 hover:text-violet-600">
              Открыть полный список похожих →
            </Link>
          </div>
        ) : (
          <div className="mt-4">
            <Alert variant="info" title="Похожие каналы пока не рассчитаны">
              Запустите сценарий «Похожие» для получения рекомендаций и причин сходства.
            </Alert>
          </div>
        )}
      </Card>

      {latestAnalysis?.report ? (
        <Card>
          <CardTitle>Последний сохранённый отчёт</CardTitle>
          <CardDescription>Актуальный AI-отчёт из истории анализов этого канала.</CardDescription>
          <AnalysisReportView report={latestAnalysis.report} />
        </Card>
      ) : (
        <Alert variant="info" title="Сохранённого отчёта пока нет">
          Ни один анализ ещё не сохранён для этого канала. Запустите блок «Запуск AI-анализа» ниже.
        </Alert>
      )}

      <ChannelAnalyzePanel channel={channel} />
    </div>
  );
}
