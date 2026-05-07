"use client";

import { useMemo, useState } from "react";
import { analyzeChannel, ApiError } from "@/lib/api-client";
import type { AnalyzeChannelResponse, ChannelDetail } from "@/lib/types/api";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";
import { ActivityBars } from "@/components/charts/activity-bars";
import { TrendArea } from "@/components/charts/trend-area";
import { AnalysisReportView } from "@/components/channel-analysis-report-view";

export function ChannelAnalyzePanel({ channel }: { channel: ChannelDetail }) {
  const [intent, setIntent] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<AnalyzeChannelResponse | null>(null);

  const stubBars = useMemo(
    () => [
      { name: "Cadence", value: Math.min(100, (channel.posts_per_week_estimate ?? 2) * 8) },
      { name: "Reach", value: Math.min(100, Math.log10((channel.subscriber_count ?? 100) + 10) * 18) },
      { name: "Freshness", value: channel.last_post_at ? 72 : 20 },
    ],
    [channel],
  );

  const stubTrend = useMemo(() => {
    const base = channel.posts_per_week_estimate ?? 3;
    return ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"].map((t, i) => ({
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
      const res = await analyzeChannel(channel.id, intent.trim() || undefined);
      setResult(res);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardTitle>Run deep analysis</CardTitle>
        <CardDescription>Scenario 2 — triggers backend analysis job; charts below illustrate channel rhythm.</CardDescription>
        <form onSubmit={onAnalyze} className="mt-4 space-y-4">
          <div>
            <Label htmlFor="intent">Optional focus / user intent</Label>
            <Textarea
              id="intent"
              placeholder="e.g. Compare tone vs competitors, assess ad-readiness…"
              value={intent}
              onChange={(e) => setIntent(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner /> : null}
            Analyze channel
          </Button>
        </form>
        {error ? (
          <div className="mt-4">
            <Alert variant="error" title="Analysis failed">
              {error}
            </Alert>
          </div>
        ) : null}
        {result ? (
          <div className="mt-4 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-950">
            <p>
              <span className="text-zinc-500">Analysis #</span> {result.analysis_id}{" "}
              <span className="text-zinc-500">· Status:</span> {result.status}
            </p>
            <p className="mt-2 text-zinc-700">{result.message}</p>
            {result.report ? <AnalysisReportView report={result.report} /> : null}
          </div>
        ) : null}
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardTitle>Engagement mix (illustrative)</CardTitle>
          <CardDescription>Normalized view from public metadata — full report comes from the analysis job.</CardDescription>
          <div className="mt-4">
            <ActivityBars data={stubBars} />
          </div>
        </Card>
        <Card>
          <CardTitle>Posting rhythm (stub)</CardTitle>
          <CardDescription>Weekly pattern placeholder until historical series is wired.</CardDescription>
          <div className="mt-4">
            <TrendArea data={stubTrend} />
          </div>
        </Card>
      </div>
    </div>
  );
}
