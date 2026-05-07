"use client";

import { useCallback, useEffect, useState } from "react";
import { Clock, Database, Loader2, Minimize2, Plane, Search, X } from "lucide-react";
import {
  ApiError,
  cancelOrchestrationJob,
  deleteChannel,
  fetchOrchestrationJobStatus,
  fetchTelegramStatus,
  searchChannels,
} from "@/lib/api-client";
import type {
  BackgroundSearchJob,
  SearchChannelsRequest,
  SearchChannelsResponse,
} from "@/lib/types/api";
import { ChannelSearchResultList } from "@/components/channel-search-result-list";
import { ExportLinks } from "@/components/export-links";
import { TelegramAuthDialog } from "@/components/telegram-auth-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

const selectClass =
  "w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20";
const LAST_SEARCH_CACHE_KEY = "tgci:last-search-page-state:v1";
const DISMISSED_COMPLETED_JOB_KEY = "tgci:dismissed-completed-job-id:v1";

export default function SearchPage() {
  const [searchSource, setSearchSource] = useState<"saved_catalog" | "telegram_live">("saved_catalog");
  const [topic, setTopic] = useState("investing & personal finance");
  const [count, setCount] = useState(15);
  const [showAllSaved, setShowAllSaved] = useState(false);
  const [minSub, setMinSub] = useState<number | "">("");
  const [maxSub, setMaxSub] = useState<number | "">("");
  const [channelType, setChannelType] = useState<"new_only" | "all">("all");
  const [liveChannelMode, setLiveChannelMode] = useState<"new" | "saved">("new");
  const [sortBy, setSortBy] = useState<"subscriber_count" | "last_sync_at">("subscriber_count");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [language, setLanguage] = useState("ru");
  const [region, setRegion] = useState("");
  const [usernameQuery, setUsernameQuery] = useState("");
  const [selectedSavedIds, setSelectedSavedIds] = useState<number[]>([]);
  const [savedSelectionMode, setSavedSelectionMode] = useState(false);
  const [lastPostFrom, setLastPostFrom] = useState("");
  const [lastPostTo, setLastPostTo] = useState("");
  const [extra, setExtra] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchChannelsResponse | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [trackedJob, setTrackedJob] = useState<BackgroundSearchJob | null>(null);
  const [showNoResultsModal, setShowNoResultsModal] = useState(false);
  const [showManualReviewModal, setShowManualReviewModal] = useState(false);
  const [showJobModal, setShowJobModal] = useState(false);
  const [jobModalMinimized, setJobModalMinimized] = useState(false);

  useEffect(() => {
    try {
      const raw = window.sessionStorage.getItem(LAST_SEARCH_CACHE_KEY);
      if (!raw) return;
      const parsed = JSON.parse(raw) as {
        searchSource?: "saved_catalog" | "telegram_live";
        topic?: string;
        count?: number;
        showAllSaved?: boolean;
        minSub?: number | "";
        maxSub?: number | "";
        channelType?: "new_only" | "all";
        liveChannelMode?: "new" | "saved";
        sortBy?: "subscriber_count" | "last_sync_at";
        sortOrder?: "asc" | "desc";
        language?: string;
        region?: string;
        usernameQuery?: string;
        selectedSavedIds?: number[];
        savedSelectionMode?: boolean;
        lastPostFrom?: string;
        lastPostTo?: string;
        extra?: string;
        data?: SearchChannelsResponse | null;
        trackedJob?: BackgroundSearchJob | null;
      };
      if (parsed.searchSource) setSearchSource(parsed.searchSource);
      if (typeof parsed.topic === "string") setTopic(parsed.topic);
      if (typeof parsed.count === "number") setCount(parsed.count);
      if (typeof parsed.showAllSaved === "boolean") setShowAllSaved(parsed.showAllSaved);
      if (parsed.minSub === "" || typeof parsed.minSub === "number") setMinSub(parsed.minSub);
      if (parsed.maxSub === "" || typeof parsed.maxSub === "number") setMaxSub(parsed.maxSub);
      if (parsed.channelType) setChannelType(parsed.channelType);
      if (parsed.liveChannelMode) setLiveChannelMode(parsed.liveChannelMode);
      if (parsed.sortBy) setSortBy(parsed.sortBy);
      if (parsed.sortOrder) setSortOrder(parsed.sortOrder);
      if (typeof parsed.language === "string") setLanguage(parsed.language);
      if (typeof parsed.region === "string") setRegion(parsed.region);
      if (typeof parsed.usernameQuery === "string") setUsernameQuery(parsed.usernameQuery);
      if (Array.isArray(parsed.selectedSavedIds)) setSelectedSavedIds(parsed.selectedSavedIds.map((x) => Number(x)).filter((x) => Number.isFinite(x) && x > 0));
      if (typeof parsed.savedSelectionMode === "boolean") setSavedSelectionMode(parsed.savedSelectionMode);
      if (typeof parsed.lastPostFrom === "string") setLastPostFrom(parsed.lastPostFrom);
      if (typeof parsed.lastPostTo === "string") setLastPostTo(parsed.lastPostTo);
      if (typeof parsed.extra === "string") setExtra(parsed.extra);
      if (parsed.data) setData(parsed.data);
      const dismissedJobId = window.sessionStorage.getItem(DISMISSED_COMPLETED_JOB_KEY);
      if (parsed.trackedJob && parsed.trackedJob.job_id !== dismissedJobId) {
        setTrackedJob(parsed.trackedJob);
      }
    } catch {
      /* ignore cache parse issues */
    }
  }, []);

  useEffect(() => {
    try {
      window.sessionStorage.setItem(
        LAST_SEARCH_CACHE_KEY,
        JSON.stringify({
          searchSource,
          topic,
          count,
          showAllSaved,
          minSub,
          maxSub,
          channelType,
          liveChannelMode,
          sortBy,
          sortOrder,
          language,
          region,
          usernameQuery,
          selectedSavedIds,
          savedSelectionMode,
          lastPostFrom,
          lastPostTo,
          extra,
          data,
          trackedJob,
        }),
      );
    } catch {
      /* ignore quota/private-mode errors */
    }
  }, [
    searchSource,
    topic,
    count,
    showAllSaved,
    minSub,
    maxSub,
    channelType,
    liveChannelMode,
    sortBy,
    sortOrder,
    language,
    region,
    usernameQuery,
    selectedSavedIds,
    savedSelectionMode,
    lastPostFrom,
    lastPostTo,
    extra,
    data,
    trackedJob,
  ]);

  useEffect(() => {
    const bgJob = data?.background_job;
    if (bgJob) {
      setTrackedJob((prev) => {
        if (!prev) return bgJob;
        if (prev.job_id !== bgJob.job_id) return bgJob;
        return {
          ...prev,
          ...bgJob,
        };
      });
      setShowJobModal(true);
      setJobModalMinimized(false);
    }
  }, [data?.background_job]);

  useEffect(() => {
    if (!trackedJob) {
      setShowJobModal(false);
      return;
    }
    if (!jobModalMinimized) {
      setShowJobModal(true);
    }
  }, [trackedJob, jobModalMinimized]);

  useEffect(() => {
    if (!trackedJob?.job_id) return;
    if (trackedJob.status !== "queued" && trackedJob.status !== "running") return;

    const jobId = trackedJob.job_id;
    let cancelled = false;
    async function poll(): Promise<void> {
      try {
        const st = await fetchOrchestrationJobStatus(jobId);
        if (cancelled) return;
        setTrackedJob((prev) => {
          if (!prev || prev.job_id !== st.job_id) return prev;
          return {
            ...prev,
            status: st.status,
            detail: st.detail,
            stage: st.stage,
            stage_label: st.stage_label,
            updated_at: st.updated_at,
            planner_output: st.planner_output ?? prev.planner_output,
          };
        });
      } catch (pollErr) {
        if (cancelled) return;
        const msg =
          pollErr instanceof ApiError ? `${pollErr.status}: ${pollErr.message}` : String(pollErr);
        setTrackedJob((prev) =>
          prev
            ? {
                ...prev,
                detail: `${prev.detail}\n(опрос статуса: ${msg} — после рестарта API задание могло пропасть из памяти)`,
              }
            : prev,
        );
      }
    }

    void poll();
    const id = setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [trackedJob?.job_id, trackedJob?.status]);

  const buildSearchBody = useCallback((): SearchChannelsRequest => {
    const isSaved = searchSource === "saved_catalog";
    const usernamePriority = searchSource === "telegram_live" && usernameQuery.trim().length > 0;
    return {
      topic: topic.trim(),
      count: isSaved ? (showAllSaved ? null : count) : Math.max(1, Math.min(15, count)),
      min_subscribers: isSaved ? (minSub === "" ? null : minSub) : null,
      max_subscribers: isSaved ? (maxSub === "" ? null : maxSub) : null,
      channel_type: channelType,
      live_channel_mode: isSaved ? "new" : liveChannelMode,
      sort_by: isSaved ? sortBy : "subscriber_count",
      sort_order: isSaved ? sortOrder : "desc",
      language: usernamePriority ? "ru" : language.trim() || null,
      region_country: usernamePriority ? null : region.trim() || null,
      username_query: usernameQuery.trim() || null,
      selected_channel_ids: searchSource === "telegram_live" && liveChannelMode === "saved" ? selectedSavedIds : [],
      last_post_from: isSaved ? lastPostFrom || null : null,
      last_post_to: isSaved ? lastPostTo || null : null,
      extra_conditions: usernamePriority ? null : extra.trim() || null,
      search_source: searchSource,
    };
  }, [
    topic,
    count,
    showAllSaved,
    minSub,
    maxSub,
    channelType,
    liveChannelMode,
    sortBy,
    sortOrder,
    language,
    region,
    usernameQuery,
    selectedSavedIds,
    lastPostFrom,
    lastPostTo,
    extra,
    searchSource,
  ]);

  const runSearchRequest = useCallback(async () => {
    const res = await searchChannels(buildSearchBody());
    setData(res);
    setShowManualReviewModal(Boolean(res.manual_review?.needs_review));
    setShowNoResultsModal(
      !res.channels.length && !res.manual_review?.needs_review && !res.background_job,
    );
  }, [buildSearchBody]);

  const closeCompletedJobModal = useCallback(() => {
    if (trackedJob?.status === "completed" && trackedJob.job_id) {
      window.sessionStorage.setItem(DISMISSED_COMPLETED_JOB_KEY, trackedJob.job_id);
    }
    setTrackedJob(null);
    setData((prev) => (prev ? { ...prev, background_job: null } : prev));
    setShowJobModal(false);
    setJobModalMinimized(false);
  }, [trackedJob]);

  const handleCancelJob = useCallback(async () => {
    if (!trackedJob?.job_id) return;
    const ok = window.confirm(
      "Отменить текущее фоновое задание? Прогресс может быть потерян.",
    );
    if (!ok) return;
    try {
      const st = await cancelOrchestrationJob(trackedJob.job_id);
      setTrackedJob((prev) =>
        prev
          ? {
              ...prev,
              status: st.status as BackgroundSearchJob["status"],
              detail: st.detail,
              stage: st.stage,
              stage_label: st.stage_label,
              updated_at: st.updated_at,
            }
          : prev,
      );
      setShowJobModal(false);
      setJobModalMinimized(false);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Не удалось отменить задание");
    }
  }, [trackedJob]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setData(null);
    try {
      if (searchSource === "telegram_live") {
        if (liveChannelMode === "saved" && selectedSavedIds.length === 0) {
          const pickRes = await searchChannels({
            ...buildSearchBody(),
            search_source: "saved_catalog",
            count: null,
            channel_type: "all",
          });
          setSavedSelectionMode(true);
          setData(pickRes);
          setShowManualReviewModal(Boolean(pickRes.manual_review?.needs_review));
          setShowNoResultsModal(!pickRes.channels.length && !pickRes.manual_review?.needs_review);
          return;
        }
        const status = await fetchTelegramStatus();
        if (!status.session_ready) {
          setLoading(false);
          if (!status.api_configured) {
            setError("На сервере не заданы TELEGRAM_API_ID и TELEGRAM_API_HASH — живой поиск Telegram недоступен.");
            return;
          }
          if (!status.interactive_login_available) {
            const extra =
              status.startup_failure?.trim() ||
              "Интерактивный вход отключён (TELEGRAM_INTERACTIVE_LOGIN). Задайте TELEGRAM_SESSION или .session и перезапустите API.";
            setError(`Сессия Telegram не подключена. ${extra}`);
            return;
          }
          setAuthOpen(true);
          return;
        }
        await runSearchRequest();
        setSavedSelectionMode(false);
        return;
      }

      await runSearchRequest();
      setSavedSelectionMode(false);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  const handleAuthSuccess = useCallback(async () => {
    setAuthOpen(false);
    setLoading(true);
    setError(null);
    try {
      await runSearchRequest();
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }, [runSearchRequest]);

  const onDeleteChannel = useCallback(
    async (channelId: number) => {
      if (!window.confirm("Удалить канал из сохраненного каталога?")) return;
      try {
        await deleteChannel(channelId);
        await runSearchRequest();
      } catch (err) {
        setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Не удалось удалить канал");
      }
    },
    [runSearchRequest],
  );

  const job = trackedJob;
  const jobActive = job && (job.status === "queued" || job.status === "running");

  return (
    <div className="relative mx-auto max-w-4xl space-y-8">
      {loading ? (
        <div
          className="fixed inset-0 z-40 flex flex-col items-center justify-center gap-4 bg-white/80 backdrop-blur-sm"
          aria-busy="true"
          aria-live="polite"
        >
          <div className="relative flex size-16 items-center justify-center">
            <Loader2 className="absolute size-14 animate-spin text-violet-600" aria-hidden />
            <Clock className="relative size-7 text-violet-800/90" aria-hidden />
          </div>
          <p className="max-w-sm text-center text-sm font-medium text-zinc-800">
            {searchSource === "telegram_live"
              ? "Выполняется поиск в Telegram и постановка фонового задания…"
              : "Выполняется поиск по сохраненному каталогу…"}
          </p>
        </div>
      ) : null}

      <TelegramAuthDialog open={authOpen} onClose={() => setAuthOpen(false)} onSuccess={handleAuthSuccess} />

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Поиск каналов</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Выберите <strong className="font-medium text-zinc-800">сохраненный каталог</strong> (SQLite) или{" "}
          <strong className="font-medium text-zinc-800">Telegram (live)</strong>. Если сессии нет, откроется окно входа.
        </p>
      </div>

      <Card>
        <CardTitle>Фильтры</CardTitle>
        <CardDescription>
          Тема обязательна. В режиме Telegram live сначала проверяется сессия на сервере.
        </CardDescription>
        <form onSubmit={onSubmit} className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label>Источник поиска</Label>
            <div className="mt-2 flex flex-wrap gap-3">
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 has-[:checked]:border-violet-400 has-[:checked]:bg-violet-50">
                <input
                  type="radio"
                  name="scope"
                  checked={searchSource === "saved_catalog"}
                  onChange={() => setSearchSource("saved_catalog")}
                  className="text-violet-600"
                />
                <Database className="size-4 text-violet-600" />
                <span className="text-sm font-medium text-zinc-800">Сохраненный каталог</span>
              </label>
              <label className="flex cursor-pointer items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 px-4 py-3 has-[:checked]:border-violet-400 has-[:checked]:bg-violet-50">
                <input
                  type="radio"
                  name="scope"
                  checked={searchSource === "telegram_live"}
                  onChange={() => setSearchSource("telegram_live")}
                  className="text-violet-600"
                />
                <Plane className="size-4 text-violet-600" />
                <span className="text-sm font-medium text-zinc-800">Telegram (live)</span>
              </label>
            </div>
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="topic">Тема / ниша</Label>
            <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} required />
          </div>
          <div>
            <Label htmlFor="count">Сколько каналов</Label>
            {searchSource === "saved_catalog" ? (
              <div className="space-y-2">
                <Input
                  id="count"
                  type="number"
                  min={1}
                  value={count}
                  disabled={showAllSaved}
                  onChange={(e) => setCount(Number(e.target.value) || 1)}
                />
                <label className="inline-flex items-center gap-2 text-sm text-zinc-700">
                  <input
                    type="checkbox"
                    checked={showAllSaved}
                    onChange={(e) => setShowAllSaved(e.target.checked)}
                  />
                  Показать все
                </label>
              </div>
            ) : (
              <Input
                id="count"
                type="number"
                min={1}
                max={15}
                value={count}
                onChange={(e) => setCount(Number(e.target.value) || 1)}
              />
            )}
          </div>
          <div>
            <Label htmlFor="ctype">Тип каналов</Label>
            <select
              id="ctype"
              value={searchSource === "saved_catalog" ? channelType : liveChannelMode}
              onChange={(e) => {
                if (searchSource === "saved_catalog") {
                  setChannelType(e.target.value as "new_only" | "all");
                } else {
                  setLiveChannelMode(e.target.value as "new" | "saved");
                  setSavedSelectionMode(false);
                  setSelectedSavedIds([]);
                }
              }}
              className={selectClass}
            >
              {searchSource === "saved_catalog" ? (
                <>
                  <option value="all">Все</option>
                  <option value="new_only">Показать последние</option>
                </>
              ) : (
                <>
                  <option value="saved">Сохраненные</option>
                  <option value="new">Новые</option>
                </>
              )}
            </select>
          </div>
          {searchSource === "saved_catalog" ? (
            <>
              <div>
                <Label htmlFor="sortBy">Сортировка</Label>
                <select
                  id="sortBy"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as "subscriber_count" | "last_sync_at")}
                  className={selectClass}
                >
                  <option value="subscriber_count">Количество подписчиков</option>
                  <option value="last_sync_at">Дата обновления</option>
                </select>
              </div>
              <div>
                <Label htmlFor="sortOrder">Порядок</Label>
                <select
                  id="sortOrder"
                  value={sortOrder}
                  onChange={(e) => setSortOrder(e.target.value as "asc" | "desc")}
                  className={selectClass}
                >
                  <option value="desc">{sortBy === "last_sync_at" ? "Сначала последние" : "По убыванию"}</option>
                  <option value="asc">{sortBy === "last_sync_at" ? "Сначала старые" : "По возрастанию"}</option>
                </select>
              </div>
            </>
          ) : null}
          {searchSource === "saved_catalog" ? (
            <>
              <div>
                <Label htmlFor="min">Подписчиков от</Label>
                <Input
                  id="min"
                  type="number"
                  min={0}
                  placeholder="необязательно"
                  value={minSub}
                  onChange={(e) => setMinSub(e.target.value === "" ? "" : Number(e.target.value))}
                />
              </div>
              <div>
                <Label htmlFor="max">Подписчиков до</Label>
                <Input
                  id="max"
                  type="number"
                  min={0}
                  placeholder="необязательно"
                  value={maxSub}
                  onChange={(e) => setMaxSub(e.target.value === "" ? "" : Number(e.target.value))}
                />
              </div>
            </>
          ) : null}
          <div>
            <Label htmlFor="lang">Язык</Label>
            <Input id="lang" placeholder="ru, en…" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="region">Регион / страна</Label>
            <Input id="region" placeholder="необязательно" value={region} onChange={(e) => setRegion(e.target.value)} />
          </div>
          {searchSource === "saved_catalog" || searchSource === "telegram_live" ? (
            <div className="sm:col-span-2 grid gap-4 md:grid-cols-3">
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
                <Input
                  id="lastPostTo"
                  type="date"
                  value={lastPostTo}
                  onChange={(e) => setLastPostTo(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="usernameQuery">Username канала</Label>
                <Input
                  id="usernameQuery"
                  placeholder="@username или https://t.me/channel"
                  value={usernameQuery}
                  onChange={(e) => setUsernameQuery(e.target.value)}
                />
              </div>
            </div>
          ) : null}
          {searchSource === "telegram_live" && usernameQuery.trim() ? (
            <div className="sm:col-span-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
              Поиск по username активен: остальные фильтры (кроме «Тема / ниша») будут проигнорированы. Язык установлен в
              `ru` по умолчанию.
            </div>
          ) : null}
          {searchSource === "telegram_live" && liveChannelMode === "saved" ? (
            <div className="sm:col-span-2 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-sm text-zinc-700">
              Сначала нажмите «Найти каналы», выберите от 1 до 20 сохранённых каналов и нажмите «Найти каналы» ещё раз для
              актуализации данных в Telegram.
            </div>
          ) : null}
          <div className="sm:col-span-2">
            <Label htmlFor="extra">Дополнительные условия</Label>
            <Textarea id="extra" placeholder="Свободный текст для планировщика…" value={extra} onChange={(e) => setExtra(e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={loading} className="w-full sm:w-auto">
              {loading ? <Spinner /> : <Search className="size-4" />}
              Найти каналы
            </Button>
          </div>
        </form>
      </Card>

      <ExportLinks />

      {error ? (
        <Alert variant="error" title="Ошибка поиска">
          {error}
        </Alert>
      ) : null}

      {showManualReviewModal && data?.manual_review?.needs_review ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-lg">
            <div className="flex items-start justify-between gap-3">
              <CardTitle>Требуется ручная проверка</CardTitle>
              <Button variant="ghost" onClick={() => setShowManualReviewModal(false)} aria-label="Закрыть">
                <X className="size-4" />
              </Button>
            </div>
            <p className="mt-2 text-sm text-zinc-700">{data.manual_review.reason}</p>
            {data.manual_review.hints?.length ? (
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-zinc-700">
                {data.manual_review.hints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            ) : null}
          </Card>
        </div>
      ) : null}

      {job && showJobModal && !jobModalMinimized ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-2xl">
            <div className="flex items-start justify-between gap-3">
              <CardTitle>Фоновая задача</CardTitle>
              <div className="flex items-center gap-1">
                {job.status === "completed" || job.status === "failed" ? (
                  <Button variant="ghost" onClick={closeCompletedJobModal} aria-label="Закрыть">
                    <X className="size-4" />
                  </Button>
                ) : (
                  <>
                    <Button
                      variant="ghost"
                      onClick={() => {
                        setJobModalMinimized(true);
                        setShowJobModal(false);
                      }}
                      aria-label="Свернуть"
                    >
                      <Minimize2 className="size-4" />
                    </Button>
                    <Button variant="ghost" onClick={handleCancelJob} aria-label="Отменить задание">
                      <X className="size-4" />
                    </Button>
                  </>
                )}
              </div>
            </div>
            <CardDescription>
              Поиск запущен. Статус:
            </CardDescription>
            <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-zinc-700">
              {jobActive ? <Loader2 className="size-4 shrink-0 animate-spin text-violet-600" aria-hidden /> : null}
              <Badge tone={job.status === "failed" ? "warning" : "violet"}>{job.status}</Badge>
            </div>
            {job.detail ? (
              <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-600">{job.detail}</p>
            ) : null}
            <p className="mt-2 text-sm text-violet-800">
              После завершения пайплайна каналы появятся в каталоге — затем снова запустите поиск в режиме
              «Сохраненный каталог».
            </p>
          </Card>
        </div>
      ) : null}
      {job && jobModalMinimized ? (
        <Button
          className="fixed bottom-6 right-6 z-20"
          variant="secondary"
          onClick={() => {
            setShowJobModal(true);
            setJobModalMinimized(false);
          }}
        >
          Открыть статус задачи
        </Button>
      ) : null}

      {data?.normalized_filters && Object.keys(data.normalized_filters).length > 0 ? (
        <Card>
          <CardTitle>Нормализованные фильтры</CardTitle>
          <CardDescription>Что планировщик выделил из вашего запроса.</CardDescription>
          <pre className="mt-4 max-h-48 overflow-auto rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-600">
            {JSON.stringify(data.normalized_filters, null, 2)}
          </pre>
        </Card>
      ) : null}

      {data?.channels?.length ? (
        <div className="space-y-3">
          <h2 className="text-lg font-medium text-zinc-900">Результаты ({data.channels.length})</h2>
          <p className="text-sm text-zinc-600">
            {savedSelectionMode
              ? "Выберите каналы для актуализации. Можно выбрать до 20."
              : "Нажмите на строку, чтобы открыть карточку канала."}
          </p>
          <ChannelSearchResultList
            channels={data.channels}
            onDelete={savedSelectionMode ? undefined : onDeleteChannel}
            selectable={savedSelectionMode}
            selectedIds={selectedSavedIds}
            onToggleSelect={(channelId, checked) => {
              setSelectedSavedIds((prev) => {
                if (checked) {
                  if (prev.includes(channelId) || prev.length >= 20) return prev;
                  return [...prev, channelId];
                }
                return prev.filter((x) => x !== channelId);
              });
            }}
          />
          {savedSelectionMode ? (
            <p className="text-sm text-zinc-700">
              Выбрано: <strong>{selectedSavedIds.length}</strong> / 20. При следующем запуске поиска будут обновляться
              именно выбранные каналы (приоритет над полем «Сколько каналов»).
            </p>
          ) : null}
        </div>
      ) : null}

      {showNoResultsModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-lg">
            <div className="flex items-start justify-between gap-3">
              <CardTitle>Поиск завершён</CardTitle>
              <Button variant="ghost" onClick={() => setShowNoResultsModal(false)} aria-label="Закрыть">
                <X className="size-4" />
              </Button>
            </div>
            <p className="mt-2 text-sm text-zinc-700">
              Ничего не найдено. Попробуйте расширить тему или ослабить фильтры.
            </p>
          </Card>
        </div>
      ) : null}

      {data?.background_job && !data.channels.length ? (
        <p className="text-sm text-zinc-600">
          Каналы появятся в сохраненном каталоге после завершения фонового пайплайна; затем запустите поиск в режиме{" "}
          <strong>Saved catalog</strong>.
        </p>
      ) : null}
    </div>
  );
}
