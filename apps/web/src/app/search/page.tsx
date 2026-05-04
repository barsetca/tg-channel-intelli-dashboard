"use client";

import { useCallback, useEffect, useState } from "react";
import { Clock, Database, Loader2, Plane, Search } from "lucide-react";
import { ApiError, fetchOrchestrationJobStatus, fetchTelegramStatus, searchChannels } from "@/lib/api-client";
import type {
  BackgroundSearchJob,
  SearchChannelsRequest,
  SearchChannelsResponse,
} from "@/lib/types/api";
import { ChannelSearchResultList } from "@/components/channel-search-result-list";
import { ExportLinks } from "@/components/export-links";
import { ManualReviewBanner } from "@/components/manual-review-banner";
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

export default function SearchPage() {
  const [searchSource, setSearchSource] = useState<"saved_catalog" | "telegram_live">("saved_catalog");
  const [topic, setTopic] = useState("investing & personal finance");
  const [count, setCount] = useState(15);
  const [minSub, setMinSub] = useState<number | "">("");
  const [maxSub, setMaxSub] = useState<number | "">("");
  const [channelType, setChannelType] = useState<"new_only" | "all">("all");
  const [language, setLanguage] = useState("ru");
  const [region, setRegion] = useState("");
  const [extra, setExtra] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SearchChannelsResponse | null>(null);
  const [authOpen, setAuthOpen] = useState(false);
  const [trackedJob, setTrackedJob] = useState<BackgroundSearchJob | null>(null);

  useEffect(() => {
    if (data?.background_job) {
      setTrackedJob(data.background_job);
    } else {
      setTrackedJob(null);
    }
  }, [data?.background_job]);

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
    return {
      topic: topic.trim(),
      count,
      min_subscribers: minSub === "" ? null : minSub,
      max_subscribers: maxSub === "" ? null : maxSub,
      channel_type: channelType,
      language: language.trim() || null,
      region_country: region.trim() || null,
      extra_conditions: extra.trim() || null,
      search_source: searchSource,
    };
  }, [topic, count, minSub, maxSub, channelType, language, region, extra, searchSource]);

  const runSearchRequest = useCallback(async () => {
    const res = await searchChannels(buildSearchBody());
    setData(res);
  }, [buildSearchBody]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setData(null);
    try {
      if (searchSource === "telegram_live") {
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
        return;
      }

      await runSearchRequest();
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

  const job = trackedJob ?? data?.background_job ?? null;
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
              ? "Идёт запрос к API: поиск в Telegram или постановка фонового задания…"
              : "Идёт поиск по каталогу…"}
          </p>
        </div>
      ) : null}

      <TelegramAuthDialog open={authOpen} onClose={() => setAuthOpen(false)} onSuccess={handleAuthSuccess} />

      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Channel search</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Choose <strong className="font-medium text-zinc-800">saved catalog</strong> (SQLite) or{" "}
          <strong className="font-medium text-zinc-800">Telegram (live)</strong>. Для live при отсутствии сессии
          откроется окно входа; при готовой сессии показывается индикатор ожидания на время запроса.
        </p>
      </div>

      <Card>
        <CardTitle>Filters</CardTitle>
        <CardDescription>
          Topic is required; Telegram live checks the server session first, then runs search or opens sign-in.
        </CardDescription>
        <form onSubmit={onSubmit} className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <Label>Search scope</Label>
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
                <span className="text-sm font-medium text-zinc-800">Saved catalog</span>
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
            <Label htmlFor="topic">Topic / niche</Label>
            <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} required />
          </div>
          <div>
            <Label htmlFor="count">How many channels</Label>
            <Input
              id="count"
              type="number"
              min={1}
              max={100}
              value={count}
              onChange={(e) => setCount(Number(e.target.value) || 1)}
            />
          </div>
          <div>
            <Label htmlFor="ctype">Channel type</Label>
            <select
              id="ctype"
              value={channelType}
              onChange={(e) => setChannelType(e.target.value as "new_only" | "all")}
              className={selectClass}
            >
              <option value="all">All</option>
              <option value="new_only">New only</option>
            </select>
          </div>
          <div>
            <Label htmlFor="min">Min subscribers</Label>
            <Input
              id="min"
              type="number"
              min={0}
              placeholder="optional"
              value={minSub}
              onChange={(e) => setMinSub(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="max">Max subscribers</Label>
            <Input
              id="max"
              type="number"
              min={0}
              placeholder="optional"
              value={maxSub}
              onChange={(e) => setMaxSub(e.target.value === "" ? "" : Number(e.target.value))}
            />
          </div>
          <div>
            <Label htmlFor="lang">Language</Label>
            <Input id="lang" placeholder="ru, en…" value={language} onChange={(e) => setLanguage(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="region">Region / country</Label>
            <Input id="region" placeholder="optional" value={region} onChange={(e) => setRegion(e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <Label htmlFor="extra">Extra conditions</Label>
            <Textarea id="extra" placeholder="Free-text constraints for the planner…" value={extra} onChange={(e) => setExtra(e.target.value)} />
          </div>
          <div className="sm:col-span-2">
            <Button type="submit" disabled={loading} className="w-full sm:w-auto">
              {loading ? <Spinner /> : <Search className="size-4" />}
              Find channels
            </Button>
          </div>
        </form>
      </Card>

      <ExportLinks />

      {error ? (
        <Alert variant="error" title="Search failed">
          {error}
        </Alert>
      ) : null}

      {data?.manual_review?.needs_review ? <ManualReviewBanner flags={data.manual_review} /> : null}

      {job ? (
        <Card>
          <CardTitle>Background job</CardTitle>
          <CardDescription>
            Конвейер обнаружения Telegram (оркестратор). Статус обновляется каждые ~1.5 с через{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs">GET /api/v1/orchestration/jobs/…</code>. В логах бэкенда
            ищите префикс <code className="rounded bg-zinc-100 px-1 text-xs">orchestration.</code> (этапы{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs">job_dequeued</code>,{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs">stage_begin</code> /{" "}
            <code className="rounded bg-zinc-100 px-1 text-xs">stage_end</code>).
          </CardDescription>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-sm text-zinc-700">
            {jobActive ? <Loader2 className="size-4 shrink-0 animate-spin text-violet-600" aria-hidden /> : null}
            <Badge tone={job.status === "failed" ? "warning" : "violet"}>{job.status}</Badge>
            <span className="font-mono text-xs text-zinc-600">{job.job_id}</span>
          </div>
          {job.stage_label ? (
            <p className="mt-2 text-sm font-medium text-violet-900">Этап: {job.stage_label}</p>
          ) : null}
          {job.detail ? (
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-600">{job.detail}</p>
          ) : null}
          {job.updated_at ? (
            <p className="mt-1 text-xs text-zinc-500">Обновлено: {new Date(job.updated_at).toLocaleString()}</p>
          ) : null}
          {jobActive ? (
            <p className="mt-2 text-sm text-violet-800">
              После завершения пайплайна каналы появятся в каталоге — затем снова запустите поиск в режиме «Saved
              catalog».
            </p>
          ) : null}
          {job.status === "completed" ? (
            <p className="mt-2 text-sm text-emerald-800">
              Задание в памяти сервера завершено. Сейчас пайплайн — MVP-заглушки; реальный Telethon→SQLite подключается
              в воркере по мере разработки.
            </p>
          ) : null}
        </Card>
      ) : null}

      {data?.normalized_filters && Object.keys(data.normalized_filters).length > 0 ? (
        <Card>
          <CardTitle>Normalized filters</CardTitle>
          <CardDescription>What the planner resolved from your request.</CardDescription>
          <pre className="mt-4 max-h-48 overflow-auto rounded-xl border border-zinc-200 bg-zinc-50 p-4 text-xs text-zinc-600">
            {JSON.stringify(data.normalized_filters, null, 2)}
          </pre>
        </Card>
      ) : null}

      {data?.channels?.length ? (
        <div className="space-y-3">
          <h2 className="text-lg font-medium text-zinc-900">Results ({data.channels.length})</h2>
          <p className="text-sm text-zinc-600">Click a row to open the channel card.</p>
          <ChannelSearchResultList channels={data.channels} />
        </div>
      ) : null}

      {data &&
      !data.channels.length &&
      !data.manual_review?.needs_review &&
      !data.background_job &&
      searchSource === "saved_catalog" ? (
        <p className="text-sm text-zinc-500">No channels matched. Try broadening the topic or relaxing filters.</p>
      ) : null}

      {data?.background_job && !data.channels.length ? (
        <p className="text-sm text-zinc-600">
          Channels will land in the saved catalog after the background pipeline finishes; run a{" "}
          <strong>saved catalog</strong> search again to open cards from the list.
        </p>
      ) : null}
    </div>
  );
}
