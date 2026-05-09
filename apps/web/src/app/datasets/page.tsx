"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, CheckCircle2, Database, Loader2, Plus, RefreshCw, Trash2, X } from "lucide-react";
import {
  ApiError,
  fetchOrchestrationJobStatus,
  collectDatasetChannel,
  createDatasetChannel,
  deleteChannel,
  listDatasets,
} from "@/lib/api-client";
import type { ChannelCreateResult, ChannelDatasetItem } from "@/lib/types/api";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

export default function DatasetsPage() {
  const [rows, setRows] = useState<ChannelDatasetItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const limit = 20;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  const [collectOpen, setCollectOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [collectRef, setCollectRef] = useState("");
  const [collectTopic, setCollectTopic] = useState("");
  const [collectExtra, setCollectExtra] = useState("");
  const [createRef, setCreateRef] = useState("");
  const [createTopic, setCreateTopic] = useState("");
  const [createExtra, setCreateExtra] = useState("");
  const [showCreateResultModal, setShowCreateResultModal] = useState(false);
  const [createResult, setCreateResult] = useState<ChannelCreateResult | null>(null);
  const [showCreateErrorModal, setShowCreateErrorModal] = useState(false);
  const [createErrorText, setCreateErrorText] = useState("");
  const [showNeedsReviewModal, setShowNeedsReviewModal] = useState(false);
  const [reviewReason, setReviewReason] = useState("");
  const [reviewHints, setReviewHints] = useState<string[]>([]);
  const [showJobModal, setShowJobModal] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<"queued" | "running" | "completed" | "failed" | null>(null);
  const [jobDetail, setJobDetail] = useState("");
  const [jobStageLabel, setJobStageLabel] = useState<string | null>(null);

  const selected = useMemo(() => rows.find((r) => r.id === selectedId) ?? null, [rows, selectedId]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listDatasets(limit, offset);
      setRows(res.items);
      setTotal(res.total);
      if (selectedId != null && !res.items.some((i) => i.id === selectedId)) {
        setSelectedId(null);
      }
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : "Не удалось загрузить наборы данных");
    } finally {
      setLoading(false);
    }
  }, [limit, offset, selectedId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!jobId || (jobStatus !== "queued" && jobStatus !== "running")) return;
    const currentJobId = jobId;
    let cancelled = false;
    async function poll() {
      try {
        const st = await fetchOrchestrationJobStatus(currentJobId);
        if (cancelled) return;
        setJobStatus(st.status);
        setJobDetail(st.detail);
        setJobStageLabel(st.stage_label);
      } catch (e) {
        if (cancelled) return;
        setJobStatus("failed");
        setJobDetail(e instanceof ApiError ? `${e.status}: ${e.message}` : "Не удалось получить статус фоновой задачи.");
      }
    }
    void poll();
    const id = setInterval(() => void poll(), 1500);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [jobId, jobStatus]);

  function openCollect() {
    if (!selected) return;
    setCollectRef(selected.username ? `@${selected.username}` : "");
    setCollectTopic(selected.topic_search || "");
    setCollectExtra(selected.extra_conditions || "");
    setCollectOpen(true);
  }

  async function onCollectSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!selected) return;
    try {
      const out = await collectDatasetChannel(selected.id, {
        channel_ref: collectRef.trim() || null,
        topic: collectTopic.trim() || null,
        extra_conditions: collectExtra,
      });
      setError(null);
      setCollectOpen(false);
      await load();
      if (out.needs_review) {
        setReviewReason(out.reason ?? "Нужна ручная проверка запроса");
        setReviewHints(out.hints ?? []);
        setShowNeedsReviewModal(true);
        return;
      }
      if (out.background_job_id) {
        setJobId(out.background_job_id);
        setJobStatus("queued");
        setJobDetail("Задача поставлена в очередь.");
        setJobStageLabel(null);
        setShowJobModal(true);
      }
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : "Не удалось запустить сбор");
    }
  }

  async function onCreateSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      const created = await createDatasetChannel({
        channel_ref: createRef.trim(),
        topic_search: createTopic.trim() || null,
        extra_conditions: createExtra.trim() || null,
      });
      setCreateOpen(false);
      setCreateRef("");
      setCreateTopic("");
      setCreateExtra("");
      await load();
      setSelectedId(created.id);
      setCreateResult(created);
      setShowCreateResultModal(true);
    } catch (e) {
      setCreateOpen(false);
      setCreateErrorText(e instanceof ApiError ? `${e.status}: ${e.message}` : "Не удалось создать канал");
      setShowCreateErrorModal(true);
    }
  }

  async function onDeleteSelected() {
    if (!selected) return;
    if (!confirm("Удалить выбранный канал из наборов данных?")) return;
    try {
      await deleteChannel(selected.id);
      setSelectedId(null);
      await load();
    } catch (e) {
      setError(e instanceof ApiError ? `${e.status}: ${e.message}` : "Не удалось удалить канал");
    }
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Наборы данных</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Таблица сохранённых каналов (dataset≈channel). Расширенные сценарии остаются в разделе{" "}
          <Link href="/search" className="text-violet-700 underline">
            Поиск каналов
          </Link>
          .
        </p>
      </div>

      {error ? (
        <Alert variant="error" title="Ошибка">
          {error}
        </Alert>
      ) : null}

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <Database className="size-5 text-violet-700" />
            <CardTitle>Список каналов</CardTitle>
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setCreateOpen(true)}>
              <Plus className="size-4" />
              Создать канал
            </Button>
            <Button variant="ghost" onClick={() => void load()} disabled={loading}>
              <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
              Обновить
            </Button>
          </div>
        </div>
        <CardDescription>
          Сортировка: по `created_at` от свежих к старым. Выберите один канал для действий.
        </CardDescription>

        <div className="mt-4 overflow-hidden rounded-xl border border-zinc-200">
          <table className="min-w-full divide-y divide-zinc-200 text-sm">
            <thead className="bg-zinc-50 text-xs uppercase text-zinc-600">
              <tr>
                <th className="px-3 py-2 text-left">Выбор</th>
                <th className="px-3 py-2 text-left">channel_id</th>
                <th className="px-3 py-2 text-left">channel_name</th>
                <th className="px-3 py-2 text-left">source</th>
                <th className="px-3 py-2 text-left">created_at</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100">
              {rows.map((r) => {
                const selectedRow = selectedId === r.id;
                const rowClass =
                  r.sync_status === "draft"
                    ? "bg-rose-50"
                    : selectedRow
                      ? "bg-emerald-50"
                      : "bg-white";
                return (
                  <tr key={r.id} className={rowClass}>
                    <td className="px-3 py-2">
                      <input
                        type="checkbox"
                        checked={selectedRow}
                        onChange={(e) => setSelectedId(e.target.checked ? r.id : null)}
                      />
                    </td>
                    <td className="px-3 py-2">{r.id}</td>
                    <td className="px-3 py-2">
                      <div className="font-medium text-zinc-900">{r.title || (r.username ? `@${r.username}` : "—")}</div>
                      <div className="text-xs text-zinc-500">{r.username ? `@${r.username}` : "без username"}</div>
                    </td>
                    <td className="px-3 py-2">
                      <Badge tone={r.sync_status === "draft" ? "warning" : "success"}>
                        {r.sync_status === "draft" ? "draft" : "telegram"}
                      </Badge>
                    </td>
                    <td className="px-3 py-2">{formatDate(r.created_at)}</td>
                  </tr>
                );
              })}
              {!rows.length ? (
                <tr>
                  <td colSpan={5} className="px-3 py-8 text-center text-zinc-500">
                    Нет сохранённых каналов.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
          <div className="text-sm text-zinc-600">
            Показано {rows.length} из {total}
          </div>
          <div className="flex gap-2">
            <Button variant="secondary" onClick={() => setOffset(Math.max(0, offset - limit))} disabled={offset === 0}>
              Назад
            </Button>
            <Button variant="secondary" onClick={() => setOffset(offset + limit)} disabled={offset + limit >= total}>
              Далее
            </Button>
          </div>
        </div>
      </Card>

      <Card>
        <CardTitle>Действия</CardTitle>
        <CardDescription>
          После выбора строки доступны: Собрать, Удалить, Очистить выбор. Выбор только одного канала.
        </CardDescription>
        <div className="mt-4 flex flex-wrap gap-2">
          <Button onClick={openCollect} disabled={!selected}>
            <CheckCircle2 className="size-4" />
            Собрать
          </Button>
          <Button variant="secondary" onClick={onDeleteSelected} disabled={!selected}>
            <Trash2 className="size-4" />
            Удалить
          </Button>
          <Button variant="ghost" onClick={() => setSelectedId(null)} disabled={!selected}>
            <X className="size-4" />
            Очистить выбор
          </Button>
        </div>
      </Card>

      {collectOpen ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-xl">
            <div className="mb-3 flex items-center justify-between">
              <CardTitle>Собрать канал</CardTitle>
              <Button variant="ghost" onClick={() => setCollectOpen(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <form className="space-y-3" onSubmit={onCollectSubmit}>
              <div>
                <Label>Username или ссылка</Label>
                <Input value={collectRef} onChange={(e) => setCollectRef(e.target.value)} />
              </div>
              <div>
                <Label>Тема канала</Label>
                <Input value={collectTopic} onChange={(e) => setCollectTopic(e.target.value)} />
              </div>
              <div>
                <Label>Дополнительные условия</Label>
                <Textarea value={collectExtra} onChange={(e) => setCollectExtra(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <Button type="submit">Отправить</Button>
              </div>
            </form>
          </Card>
        </div>
      ) : null}

      {createOpen ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-xl">
            <div className="mb-3 flex items-center justify-between">
              <CardTitle>Создать канал</CardTitle>
              <Button variant="ghost" onClick={() => setCreateOpen(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <form className="space-y-3" onSubmit={onCreateSubmit}>
              <div>
                <Label>Username или ссылка *</Label>
                <Input value={createRef} onChange={(e) => setCreateRef(e.target.value)} required />
              </div>
              <div>
                <Label>Тема канала</Label>
                <Input value={createTopic} onChange={(e) => setCreateTopic(e.target.value)} />
              </div>
              <div>
                <Label>Дополнительные условия</Label>
                <Textarea value={createExtra} onChange={(e) => setCreateExtra(e.target.value)} />
              </div>
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-2 text-xs text-amber-900">
                Новый канал добавляется как draft (красная строка), пока не выполнен успешный сбор.
              </div>
              <Button type="submit" disabled={!createRef.trim()}>
                Создать
              </Button>
            </form>
          </Card>
        </div>
      ) : null}

      {showCreateResultModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-xl">
            <div className="mb-2 flex items-start justify-between gap-2">
              <CardTitle>{createResult?.already_exists ? "Канал уже существует" : "Канал создан"}</CardTitle>
              <Button variant="ghost" onClick={() => setShowCreateResultModal(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <CardDescription>
              {createResult?.message ??
                "Канал добавлен в базу как draft: данные ещё не собраны и доступность не подтверждена."}
            </CardDescription>
            {!createResult?.already_exists ? (
              <p className="mt-3 text-sm text-zinc-800">Собрать канал сейчас?</p>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              {!createResult?.already_exists ? (
                <Button
                  onClick={() => {
                    setShowCreateResultModal(false);
                    openCollect();
                  }}
                  disabled={!selected}
                >
                  Собрать
                </Button>
              ) : null}
              {!createResult?.already_exists ? (
                <Button variant="secondary" onClick={onDeleteSelected} disabled={!selected}>
                  Удалить
                </Button>
              ) : null}
              <Button variant="ghost" onClick={() => setShowCreateResultModal(false)}>
                Показать в списке каналов
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {showNeedsReviewModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-xl">
            <div className="mb-2 flex items-start justify-between gap-2">
              <CardTitle>Нужна ручная проверка</CardTitle>
              <Button variant="ghost" onClick={() => setShowNeedsReviewModal(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <p className="text-sm text-zinc-800">{reviewReason}</p>
            {reviewHints.length ? (
              <ul className="mt-3 list-inside list-disc space-y-1 text-sm text-zinc-700">
                {reviewHints.map((h) => (
                  <li key={h}>{h}</li>
                ))}
              </ul>
            ) : null}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button
                onClick={() => {
                  setShowNeedsReviewModal(false);
                  setCollectOpen(true);
                }}
              >
                Повторить создание канала
              </Button>
              <Link href="/manual-review" className="inline-flex items-center rounded-xl border border-zinc-300 px-3 py-2 text-sm text-zinc-800">
                Перейти в меню «Требует проверки»
              </Link>
              <Button variant="secondary" onClick={onDeleteSelected} disabled={!selected}>
                Удалить канал
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {showCreateErrorModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-xl">
            <div className="mb-2 flex items-start justify-between gap-2">
              <CardTitle>Ошибка создания канала</CardTitle>
              <Button variant="ghost" onClick={() => setShowCreateErrorModal(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <CardDescription>{createErrorText}</CardDescription>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setShowCreateErrorModal(false)}>
                Понятно
              </Button>
              <Button
                onClick={() => {
                  setShowCreateErrorModal(false);
                  setCreateOpen(true);
                }}
              >
                Попробовать ещё раз
              </Button>
            </div>
          </Card>
        </div>
      ) : null}

      {showJobModal ? (
        <div className="fixed inset-0 z-30 flex items-center justify-center bg-black/30 p-4">
          <Card className="w-full max-w-2xl">
            <div className="mb-2 flex items-start justify-between gap-2">
              <CardTitle>Фоновая задача</CardTitle>
              <Button variant="ghost" onClick={() => setShowJobModal(false)}>
                <X className="size-4" />
              </Button>
            </div>
            <div className="flex items-center gap-2 text-sm text-zinc-700">
              {jobStatus === "queued" || jobStatus === "running" ? <Loader2 className="size-4 animate-spin text-violet-600" /> : null}
              <Badge tone={jobStatus === "failed" ? "warning" : "violet"}>{jobStatus ?? "queued"}</Badge>
              {jobId ? <span className="text-xs text-zinc-500">job_id: {jobId}</span> : null}
            </div>
            {jobStageLabel ? <p className="mt-2 text-sm text-zinc-700">Этап: {jobStageLabel}</p> : null}
            {jobDetail ? <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-600">{jobDetail}</p> : null}
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => setShowJobModal(false)}>
                Показать в списке каналов
              </Button>
              <Link href="/showcase" className="inline-flex items-center rounded-xl border border-zinc-300 px-3 py-2 text-sm text-zinc-800">
                Открыть витрину данных
              </Link>
            </div>
          </Card>
        </div>
      ) : null}

      <div className="rounded-xl border border-zinc-200 bg-white p-4 text-sm text-zinc-700">
        <div className="mb-1 flex items-center gap-2 font-medium">
          <AlertCircle className="size-4 text-violet-700" />
          Подсказка
        </div>
        Для расширенных режимов массового выбора и Telegram live используйте раздел <Link href="/search" className="text-violet-700 underline">Поиск каналов</Link>.
      </div>
    </div>
  );
}
