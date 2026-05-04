import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { ApiError, getChannel, getRecommendations } from "@/lib/api-client";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export default async function RecommendationsPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const numericId = Number(id);
  if (!Number.isFinite(numericId)) notFound();

  let channel;
  try {
    channel = await getChannel(numericId);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  let rec;
  try {
    rec = await getRecommendations(channel.id, 12);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <Link
        href={`/channels/${channel.id}`}
        className="inline-flex items-center gap-1 text-sm text-zinc-600 hover:text-zinc-900"
      >
        <ChevronLeft className="size-4" />
        Back to channel
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Similar channels</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Scenario 6 — vector neighborhood from{" "}
          <span className="font-medium text-zinc-800">{channel.title ?? channel.username ?? `#${channel.id}`}</span>.
        </p>
      </div>

      <Card>
        <CardTitle>Recommendations</CardTitle>
        <CardDescription>Ranked by similarity score when the backend provides it.</CardDescription>
        {rec.similar.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-500">No similar channels yet — index may be empty.</p>
        ) : (
          <ul className="mt-4 divide-y divide-zinc-200">
            {rec.similar.map((s) => (
              <li key={s.channel_id} className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0">
                <div>
                  <Link href={`/channels/${s.channel_id}`} className="font-medium text-violet-700 hover:text-violet-600">
                    {s.title ?? s.username ?? `Channel ${s.channel_id}`}
                  </Link>
                  {s.username ? <p className="text-sm text-zinc-500">@{s.username}</p> : null}
                </div>
                {s.score != null ? (
                  <Badge tone="violet">
                    {s.score >= 0 && s.score <= 1 ? `${(s.score * 100).toFixed(0)}% match` : `score ${s.score.toFixed(4)}`}
                  </Badge>
                ) : (
                  <Badge tone="neutral">score n/a</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
