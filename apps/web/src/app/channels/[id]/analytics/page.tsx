import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { ApiError, getChannel } from "@/lib/api-client";
import { ChannelAnalyzePanel } from "@/components/channel-analyze-panel";

export default async function ChannelAnalyticsPage({ params }: { params: Promise<{ id: string }> }) {
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

  return (
    <div className="mx-auto max-w-5xl space-y-8">
      <Link
        href={`/channels/${channel.id}`}
        className="inline-flex items-center gap-1 text-sm text-zinc-600 hover:text-zinc-900"
      >
        <ChevronLeft className="size-4" />
        Back to channel
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Analytics</h1>
        <p className="mt-2 text-sm text-zinc-600">
          {channel.title ?? channel.username ?? `Channel #${channel.id}`} — Scenario 2 deep dive with chart stubs until
          time-series endpoints land.
        </p>
      </div>
      <ChannelAnalyzePanel channel={channel} />
    </div>
  );
}
