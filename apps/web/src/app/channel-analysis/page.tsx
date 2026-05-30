"use client";

import { useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import {
  analyzeChannelByHandle,
  ApiError,
  searchChannels,
  listChannelAnalyses,
  getSavedChannelAnalysis,
  deleteChannelAnalysis,
  summarizeChannelByHandle,
} from "@/lib/api-client";
import type {
  AnalyzeChannelResponse,
  ChannelAnalysisHistoryItem,
  ChannelCard,
  SavedChannelAnalysisDetail,
  SummarizePostsResponse,
} from "@/lib/types/api";
import { AnalysisReportView } from "@/components/channel-analysis-report-view";
import { ChannelAnalysisPdfButton } from "@/components/channel-analysis-pdf-button";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";

const selectClass =
  "w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20";

function channelRefFromCard(ch: ChannelCard): string {
  if (ch.username) return `@${ch.username.replace(/^@/, "")}`;
  if (ch.invite_slug) return ch.invite_slug;
  return String(ch.telegram_id);
}

function mapSavedToAnalyzeResponse(s: SavedChannelAnalysisDetail): AnalyzeChannelResponse {
  return {
    analysis_id: s.analysis_id,
    channel_id: s.channel_id,
    status: s.status,
    message: s.message,
    report: s.report,
    channel_display_ref: s.channel_display_ref ?? null,
  };
}

function formatHistoryDate(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function ChannelAnalysisPage() {
  const [channelRef, setChannelRef] = useState("");
  const [intent, setIntent] = useState("");
  const [postLimit, setPostLimit] = useState(10);
  const [loading, setLoading] = useState(false);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [errorTitle, setErrorTitle] = useState("Ошибка");
  const [result, setResult] = useState<AnalyzeChannelResponse | null>(null);
  const [summaryResult, setSummaryResult] = useState<SummarizePostsResponse | null>(null);
  const [showPick, setShowPick] = useState(false);

  const [resolvedChannelId, setResolvedChannelId] = useState<number | null>(null);
  const [showHistory, setShowHistory] = useState(false);
  const [historyRows, setHistoryRows] = useState<ChannelAnalysisHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(15);
  const [language, setLanguage] = useState("ru");
  const [region, setRegion] = useState("");
  const [usernameQuery, setUsernameQuery] = useState("");
  const [lastPostFrom, setLastPostFrom] = useState("");
  const [lastPostTo, setLastPostTo] = useState("");
  const [sortBy, setSortBy] = useState<"subscriber_count" | "last_sync_at">("subscriber_count");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [minSub, setMinSub] = useState<number | "">("");
  const [maxSub, setMaxSub] = useState<number | "">("");
  const [pickRows, setPickRows] = useState<ChannelCard[]>([]);
  const [pickLoading, setPickLoading] = useState(false);
  const [pickError, setPickError] = useState<string | null>(null);

  useEffect(() => {
    const v = new URLSearchParams(window.location.search).get("channel_ref");
    if (v) setChannelRef(v);
  }, []);

  const report = result?.report;
  const manualReview = result?.manual_review;
  const reportChannelLabel =
    result?.channel_display_ref?.trim() ||
    channelRef.trim() ||
    (result?.channel_id ? `#${result.channel_id}` : "");
  const statusTone = useMemo(() => {
    if (!result) return "border-zinc-200 bg-zinc-50 text-zinc-900";
    if (result.status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-950";
    return "border-amber-200 bg-amber-50 text-amber-950";
  }, [result]);

  async function openHistoryPanel() {
    setShowHistory(true);
    setHistoryError(null);
    setHistoryLoading(true);
    try {
      const rows = await listChannelAnalyses();
      setHistoryRows(rows);
    } catch (err) {
      setHistoryError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function deleteReportById(analysisId: number, source: "card" | "history") {
    if (!confirm("Удалить этот отчёт из истории?")) return;
    try {
      await deleteChannelAnalysis(analysisId);
      setHistoryRows((rows) => rows.filter((r) => r.id !== analysisId));
      if (result?.analysis_id === analysisId) setResult(null);
      setHistoryError(null);
      setError(null);
    } catch (err) {
      const msg = err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed";
      if (source === "history") setHistoryError(msg);
      else setError(msg);
    }
  }

  async function onSelectHistoryRow(row: ChannelAnalysisHistoryItem) {
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const detail = await getSavedChannelAnalysis(row.id);
      setResult(mapSavedToAnalyzeResponse(detail));
      setShowHistory(false);
    } catch (err) {
      setHistoryError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setHistoryLoading(false);
    }
  }

  async function onSearchSaved(e: React.FormEvent) {
    e.preventDefault();
    setPickLoading(true);
    setPickError(null);
    try {
      const data = await searchChannels({
        topic: topic.trim() || "канал",
        count,
        min_subscribers: minSub === "" ? null : minSub,
        max_subscribers: maxSub === "" ? null : maxSub,
        channel_type: "all",
        language: language.trim() || null,
        region_country: region.trim() || null,
        username_query: usernameQuery.trim() || null,
        last_post_from: lastPostFrom || null,
        last_post_to: lastPostTo || null,
        extra_conditions: null,
        sort_by: sortBy,
        sort_order: sortOrder,
        search_source: "saved_catalog",
      });
      setPickRows(data.channels);
      if (data.manual_review?.needs_review) {
        setPickError(data.manual_review.reason);
      }
    } catch (err) {
      setPickError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setPickLoading(false);
    }
  }

  async function onAnalyze(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setErrorTitle("Ошибка анализа");
    setResult(null);
    setSummaryResult(null);
    try {
      const res = await analyzeChannelByHandle({
        channel_ref: channelRef.trim(),
        user_intent: intent.trim() || undefined,
        post_limit: postLimit,
      });
      setResult(res);
      if (res.channel_id > 0) {
        setResolvedChannelId(res.channel_id);
      }
    } catch (err) {
      setError(formatRequestError(err));
    } finally {
      setLoading(false);
    }
  }

  function formatRequestError(err: unknown): string {
    if (err instanceof ApiError) return `${err.status}: ${err.message}`;
    if (err instanceof Error && err.message) return err.message;
    return "Не удалось выполнить запрос к API";
  }

  async function onSummarizePosts() {
    setSummaryLoading(true);
    setError(null);
    setErrorTitle("Ошибка резюме постов");
    setResult(null);
    setSummaryResult(null);
    try {
      const res = await summarizeChannelByHandle({
        channel_ref: channelRef.trim(),
        post_limit: postLimit,
      });
      setSummaryResult(res);
      if (res.channel_id > 0) {
        setResolvedChannelId(res.channel_id);
      }
    } catch (err) {
      setError(formatRequestError(err));
    } finally {
      setSummaryLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Анализ конкретного Telegram-канала</h1>
          <p className="mt-2 text-sm text-zinc-600">
            Введите ссылку на канал или username, либо выберите канал из сохраненного каталога.
          </p>
        </div>
        <Button type="button" variant="secondary" onClick={() => void openHistoryPanel()}>
          Сохранённые отчёты
        </Button>
      </div>

      <Card>
        <CardTitle>Запуск анализа</CardTitle>
        <CardDescription>Шаги: проверка доступа, сбор последних постов, AI-анализ, сохранение отчета.</CardDescription>
        <form onSubmit={onAnalyze} className="mt-4 space-y-4">
          <div>
            <Label htmlFor="channelRef">Ссылка или username канала</Label>
            <Input
              id="channelRef"
              placeholder="@channel_username или https://t.me/channel"
              value={channelRef}
              onChange={(e) => setChannelRef(e.target.value)}
              required
            />
          </div>
          {resolvedChannelId != null ? (
            <p className="text-xs text-zinc-500">
              Последний проанализированный канал в каталоге: id {resolvedChannelId} (для удобства навигации).
            </p>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="postLimit">Сколько постов анализировать</Label>
              <Input
                id="postLimit"
                type="number"
                min={3}
                max={20}
                value={postLimit}
                onChange={(e) => setPostLimit(Math.max(3, Math.min(20, Number(e.target.value) || 10)))}
              />
            </div>
            <div>
              <Label htmlFor="intent">Фокус анализа (необязательно)</Label>
              <Textarea
                id="intent"
                placeholder="Например: оценить риски и рекламную пригодность"
                value={intent}
                onChange={(e) => setIntent(e.target.value)}
              />
              <p className="mt-1.5 text-xs leading-relaxed text-zinc-500">
                Этот текст передаётся в LLM-планировщик как «намерение пользователя»: от него зависят шаги пайплайна,
                приоритет тем и при необходимости — решение о семантическом поиске по накопленному корпусу (RAG).
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-3">
            <Button type="submit" disabled={loading}>
              {loading ? <Spinner /> : null}
              Анализировать канал
            </Button>
            <Button type="button" variant="secondary" disabled={summaryLoading || !channelRef.trim()} onClick={() => void onSummarizePosts()}>
              {summaryLoading ? <Spinner /> : null}
              Резюмировать посты
            </Button>
            <Button type="button" variant="secondary" onClick={() => setShowPick((v) => !v)}>
              {showPick ? "Свернуть фильтры" : "Выбрать из сохраненных"}
            </Button>
            <Button type="button" variant="ghost" onClick={() => setChannelRef("")}>
              Очистить поле
            </Button>
          </div>
        </form>
      </Card>

      {showPick ? (
        <Card>
          <CardTitle>Выбор канала из сохраненного каталога</CardTitle>
          <CardDescription>Для анализа канала выберите его в списке.</CardDescription>
          <form onSubmit={onSearchSaved} className="mt-4 grid gap-4 md:grid-cols-3">
            <div>
              <Label htmlFor="topic">Тема / ниша</Label>
              <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="необязательно" />
            </div>
            <div>
              <Label htmlFor="count">Сколько каналов</Label>
              <Input
                id="count"
                type="number"
                min={1}
                value={count}
                onChange={(e) => setCount(Math.max(1, Number(e.target.value) || 15))}
              />
            </div>
            <div>
              <Label htmlFor="minSubPick">Подписчиков от</Label>
              <Input
                id="minSubPick"
                type="number"
                min={0}
                value={minSub === "" ? "" : minSub}
                onChange={(e) => {
                  const v = e.target.value;
                  setMinSub(v === "" ? "" : Math.max(0, Number(v)));
                }}
                placeholder="необязательно"
              />
            </div>
            <div>
              <Label htmlFor="maxSubPick">Подписчиков до</Label>
              <Input
                id="maxSubPick"
                type="number"
                min={0}
                value={maxSub === "" ? "" : maxSub}
                onChange={(e) => {
                  const v = e.target.value;
                  setMaxSub(v === "" ? "" : Math.max(0, Number(v)));
                }}
                placeholder="необязательно"
              />
            </div>
            <div>
              <Label htmlFor="language">Язык</Label>
              <Input id="language" value={language} onChange={(e) => setLanguage(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="region">Регион / страна</Label>
              <Input id="region" value={region} onChange={(e) => setRegion(e.target.value)} placeholder="необязательно" />
            </div>
            <div>
              <Label htmlFor="usernameQuery">Username</Label>
              <Input
                id="usernameQuery"
                value={usernameQuery}
                onChange={(e) => setUsernameQuery(e.target.value)}
                placeholder="@username"
              />
            </div>
            <div>
              <Label htmlFor="sortBy">Сортировка</Label>
              <select
                id="sortBy"
                className={selectClass}
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as "subscriber_count" | "last_sync_at")}
              >
                <option value="subscriber_count">Количество подписчиков</option>
                <option value="last_sync_at">Дата обновления</option>
              </select>
            </div>
            <div>
              <Label htmlFor="sortOrder">Порядок</Label>
              <select
                id="sortOrder"
                className={selectClass}
                value={sortOrder}
                onChange={(e) => setSortOrder(e.target.value as "asc" | "desc")}
              >
                <option value="desc">{sortBy === "last_sync_at" ? "Сначала последние" : "По убыванию"}</option>
                <option value="asc">{sortBy === "last_sync_at" ? "Сначала старые" : "По возрастанию"}</option>
              </select>
            </div>
            <div>
              <Label htmlFor="lastPostFrom">Последний пост от</Label>
              <Input
                id="lastPostFrom"
                type="date"
                value={lastPostFrom}
                onChange={(e) => setLastPostFrom(e.target.value)}
              />
            </div>
            <div>
              <Label htmlFor="lastPostTo">Последний пост до</Label>
              <Input id="lastPostTo" type="date" value={lastPostTo} onChange={(e) => setLastPostTo(e.target.value)} />
            </div>
            <div className="md:col-span-3">
              <Button type="submit" disabled={pickLoading}>
                {pickLoading ? <Spinner /> : null}
                Найти в сохраненном каталоге
              </Button>
            </div>
          </form>

          {pickError ? (
            <div className="mt-4">
              <Alert variant="error" title="Ошибка поиска">
                {pickError}
              </Alert>
            </div>
          ) : null}

          <div className="mt-4 space-y-2">
            {pickRows.map((ch) => (
              <div key={ch.id} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-200 p-3">
                <div className="text-sm text-zinc-700">
                  <p className="font-medium text-zinc-900">{ch.title ?? ch.username ?? `Канал #${ch.id}`}</p>
                  <p>@{ch.username ?? "—"} · Подписчики: {ch.subscriber_count?.toLocaleString() ?? "—"}</p>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => {
                    setChannelRef(channelRefFromCard(ch));
                    setResolvedChannelId(ch.id);
                    setShowPick(false);
                    window.scrollTo({ top: 0, behavior: "smooth" });
                  }}
                >
                  Выбрать для анализа
                </Button>
              </div>
            ))}
            {!pickLoading && pickRows.length === 0 ? (
              <p className="text-sm text-zinc-500">Список пуст. Попробуйте изменить фильтры.</p>
            ) : null}
          </div>
        </Card>
      ) : null}

      {error ? (
        <Alert variant="error" title={errorTitle}>
          {error}
        </Alert>
      ) : null}

      {manualReview?.needs_review ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-lg">
            <div className="flex items-start justify-between gap-3">
              <CardTitle>Не удалось выполнить анализ</CardTitle>
              <Button variant="ghost" onClick={() => setResult(null)} aria-label="Закрыть">
                Закрыть
              </Button>
            </div>
            <p className="mt-2 text-sm text-zinc-700">{manualReview.reason}</p>
          </Card>
        </div>
      ) : null}

      {showHistory ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <Card className="max-h-[85vh] w-full max-w-lg overflow-hidden">
            <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-3">
              <div>
                <CardTitle>Сохранённые отчёты</CardTitle>
                <CardDescription>Выберите строку, чтобы открыть сохранённый результат анализа.</CardDescription>
              </div>
              <Button variant="ghost" onClick={() => setShowHistory(false)} aria-label="Закрыть">
                Закрыть
              </Button>
            </div>
            {historyLoading ? (
              <div className="flex justify-center py-8">
                <Spinner />
              </div>
            ) : null}
            {historyError ? (
              <div className="mt-3">
                <Alert variant="error" title="Ошибка">
                  {historyError}
                </Alert>
              </div>
            ) : null}
            <div className="mt-3 max-h-[55vh] space-y-1 overflow-y-auto pr-1">
              {historyRows.map((row) => (
                <div
                  key={row.id}
                  className="flex items-stretch gap-1 rounded-xl border border-zinc-200 bg-white transition hover:border-violet-300 hover:bg-violet-50/50"
                >
                  <button
                    type="button"
                    className="min-w-0 flex-1 px-3 py-2.5 text-left text-sm"
                    onClick={() => void onSelectHistoryRow(row)}
                  >
                    <span className="font-medium text-zinc-900">#{row.id}</span>
                    <span className="text-zinc-500"> · канал </span>
                    <span className="text-zinc-800">
                      {row.channel_display_ref?.trim() || row.channel_id || "—"}
                    </span>
                    <span className="text-zinc-500"> · </span>
                    <span className="text-zinc-600">{row.status}</span>
                    <span className="mt-0.5 block text-xs text-zinc-500">{formatHistoryDate(row.created_at)}</span>
                  </button>
                  <ChannelAnalysisPdfButton
                    analysisId={row.id}
                    stopPropagation
                    className="shrink-0 rounded-none p-2.5"
                  />
                  <Button
                    type="button"
                    variant="ghost"
                    className="shrink-0 rounded-none rounded-r-xl p-2.5"
                    aria-label="Удалить отчёт"
                    onClick={(e) => {
                      e.stopPropagation();
                      void deleteReportById(row.id, "history");
                    }}
                  >
                    <Trash2 className="size-4 text-zinc-500" />
                  </Button>
                </div>
              ))}
              {!historyLoading && historyRows.length === 0 ? (
                <p className="py-6 text-center text-sm text-zinc-500">Пока нет сохранённых отчётов.</p>
              ) : null}
            </div>
          </Card>
        </div>
      ) : null}

      {result ? (
        <Card>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <CardTitle>
              {reportChannelLabel
                ? `Результат анализа канала ${reportChannelLabel}`
                : "Результат анализа канала"}
            </CardTitle>
            {result.analysis_id > 0 ? (
              <div className="flex shrink-0 items-center gap-0.5">
                <ChannelAnalysisPdfButton analysisId={result.analysis_id} />
                <Button
                  type="button"
                  variant="ghost"
                  className="p-2"
                  aria-label="Удалить отчёт"
                  onClick={() => void deleteReportById(result.analysis_id, "card")}
                >
                  <Trash2 className="size-4 text-zinc-500" />
                </Button>
              </div>
            ) : null}
          </div>
          <div className={`mt-4 rounded-xl border p-3 text-sm whitespace-pre-line ${statusTone}`}>
            {result.message}
          </div>
          {report ? <AnalysisReportView report={report} /> : null}
        </Card>
      ) : null}

      {summaryResult ? (
        <Card>
          <CardTitle>
            {summaryResult.channel_display_ref
              ? `Резюме постов канала ${summaryResult.channel_display_ref}`
              : "Резюме постов канала"}
          </CardTitle>
          <CardDescription>Обработано постов: {summaryResult.posts_used}</CardDescription>
          <div className="mt-4 rounded-xl border border-cyan-200 bg-cyan-50 p-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-cyan-950">{summaryResult.summary}</p>
            {summaryResult.stored_analysis_hint ? (
              <p className="mt-3 text-xs text-cyan-900/80">{summaryResult.stored_analysis_hint}</p>
            ) : null}
          </div>
          {summaryResult.per_post_summaries?.length ? (
            <div className="mt-4 space-y-2">
              {summaryResult.per_post_summaries.map((item) => (
                <div key={item} className="rounded-lg border border-zinc-200 bg-white p-3 text-sm text-zinc-800">
                  {item}
                </div>
              ))}
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}
