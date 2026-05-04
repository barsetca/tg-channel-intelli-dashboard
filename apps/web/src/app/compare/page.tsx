"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { GitCompareArrows } from "lucide-react";
import { ApiError, compareChannels } from "@/lib/api-client";
import type { CompareChannelsResponse } from "@/lib/types/api";
import { ActivityBars } from "@/components/charts/activity-bars";
import { Button } from "@/components/ui/button";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Spinner } from "@/components/ui/spinner";
import { Alert } from "@/components/ui/alert";

function parseIds(raw: string): number[] {
  return raw
    .split(/[\s,;]+/)
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n));
}

export default function ComparePage() {
  const [rawIds, setRawIds] = useState("1 2 3");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<CompareChannelsResponse | null>(null);

  const chartData = useMemo(() => {
    if (!data?.rows?.length) return [];
    return data.rows.map((r) => ({
      name: (r.username ? `@${r.username}` : r.title)?.slice(0, 12) ?? `#${r.channel_id}`,
      value: Math.min(100, Math.log10((r.subscriber_count ?? 100) + 10) * 14),
    }));
  }, [data]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const channel_ids = parseIds(rawIds);
    if (channel_ids.length < 2) {
      setError("Enter at least two numeric channel ids.");
      setData(null);
      return;
    }
    if (channel_ids.length > 5) {
      setError("Compare at most five channels (Scenario 5).");
      setData(null);
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const res = await compareChannels({ channel_ids });
      setData(res);
    } catch (err) {
      setError(err instanceof ApiError ? `${err.status}: ${err.message}` : "Request failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Compare channels</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Scenario 5 — side-by-side metrics and AI comparison notes. Enter 2–5 internal channel ids (from search cards).
        </p>
      </div>

      <Card>
        <CardTitle>Channel ids</CardTitle>
        <CardDescription>Space or comma separated, e.g. <code className="text-zinc-500">101 204 310</code></CardDescription>
        <form onSubmit={onSubmit} className="mt-4 space-y-4">
          <div>
            <Label htmlFor="ids">Ids</Label>
            <Input id="ids" value={rawIds} onChange={(e) => setRawIds(e.target.value)} />
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner /> : <GitCompareArrows className="size-4" />}
            Compare
          </Button>
        </form>
      </Card>

      {error ? (
        <Alert variant="error" title="Compare failed">
          {error}
        </Alert>
      ) : null}

      {data?.comparison_notes ? (
        <Card>
          <CardTitle>AI comparison notes</CardTitle>
          <CardDescription>Narrative summary from the orchestration layer.</CardDescription>
          <p className="mt-4 text-sm leading-relaxed text-zinc-700 whitespace-pre-wrap">{data.comparison_notes}</p>
        </Card>
      ) : null}

      {data?.rows?.length ? (
        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardTitle>Reach (log-scaled)</CardTitle>
            <CardDescription>Quick visual — pair with the table for decisions.</CardDescription>
            <div className="mt-4">
              <ActivityBars data={chartData} />
            </div>
          </Card>
          <Card>
            <CardTitle>Comparison table</CardTitle>
            <div className="mt-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 text-xs uppercase text-zinc-500">
                    <th className="pb-2 pr-3">Channel</th>
                    <th className="pb-2 pr-3">Subs</th>
                    <th className="pb-2 pr-3">Posts/wk</th>
                    <th className="pb-2">Topic</th>
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
        </div>
      ) : null}
    </div>
  );
}
