"use client";

import { useState } from "react";
import { Layers } from "lucide-react";
import { ApiError, semanticSearch } from "@/lib/api-client";
import type { SemanticSearchResponse } from "@/lib/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";

const modeLabel: Record<NonNullable<SemanticSearchResponse["mode"]>, string> = {
  post_search: "Поиск постов",
  channel_search: "Поиск каналов",
  question_answering_over_posts: "Ответ на вопрос по постам",
};

export default function SemanticSearchPage() {
  const [query, setQuery] = useState("Какие каналы часто пишут про инвестиции в недвижимость?");
  const [limit, setLimit] = useState(12);
  const [channelUsername, setChannelUsername] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<SemanticSearchResponse | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await semanticSearch({
        query: query.trim(),
        limit,
        channel_username: channelUsername.trim() ? channelUsername.trim().replace(/^@/, "") : null,
      });
      setData(res);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Семантический поиск</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Поиск работает по накопленным данным из сводок постов и каналов. Если запрос слишком общий или неоднозначный,
          система попросит уточнение и не будет строить недостоверный ответ.
        </p>
      </div>

      <Card>
        <CardTitle>Вопрос</CardTitle>
        <CardDescription>Введите запрос в свободной форме: система сама выберет режим поиска.</CardDescription>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <Label htmlFor="q">Что нужно найти</Label>
            <Input id="q" value={query} onChange={(e) => setQuery(e.target.value)} required />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="lim">Количество результатов</Label>
              <Input
                id="lim"
                type="number"
                min={1}
                max={30}
                value={limit}
                onChange={(e) => setLimit(Math.max(1, Math.min(30, Number(e.target.value) || 12)))}
              />
            </div>
            <div>
              <Label htmlFor="cun">Username канала (необязательно)</Label>
              <Input
                id="cun"
                placeholder="@channel_username"
                value={channelUsername}
                onChange={(e) => setChannelUsername(e.target.value)}
              />
            </div>
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner /> : <Layers className="size-4" />}
            Выполнить поиск
          </Button>
        </form>
      </Card>

      {error ? (
        <Alert variant="error" title="Ошибка поиска">
          {error}
        </Alert>
      ) : null}

      {data?.needs_review ? (
        <Alert variant="warning" title="Нужна уточняющая формулировка">
          {data.reason ?? "Недостаточно данных для надёжного поиска"}
        </Alert>
      ) : null}

      {data?.answer ? (
        <Alert
          variant="info"
          title={`Режим: ${data.mode ? modeLabel[data.mode] : "—"}`}
        >
          {data.answer}
        </Alert>
      ) : null}

      {data?.synthesis_placeholder ? (
        <Alert variant="info" title="Контекст из оконных сводок">
          {data.synthesis_placeholder}
        </Alert>
      ) : null}

      {data?.mode === "channel_search" && data?.results?.length ? (
        <div className="space-y-3">
          <h2 className="text-lg font-medium text-zinc-900">Результаты ({data.results.length})</h2>
          {data.mode === "channel_search" ? (
            <p className="text-sm text-zinc-600">
              Каналы семантически близкие к запросу по теме и формулировкам, имеющие релевантные посты.
            </p>
          ) : null}
          <ul className="space-y-3">
            {data.results.map((item, idx) => (
              <li key={`${item.channel_username}-${item.source_url}-${idx}`}>
                <Card className="py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {item.channel_username ? <Badge tone="violet">@{item.channel_username.replace(/^@/, "")}</Badge> : null}
                    {item.score != null ? <span className="text-xs text-zinc-500">score {item.score.toFixed(3)}</span> : null}
                  </div>
                  <p className="mt-2 text-sm font-medium text-zinc-900">{item.title ?? "Результат поиска"}</p>
                  {item.relevance_reason ? <p className="mt-1 text-sm text-zinc-700">{item.relevance_reason}</p> : null}
                  {item.source_url ? (
                    <a className="mt-2 inline-block text-xs text-violet-700 hover:text-violet-600" href={item.source_url} target="_blank" rel="noreferrer">
                      Открыть источник
                    </a>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {data?.hits?.length ? (
        <div className="space-y-3">
          <h2 className="text-lg font-medium text-zinc-900">Найденные фрагменты ({data.hits.length})</h2>
          <ul className="space-y-3">
            {data.hits.map((hit) => (
              <li key={hit.point_id}>
                <Card className="py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {hit.content_type ? <Badge tone="violet">{hit.content_type}</Badge> : null}
                    {hit.channel_username ? (
                      <Badge tone="neutral">@{hit.channel_username.replace(/^@/, "")}</Badge>
                    ) : null}
                    {hit.score != null ? (
                      <span className="text-xs text-zinc-500">score {hit.score.toFixed(3)}</span>
                    ) : null}
                    {hit.published_at ? (
                      <span className="text-xs text-zinc-500">
                        {new Date(hit.published_at).toLocaleString(undefined, {
                          dateStyle: "medium",
                          timeStyle: "short",
                        })}
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-2 text-sm text-zinc-700">{hit.text_preview ?? "—"}</p>
                  {hit.source_url ? (
                    <a
                      className="mt-2 inline-block text-xs text-violet-700 hover:text-violet-600"
                      href={hit.source_url}
                      target="_blank"
                      rel="noreferrer"
                    >
                      Открыть пост
                    </a>
                  ) : null}
                </Card>
              </li>
            ))}
          </ul>
        </div>
      ) : data && !data.needs_review && !data.results.length && !data.hits.length ? (
        <p className="text-sm text-zinc-500">Совпадения не найдены. Уточните запрос или снимите ограничение по username.</p>
      ) : null}
    </div>
  );
}
