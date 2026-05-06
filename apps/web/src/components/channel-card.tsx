import Link from "next/link";
import type { ChannelCard as ChannelCardType } from "@/lib/types/api";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";

function formatDate(iso: string | null) {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function ChannelCard({ channel }: { channel: ChannelCardType }) {
  const id = channel.id;
  const href = `/channels/${id}`;
  const handle = channel.username ? `@${channel.username}` : `id:${id}`;

  return (
    <Card className="transition hover:border-violet-300 hover:shadow-md">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link href={href} className="text-base font-semibold text-zinc-900 hover:text-violet-700">
            {channel.title ?? handle}
          </Link>
          <p className="mt-0.5 text-sm text-zinc-500">{handle}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {channel.primary_topic ? <Badge tone="violet">{channel.primary_topic}</Badge> : null}
        </div>
      </div>
      {channel.description ? (
        <p className="mt-3 line-clamp-2 text-sm text-zinc-600">{channel.description}</p>
      ) : null}
      <div className="mt-4 flex flex-wrap gap-4 text-xs text-zinc-500">
        <span>Subs: {channel.subscriber_count?.toLocaleString() ?? "—"}</span>
        <span>Posts/wk: {channel.posts_per_week_estimate?.toFixed(1) ?? "—"}</span>
        <span>Last post: {formatDate(channel.last_post_at)}</span>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <Link href={href} className="text-sm font-medium text-violet-700 hover:text-violet-600">
          Open channel →
        </Link>
        <Link href={`${href}/analytics`} className="text-sm text-zinc-500 hover:text-zinc-800">
          Analytics
        </Link>
        <Link
          href={`/channel-analysis?channel_ref=${encodeURIComponent(channel.username ? `@${channel.username}` : String(channel.telegram_id))}`}
          className="text-sm text-zinc-500 hover:text-zinc-800"
        >
          Analyze
        </Link>
        <Link href={`${href}/recommendations`} className="text-sm text-zinc-500 hover:text-zinc-800">
          Recommendations
        </Link>
      </div>
    </Card>
  );
}
