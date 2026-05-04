"use client";

import { useState } from "react";
import Link from "next/link";
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

export default function SemanticSearchPage() {
  const [query, setQuery] = useState("Which channels discuss real-estate investing?");
  const [limit, setLimit] = useState(12);
  const [channelId, setChannelId] = useState("");
  const [contentType, setContentType] = useState<"post" | "summary" | "profile" | "">("");

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
        channel_id: channelId.trim() ? Number(channelId) : null,
        content_type: contentType || null,
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
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Semantic search</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Scenario 4 — meaning-first retrieval over embedded posts and profiles. Synthesis placeholder surfaces when the
          backend wires LLM output.
        </p>
      </div>

      <Card>
        <CardTitle>Query</CardTitle>
        <CardDescription>Natural-language question over your vector index.</CardDescription>
        <form onSubmit={onSubmit} className="mt-6 space-y-4">
          <div>
            <Label htmlFor="q">Question</Label>
            <Input id="q" value={query} onChange={(e) => setQuery(e.target.value)} required />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <Label htmlFor="lim">Limit</Label>
              <Input
                id="lim"
                type="number"
                min={1}
                max={50}
                value={limit}
                onChange={(e) => setLimit(Number(e.target.value) || 1)}
              />
            </div>
            <div>
              <Label htmlFor="cid">Channel id (optional)</Label>
              <Input id="cid" type="number" placeholder="scope to one channel" value={channelId} onChange={(e) => setChannelId(e.target.value)} />
            </div>
            <div>
              <Label htmlFor="ct">Content type</Label>
              <select
                id="ct"
                value={contentType}
                onChange={(e) => setContentType(e.target.value as typeof contentType)}
                className="w-full rounded-xl border border-zinc-300 bg-white px-3 py-2.5 text-sm text-zinc-900 outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20"
              >
                <option value="">Any</option>
                <option value="post">post</option>
                <option value="summary">summary</option>
                <option value="profile">profile</option>
              </select>
            </div>
          </div>
          <Button type="submit" disabled={loading}>
            {loading ? <Spinner /> : <Layers className="size-4" />}
            Search
          </Button>
        </form>
      </Card>

      {error ? (
        <Alert variant="error" title="Semantic search failed">
          {error}
        </Alert>
      ) : null}

      {data?.synthesis_placeholder ? (
        <Alert variant="info" title="Synthesis (placeholder)">
          {data.synthesis_placeholder}
        </Alert>
      ) : null}

      {data?.hits?.length ? (
        <div className="space-y-3">
          <h2 className="text-lg font-medium text-zinc-900">Hits ({data.hits.length})</h2>
          <ul className="space-y-3">
            {data.hits.map((hit) => (
              <li key={hit.point_id}>
                <Card className="py-4">
                  <div className="flex flex-wrap items-center gap-2">
                    {hit.content_type ? <Badge tone="violet">{hit.content_type}</Badge> : null}
                    {hit.channel_id != null ? (
                      <Link href={`/channels/${hit.channel_id}`} className="text-sm font-medium text-violet-700 hover:text-violet-600">
                        Channel #{hit.channel_id}
                      </Link>
                    ) : null}
                    {hit.score != null ? (
                      <span className="text-xs text-zinc-500">score {hit.score.toFixed(3)}</span>
                    ) : null}
                  </div>
                  <p className="mt-2 text-sm text-zinc-700">{hit.text_preview ?? "—"}</p>
                </Card>
              </li>
            ))}
          </ul>
        </div>
      ) : data && !data.hits.length ? (
        <p className="text-sm text-zinc-500">No hits. Ingest content into the vector store or widen the query.</p>
      ) : null}
    </div>
  );
}
