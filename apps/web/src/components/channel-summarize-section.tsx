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
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card>
      <CardTitle>Recent posts summary</CardTitle>
      <CardDescription>Scenario 3 — LLM digest of the latest posts.</CardDescription>
      <form onSubmit={onSubmit} className="mt-4 space-y-4">
        <div>
          <Label htmlFor="post_limit">Posts to include</Label>
          <Input
            id="post_limit"
            type="number"
            min={1}
            max={50}
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value) || 1)}
          />
        </div>
        <Button type="submit" disabled={loading}>
          {loading ? <Spinner /> : null}
          Generate summary
        </Button>
      </form>
      {error ? (
        <div className="mt-4">
          <Alert variant="error" title="Summary failed">
            {error}
          </Alert>
        </div>
      ) : null}
      {summary ? (
        <div className="mt-4 rounded-xl border border-zinc-200 bg-zinc-50 p-4">
          <p className="text-sm leading-relaxed text-zinc-800 whitespace-pre-wrap">{summary}</p>
          {hint ? <p className="mt-3 text-xs text-zinc-500">{hint}</p> : null}
        </div>
      ) : null}
    </Card>
  );
}
