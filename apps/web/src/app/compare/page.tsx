"use client";

import { useMemo, useRef, useState } from "react";
import Link from "next/link";
import { ApiError, compareChannels, searchChannels } from "@/lib/api-client";
import type { ChannelCard, CompareChannelsResponse } from "@/lib/types/api";
import { ActivityBars } from "@/components/charts/activity-bars";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";

const selectClass =
  "w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20";

const SEARCH_BATCH = 30;
const VISIBLE_STEP = 20;

function channelLabel(ch: ChannelCard): string {
  const uname = ch.username ? `@${ch.username.replace(/^@/, "")}` : `#${ch.id}`;
  const subs = ch.subscriber_count?.toLocaleString() ?? "—";
  return `${uname} · ${subs} подписчиков`;
}

function renderInlineMarkdown(line: string) {
  const chunks = line.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return chunks.map((chunk, idx) => {
    if (/^\*\*[^*]+\*\*$/.test(chunk)) {
      return <strong key={idx}>{chunk.slice(2, -2)}</strong>;
    }
    if (/^\*[^*]+\*$/.test(chunk)) {
      return <em key={idx}>{chunk.slice(1, -1)}</em>;
    }
    return <span key={idx}>{chunk}</span>;
  });
}

function renderSimpleMarkdown(text: string) {
  const lines = text.split("\n");
  return (
    <div className="space-y-2 text-sm leading-relaxed text-zinc-700">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={idx} className="h-1" />;
        if (trimmed.startsWith("###")) {
          return (
            <p key={idx} className="text-base font-semibold text-zinc-900">
              {renderInlineMarkdown(trimmed.replace(/^###\s*/, ""))}
            </p>
          );
        }
        if (trimmed.startsWith("####")) {
          return (
            <p key={idx} className="text-sm font-semibold text-zinc-900">
              {renderInlineMarkdown(trimmed.replace(/^####\s*/, ""))}
            </p>
          );
        }
        return <p key={idx}>{renderInlineMarkdown(trimmed)}</p>;
      })}
    </div>
  );
}

export default function ComparePage() {
  const [topic, setTopic] = useState("");
  const [count, setCount] = useState(20);
  const [language, setLanguage] = useState("ru");
  const [region, setRegion] = useState("");
  const [usernameQuery, setUsernameQuery] = useState("");
  const [sortBy, setSortBy] = useState<"subscriber_count" | "last_sync_at">("subscriber_count");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [pickRows, setPickRows] = useState<ChannelCard[]>([]);
  const [visibleRows, setVisibleRows] = useState(VISIBLE_STEP);
  const [hasMorePickRows, setHasMorePickRows] = useState(true);
  const [pickLoading, setPickLoading] = useState(false);
  const [pickError, setPickError] = useState<string | null>(null);
  const [showPicker, setShowPicker] = useState(false);

  const [selectedChannels, setSelectedChannels] = useState<ChannelCard[]>([]);
  const [pickerWarning, setPickerWarning] = useState<string | null>(null);
  const [loadingCompare, setLoadingCompare] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CompareChannelsResponse | null>(null);
  const pickerListRef = useRef<HTMLDivElement | null>(null);
  const pickLoadLockRef = useRef(false);
  const pickLastLoadAtRef = useRef(0);

  const chartData = useMemo(() => {
    if (!data?.insights?.length) return [];
    return data.insights.map((r) => ({
      name: (r.username ? `@${r.username}` : `#${r.channel_id}`).slice(0, 14),
      value: r.metrics.normalized_score,
    }));
  }, [data]);

  const engagementData = useMemo(() => {
    if (!data?.insights?.length) return [];
    return data.insights.map((r) => ({
      name: (r.username ? `@${r.username}` : `#${r.channel_id}`).slice(0, 14),
      value: r.metrics.er_forward_rate_mean * 100,
    }));
  }, [data]);

  const frequencyData = useMemo(() => {
    if (!data?.insights?.length) return [];
    return data.insights.map((r) => ({
      name: (r.username ? `@${r.username}` : `#${r.channel_id}`).slice(0, 14),
      value: r.metrics.posting_frequency_per_week,
    }));
  }, [data]);

  const medianViewsData = useMemo(() => {
    if (!data?.insights?.length) return [];
    return data.insights.map((r) => ({
      name: (r.username ? `@${r.username}` : `#${r.channel_id}`).slice(0, 14),
      value: r.metrics.median_views,
    }));
  }, [data]);

  const historicalFreqByChannelId = useMemo(() => {
    const m = new Map<number, number | null>();
    for (const r of data?.rows ?? []) m.set(r.channel_id, r.posts_per_week_estimate ?? null);
    return m;
  }, [data]);

  async function loadBatch(offset: number, reset = false) {
    if (pickLoadLockRef.current) return;
    pickLoadLockRef.current = true;
    setPickLoading(true);
    setPickError(null);
    try {
      const res = await searchChannels({
        topic: topic.trim() || "__all__",
        count: SEARCH_BATCH,
        offset,
        min_subscribers: null,
        max_subscribers: null,
        channel_type: "all",
        language: language.trim() || null,
        region_country: region.trim() || null,
        username_query: usernameQuery.trim() || null,
        last_post_from: null,
        last_post_to: null,
        extra_conditions: null,
        sort_by: sortBy,
        sort_order: sortOrder,
        search_source: "saved_catalog",
      });
      setPickRows((prev) => {
        const base = reset ? [] : prev;
        const byId = new Map<number, ChannelCard>();
        for (const ch of base) byId.set(ch.id, ch);
        for (const ch of res.channels) byId.set(ch.id, ch);
        return Array.from(byId.values());
      });
      setHasMorePickRows(Boolean(res.has_more));
      pickLastLoadAtRef.current = Date.now();
    } catch (err) {
      setPickError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setPickLoading(false);
      pickLoadLockRef.current = false;
    }
  }

  async function onSearch(e: React.FormEvent) {
    e.preventDefault();
    setPickRows([]);
    setHasMorePickRows(true);
    setData(null);
    setVisibleRows(VISIBLE_STEP);
    setShowPicker(true);
    await loadBatch(0, true);
  }

  async function runCompare(channelIds: number[]) {
    if (channelIds.length < 2 || channelIds.length > 3) return;
    setLoadingCompare(true);
    setError(null);
    setData(null);
    try {
      const res = await compareChannels({ channel_ids: channelIds });
      setData(res);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoadingCompare(false);
    }
  }

  function toggleChannel(ch: ChannelCard) {
    setPickerWarning(null);
    setSelectedChannels((prev) => {
      const exists = prev.some((x) => x.id === ch.id);
      if (exists) return prev.filter((x) => x.id !== ch.id);
      if (prev.length >= 3) {
        setPickerWarning("Максимум каналов для сравнения — 3. Чтобы добавить другой, снимите выбор с одного из текущих.");
        return prev;
      }
      return [...prev, ch];
    });
  }

  function onPickerScroll() {
    const el = pickerListRef.current;
    if (!el) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 60;
    if (!nearBottom || pickLoading) return;
    if (visibleRows < pickRows.length) {
      setVisibleRows((v) => Math.min(v + VISIBLE_STEP, pickRows.length));
      return;
    }
    if (!hasMorePickRows) return;
    if (Date.now() - pickLastLoadAtRef.current < 500) return;
    void loadBatch(pickRows.length);
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Сравнение каналов</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Выберите от 2 до 3 каналов из списка. Сравнение запускается по кнопке.
        </p>
      </div>

      <Card>
        <CardTitle>Подбор каналов для сравнения</CardTitle>
        <CardDescription>
          Форма поиска аналогична каталогу каналов, тема необязательна.
        </CardDescription>
        <form onSubmit={onSearch} className="mt-4 grid gap-4 md:grid-cols-3">
          <div>
            <Label htmlFor="topic">Тема / ниша</Label>
            <Input id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="необязательно (если пусто — все темы)" />
          </div>
          <div>
            <Label htmlFor="count">Сколько каналов в выдаче</Label>
            <Input
              id="count"
              type="number"
              min={1}
              value={count}
              onChange={(e) => setCount(Math.max(1, Number(e.target.value) || 20))}
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
            <Input id="usernameQuery" value={usernameQuery} onChange={(e) => setUsernameQuery(e.target.value)} placeholder="@username" />
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
              <option value="desc">По убыванию</option>
              <option value="asc">По возрастанию</option>
            </select>
          </div>
          <div className="md:col-span-1 self-end">
            <Button type="submit" variant="secondary" disabled={pickLoading}>
              {pickLoading ? <Spinner /> : null}
              Выбрать каналы
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

        {pickerWarning ? (
          <div className="mt-4">
            <Alert variant="warning" title="Ограничение выбора">
              {pickerWarning}
            </Alert>
          </div>
        ) : null}

        <div className="mt-4">
          <p className="text-xs font-medium text-zinc-500">Выбрано для сравнения ({selectedChannels.length}/3)</p>
          <div className="mt-2 flex flex-wrap gap-2">
            {selectedChannels.map((ch) => (
              <button
                key={ch.id}
                type="button"
                className="rounded-lg border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs text-violet-900"
                onClick={() => toggleChannel(ch)}
              >
                {channelLabel(ch)} ×
              </button>
            ))}
            {selectedChannels.length === 0 ? <span className="text-xs text-zinc-500">Каналы пока не выбраны.</span> : null}
          </div>
          <div className="mt-3">
            <Button
              type="button"
              variant="secondary"
              disabled={selectedChannels.length === 0}
              onClick={() => {
                setSelectedChannels([]);
                setPickerWarning(null);
              }}
              className="border-zinc-400 text-zinc-800 disabled:border-zinc-200 disabled:text-zinc-400"
            >
              Очистить список выбранных каналов
            </Button>
          </div>
        </div>

        <div className="mt-4">
          <Button
            type="button"
            variant="primary"
            disabled={selectedChannels.length < 2 || selectedChannels.length > 3 || loadingCompare}
            onClick={() => void runCompare(selectedChannels.map((c) => c.id))}
            className={selectedChannels.length >= 2 && selectedChannels.length <= 3 ? "" : "opacity-60"}
          >
            {loadingCompare ? <Spinner /> : null}
            Сравнить выбранные каналы
          </Button>
          <p className="mt-2 text-xs text-zinc-500">
            Ограничение: от 2 до 3 каналов. Сравнение по окну 30 дней.
          </p>
        </div>
      </Card>

      {error ? (
        <Alert variant="error" title="Ошибка сравнения">
          {error}
        </Alert>
      ) : null}
      {loadingCompare ? (
        <div className="flex items-center gap-2 text-sm text-zinc-600">
          <Spinner />
          Сравнение выполняется...
        </div>
      ) : null}

      {data?.comparison_notes ? (
        <Card>
          <CardTitle>Сравнительный анализ</CardTitle>
          <CardDescription>
            Окно: {data.comparison_window_days} дней
            {data.generated_at
              ? ` · сформировано ${new Date(data.generated_at).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })}`
              : ""}
          </CardDescription>
          <div className="mt-4">{renderSimpleMarkdown(data.comparison_notes || "")}</div>
        </Card>
      ) : null}

      {data?.insights?.length ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardTitle>Итоговый рейтинг (0–100)</CardTitle>
            <CardDescription>Нормализованный рейтинг по динамике, вовлеченности и стабильности.</CardDescription>
            <div className="mt-4">
              <ActivityBars data={chartData} />
            </div>
          </Card>
          <Card>
            <CardTitle>Прокси вовлеченности (доля пересылок к просмотрам)</CardTitle>
            <CardDescription>Средняя доля пересылок к просмотрам в процентах за окно 30 дней.</CardDescription>
            <div className="mt-4">
              <ActivityBars data={engagementData} />
            </div>
          </Card>
          <Card>
            <CardTitle>Частота публикаций (постов в неделю)</CardTitle>
            <div className="mt-4">
              <ActivityBars data={frequencyData} />
            </div>
          </Card>
          <Card>
            <CardTitle>Медиана просмотров</CardTitle>
            <CardDescription>Медиана = центральное значение просмотров постов за 30 дней.</CardDescription>
            <div className="mt-4">
              <ActivityBars data={medianViewsData} />
            </div>
          </Card>
        </div>
      ) : null}

      {data?.insights?.length ? (
        <div className="grid gap-4">
          {data.insights.map((item) => (
            <Card key={item.channel_id}>
              <CardTitle>{item.username ? `@${item.username}` : `Канал #${item.channel_id}`}</CardTitle>
              <CardDescription>
                Рейтинг: {item.metrics.normalized_score.toFixed(1)} · Постов за 30 дней: {item.metrics.posts_in_window}
              </CardDescription>
              <div className="mt-4 grid gap-4 lg:grid-cols-3">
                <div>
                  <p className="text-xs font-medium text-zinc-500">Ключевые метрики</p>
                  <p className="mt-1 text-sm text-zinc-700">Частота: {item.metrics.posting_frequency_per_week.toFixed(2)} поста/нед</p>
                  <p className="text-sm text-zinc-700">
                    Историческая частота (каталог):{" "}
                    {historicalFreqByChannelId.get(item.channel_id) != null
                      ? `${Number(historicalFreqByChannelId.get(item.channel_id)).toFixed(1)} поста/нед`
                      : "—"}
                  </p>
                  <p className="text-xs text-zinc-500">
                    Историческая частота берется из ранее накопленного каталога и помогает увидеть долгосрочный ритм, а не только окно 30 дней.
                  </p>
                  <p className="text-sm text-zinc-700">Средние просмотры: {item.metrics.avg_views.toFixed(0)}</p>
                  <p className="text-sm text-zinc-700">Медиана просмотров: {item.metrics.median_views.toFixed(0)}</p>
                  <p className="text-sm text-zinc-700">75-й перцентиль просмотров: {item.metrics.p75_views.toFixed(0)}</p>
                  <p className="text-sm text-zinc-700">
                    Доля пересылок к просмотрам (средняя / P75): {(item.metrics.er_forward_rate_mean * 100).toFixed(2)}% /{" "}
                    {(item.metrics.er_forward_rate_p75 * 100).toFixed(2)}%
                  </p>
                  <p className="text-sm text-zinc-700">Стабильность: {item.metrics.weekly_stability_score.toFixed(1)} · Тон: {item.metrics.tone_label}</p>
                </div>
                <div>
                  <p className="text-xs font-medium text-zinc-500">Сильные стороны</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-zinc-700">
                    {item.strengths.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-xs font-medium text-zinc-500">Рекомендации</p>
                  <ul className="mt-1 list-inside list-disc text-sm text-zinc-700">
                    {item.recommendations.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
              </div>
              {item.evidence_urls.length ? (
                <div className="mt-4">
                  <p className="text-xs font-medium text-zinc-500">Источники (посты)</p>
                  <div className="mt-1 flex flex-wrap gap-2">
                    {item.evidence_urls.slice(0, 3).map((u) => (
                      <a key={u} href={u} target="_blank" rel="noreferrer" className="text-xs text-violet-700 hover:text-violet-600">
                        Открыть источник
                      </a>
                    ))}
                  </div>
                </div>
              ) : null}
            </Card>
          ))}
        </div>
      ) : null}

      <Card>
        <CardTitle>Пояснение терминов</CardTitle>
        <div className="mt-3 space-y-1 text-sm text-zinc-700">
          <p>Рейтинг: итоговая нормализованная оценка канала по выбранным метрикам (0–100).</p>
          <p>Историческая частота: оценка публикаций в неделю по накопленным данным каталога (вне текущего окна 30 дней).</p>
          <p>Медиана (P50): центральное значение, половина постов выше, половина ниже.</p>
          <p>P75 (75-й перцентиль): уровень, выше которого только 25% постов.</p>
          <p>Доля пересылок к просмотрам: прокси вовлеченности аудитории по реакции на посты.</p>
        </div>
      </Card>

      {data?.rows?.length ? (
        <Card>
          <CardTitle>Таблица каналов</CardTitle>
          <div className="mt-4 overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                  <th className="pb-2 pr-3">Канал</th>
                  <th className="pb-2 pr-3">Подписчики</th>
                  <th className="pb-2 pr-3">Историч. постов/нед</th>
                  <th className="pb-2">Тема</th>
                </tr>
              </thead>
              <tbody className="text-zinc-800">
                {data.rows.map((r) => (
                  <tr key={r.channel_id} className="border-b border-zinc-200">
                    <td className="py-2 pr-3">
                      <Link className="font-medium text-violet-700 hover:text-violet-600" href={`/channels/${r.channel_id}`}>
                        {r.title ?? r.username ?? r.channel_id}
                      </Link>
                      <div className="text-xs text-zinc-500">{r.username ? `@${r.username}` : null}</div>
                    </td>
                    <td className="py-2 pr-3">{r.subscriber_count?.toLocaleString() ?? "—"}</td>
                    <td className="py-2 pr-3">{r.posts_per_week_estimate?.toFixed(1) ?? "—"}</td>
                    <td className="py-2">{r.primary_topic ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {showPicker ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <Card className="max-h-[85vh] w-full max-w-2xl overflow-hidden">
            <div className="flex items-start justify-between gap-3 border-b border-zinc-100 pb-3">
              <div>
                <CardTitle>Выбор каналов</CardTitle>
                <CardDescription>Листайте вниз: список подгружается чанками по {SEARCH_BATCH} каналов.</CardDescription>
              </div>
              <Button variant="ghost" onClick={() => setShowPicker(false)} aria-label="Закрыть">
                Закрыть
              </Button>
            </div>
            <div
              ref={pickerListRef}
              onScroll={onPickerScroll}
              className="mt-3 max-h-[60vh] space-y-2 overflow-y-auto pr-1"
            >
              {pickRows.slice(0, visibleRows).map((ch) => {
                const checked = selectedChannels.some((x) => x.id === ch.id);
                const keyword = ch.topic_search || ch.primary_topic || "—";
                return (
                  <label
                    key={ch.id}
                    className="flex cursor-pointer items-center justify-between gap-3 rounded-xl border border-zinc-200 p-3"
                  >
                    <span className="text-sm text-zinc-700">
                      {channelLabel(ch)}
                      <span className="block text-xs text-zinc-500">Ключевое слово: {keyword}</span>
                    </span>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleChannel(ch)}
                      className="size-4 accent-violet-600"
                    />
                  </label>
                );
              })}
              {pickLoading ? (
                <div className="flex justify-center py-3">
                  <Spinner />
                </div>
              ) : null}
              {!pickLoading && !hasMorePickRows && pickRows.length > 0 ? (
                <p className="py-2 text-center text-xs text-zinc-500">Достигнут конец списка по текущим фильтрам.</p>
              ) : null}
            </div>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
