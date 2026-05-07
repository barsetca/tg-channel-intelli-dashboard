"use client";

import { useState } from "react";
import { ApiError, summarizeChannel } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";

export function ChannelSummarizeSection({ channelId }: { channelId: number }) {
  const [limit, setLimit] = useState(5);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSummary(null);
    setHint(null);
    try {
      const res = await summarizeChannel(channelId, { post_limit: limit });
      setSummary(res.summary);
      setHint(res.stored_analysis_hint);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Ошибка запроса");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardTitle>Резюме последних постов</CardTitle>
      <CardDescription>
        Этот блок делает краткую сводку по последним постам канала: выделяет ключевые темы, смысловые акценты и общий
        контекст публикаций.
      </CardDescription>
      <form onSubmit={onSubmit} className="mt-4 space-y-4">
        <div>
          <Label htmlFor="post_limit">Сколько постов включить в резюме</Label>
          <Input
            id="post_limit"
            type="number"
            min={3}
            max={20}
            value={limit}
            onChange={(e) => setLimit(Math.max(3, Math.min(20, Number(e.target.value) || 5)))}
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? <Spinner /> : null}
          Сформировать резюме
        </Button>
      </form>
      {error ? (
        <div className="mt-4">
          <Alert variant="error" title="Ошибка формирования резюме">
            {error}
          </Alert>
        </div>
      ) : null}
      {summary ? (
        <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-zinc-800">{summary}</p>
          {hint ? <p className="mt-3 text-xs text-zinc-500">{hint}</p> : null}
        </div>
      ) : null}
    </Card>
  );
}
