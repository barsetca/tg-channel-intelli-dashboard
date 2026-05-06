import Link from "next/link";
import { ChevronRight, Trash2 } from "lucide-react";
import type { ChannelCard as ChannelCardType } from "@/lib/types/api";
import { Button } from "@/components/ui/button";

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

/**
 * Компактный список: вся строка ведёт на карточку канала (сценарий 1 — быстрый переход).
 */
export function ChannelSearchResultList({
  channels,
  onDelete,
}: {
  channels: ChannelCardType[];
  onDelete?: (channelId: number) => void;
}) {
  return (
    <ul className="divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      {channels.map((ch) => {
        const href = `/channels/${ch.id}?from=search`;
        const handle = ch.username ? `@${ch.username}` : `id:${ch.id}`;
        const title = ch.title ?? handle;
        return (
          <li key={ch.id}>
            <div className="flex items-center gap-4 px-4 py-3 transition hover:bg-violet-50/80">
              <Link href={href} className="min-w-0 flex-1">
                <p className="truncate font-medium text-zinc-900">{title}</p>
                <p className="truncate text-sm text-zinc-500">{handle}</p>
                {ch.topic_search ? (
                  <p className="mt-0.5 truncate text-xs text-zinc-500">topic_search: {ch.topic_search}</p>
                ) : null}
                {ch.primary_topic ? (
                  <p className="mt-0.5 truncate text-xs text-violet-700">{ch.primary_topic}</p>
                ) : null}
              </Link>
              {onDelete ? (
                <Button
                  type="button"
                  variant="ghost"
                  className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                  onClick={() => onDelete(ch.id)}
                  aria-label={`Удалить ${title}`}
                >
                  <Trash2 className="size-4" />
                </Button>
              ) : null}
              <div className="hidden shrink-0 text-right text-xs text-zinc-500 sm:block">
                <div>{ch.subscriber_count != null ? `${ch.subscriber_count.toLocaleString()} подписчиков` : "—"}</div>
                <div className="mt-0.5">Последний пост: {formatDate(ch.last_post_at)}</div>
                <div className="mt-0.5">По состоянию на: {formatDate(ch.last_sync_at)}</div>
              </div>
              <ChevronRight className="size-5 shrink-0 text-zinc-400" aria-hidden />
            </div>
          </li>
        );
      })}
    </ul>
  );
}
