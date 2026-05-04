import Link from "next/link";
import { ChevronRight } from "lucide-react";
import type { ChannelCard as ChannelCardType } from "@/lib/types/api";

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
export function ChannelSearchResultList({ channels }: { channels: ChannelCardType[] }) {
  return (
    <ul className="divide-y divide-zinc-200 overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-sm">
      {channels.map((ch) => {
        const href = `/channels/${ch.id}`;
        const handle = ch.username ? `@${ch.username}` : `id:${ch.id}`;
        const title = ch.title ?? handle;
        return (
          <li key={ch.id}>
            <Link
              href={href}
              className="flex items-center gap-4 px-4 py-3 transition hover:bg-violet-50/80 active:bg-violet-100/60"
            >
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-zinc-900">{title}</p>
                <p className="truncate text-sm text-zinc-500">{handle}</p>
                {ch.primary_topic ? (
                  <p className="mt-0.5 truncate text-xs text-violet-700">{ch.primary_topic}</p>
                ) : null}
              </div>
              <div className="hidden shrink-0 text-right text-xs text-zinc-500 sm:block">
                <div>{ch.subscriber_count != null ? `${ch.subscriber_count.toLocaleString()} subs` : "—"}</div>
                <div className="mt-0.5">{formatDate(ch.last_post_at)}</div>
              </div>
              <ChevronRight className="size-5 shrink-0 text-zinc-400" aria-hidden />
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
