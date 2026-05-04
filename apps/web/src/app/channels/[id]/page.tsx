import Link from "next/link";
import { notFound } from "next/navigation";
import { ExternalLink, BarChart3, Sparkles, Users } from "lucide-react";
import { ApiError, getChannel } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { ChannelSummarizeSection } from "@/components/channel-summarize-section";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

export default async function ChannelPage({ params }: { params: Promise<{ id: string }> }) {
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

  const handle = channel.username ? `@${channel.username}` : `id:${channel.id}`;
  const tgLink =
    channel.username != null ? `https://t.me/${channel.username.replace(/^@/, "")}` : null;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
            {channel.title ?? handle}
          </h1>
          <p className="mt-1 text-sm text-zinc-500">{handle}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {channel.primary_topic ? <Badge tone="violet">{channel.primary_topic}</Badge> : null}
            {channel.sync_status ? <Badge tone="neutral">sync: {channel.sync_status}</Badge> : null}
            {channel.is_public_accessible === false ? (
              <Badge tone="warning">Limited public access</Badge>
            ) : null}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {tgLink ? (
            <a
              href={tgLink}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-2 rounded-xl border border-zinc-300 px-3 py-2 text-sm text-zinc-800 hover:border-violet-400 hover:bg-violet-50/50"
            >
              <ExternalLink className="size-4" />
              Open in Telegram
            </a>
          ) : null}
          <Link
            href={`/channels/${channel.id}/analytics`}
            className="inline-flex items-center gap-2 rounded-xl bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500"
          >
            <BarChart3 className="size-4" />
            Analytics
          </Link>
          <Link
            href={`/channels/${channel.id}/recommendations`}
            className="inline-flex items-center gap-2 rounded-xl border border-zinc-300 px-3 py-2 text-sm text-zinc-800 hover:border-violet-400 hover:bg-violet-50/50"
          >
            <Users className="size-4" />
            Similar
          </Link>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardTitle>Audience & cadence</CardTitle>
          <CardDescription>Public metadata snapshot (Scenario 1 card fields).</CardDescription>
          <dl className="mt-4 space-y-2 text-sm">
            <div className="flex justify-between gap-4 border-b border-zinc-200 py-2">
              <dt className="text-zinc-500">Subscribers</dt>
              <dd className="text-zinc-900">{channel.subscriber_count?.toLocaleString() ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-zinc-200 py-2">
              <dt className="text-zinc-500">Posts / week (est.)</dt>
              <dd className="text-zinc-900">{channel.posts_per_week_estimate?.toFixed(1) ?? "—"}</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-zinc-200 py-2">
              <dt className="text-zinc-500">Last post</dt>
              <dd className="text-zinc-900">{formatDate(channel.last_post_at)}</dd>
            </div>
            <div className="flex justify-between gap-4 border-b border-zinc-200 py-2">
              <dt className="text-zinc-500">Last sync</dt>
              <dd className="text-zinc-900">{formatDate(channel.last_sync_at)}</dd>
            </div>
            <div className="flex justify-between gap-4 py-2">
              <dt className="text-zinc-500">Language / region</dt>
              <dd className="text-right text-zinc-900">
                {[channel.language_hint, channel.region_country].filter(Boolean).join(" · ") || "—"}
              </dd>
            </div>
          </dl>
        </Card>
        <Card>
          <CardTitle>Description</CardTitle>
          <CardDescription>Invite slug for deep links when present.</CardDescription>
          <p className="mt-4 text-sm leading-relaxed text-zinc-700">
            {channel.description ?? "No description stored yet."}
          </p>
          {channel.invite_slug ? (
            <p className="mt-3 text-xs text-zinc-500">
              invite: <code className="text-zinc-700">{channel.invite_slug}</code>
            </p>
          ) : null}
        </Card>
      </div>

      <div className="flex items-start gap-3 rounded-xl border border-cyan-200 bg-cyan-50 p-4 text-sm text-cyan-950">
        <Sparkles className="mt-0.5 size-5 shrink-0 text-cyan-600" />
        <p>
          Run <Link className="font-medium text-cyan-800 underline-offset-2 hover:underline" href={`/semantic-search`}>semantic search</Link>{" "}
          scoped to this channel id to probe the post corpus, or open{" "}
          <Link className="font-medium text-cyan-800 underline-offset-2 hover:underline" href={`/channels/${channel.id}/analytics`}>
            analytics
          </Link>{" "}
          for the full analysis workflow (Scenario 2).
        </p>
      </div>

      <ChannelSummarizeSection channelId={channel.id} />
    </div>
  );
}
