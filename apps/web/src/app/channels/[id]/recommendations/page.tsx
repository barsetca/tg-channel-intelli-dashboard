import Link from "next/link";
import { notFound } from "next/navigation";
import { ChevronLeft } from "lucide-react";
import { ApiError, getChannel, getRecommendations } from "@/lib/api-client";
import { Card, CardDescription, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert } from "@/components/ui/alert";

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
    rec = await getRecommendations(channel.id, 5);
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
        Назад к каналу
      </Link>
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">Похожие каналы</h1>
        <p className="mt-2 text-sm text-zinc-600">
          Сценарий 6 — подбор до 5 похожих каналов для{" "}
          <span className="font-medium text-zinc-800">{channel.title ?? channel.username ?? `#${channel.id}`}</span>
          {channel.username ? (
            <>
              {" "}
              (
              <a
                href={`https://t.me/${channel.username.replace(/^@/, "")}`}
                target="_blank"
                rel="noreferrer"
                className="text-violet-700 hover:text-violet-600"
              >
                @{channel.username}
              </a>
              )
            </>
          ) : null}
          .
        </p>
      </div>

      <Card>
        <CardTitle>Рекомендации</CardTitle>
        <CardDescription>Ранжирование учитывает семантическую близость, темы, стиль и частоту публикаций.</CardDescription>
        {(rec.quality_notes ?? []).length > 0 ? (
          <div className="mt-4 space-y-2">
            {(rec.quality_notes ?? []).map((note) => (
              <p key={note} className="text-xs leading-relaxed text-zinc-600">{note}</p>
            ))}
          </div>
        ) : null}
        {rec.needs_review ? (
          <div className="mt-4">
            <Alert variant="warning" title="Нужна подготовка данных">
              {rec.reason ?? "Недостаточно данных для устойчивой рекомендации."}
            </Alert>
          </div>
        ) : rec.results.length === 0 ? (
          <p className="mt-4 text-sm text-zinc-500">Похожие каналы пока не найдены.</p>
        ) : (
          <ul className="mt-4 divide-y divide-zinc-200">
            {rec.results.map((s) => (
              <li key={s.channel_id} className="flex flex-wrap items-center justify-between gap-3 py-4 first:pt-0">
                <div>
                  <Link
                    href={`/channels/${s.channel_id}?from_similar=1&seed_channel_id=${encodeURIComponent(String(channel.id))}`}
                    className="font-medium text-violet-700 hover:text-violet-600"
                  >
                    {s.title ?? s.channel_username ?? `Канал ${s.channel_id}`}
                  </Link>
                  {s.channel_username ? (
                    <p className="text-sm text-zinc-500">
                      <a
                        href={`https://t.me/${s.channel_username.replace(/^@/, "")}`}
                        target="_blank"
                        rel="noreferrer"
                        className="hover:text-violet-600"
                      >
                        @{s.channel_username}
                      </a>
                    </p>
                  ) : null}
                  {s.reasons.length ? (
                    <div className="mt-1 space-y-1">
                      {s.reasons.map((reason) => (
                        <p key={reason} className="text-sm text-zinc-600">
                          {reason}
                        </p>
                      ))}
                    </div>
                  ) : null}
                  {s.supporting_topics.length ? (
                    <p className="mt-1 text-xs text-zinc-500">Темы: {s.supporting_topics.slice(0, 4).join(", ")}</p>
                  ) : null}
                  {s.missing_data?.length ? (
                    <p className="mt-1 text-xs text-amber-800">Ограничения данных: {s.missing_data.join(" ")}</p>
                  ) : null}
                </div>
                <Badge tone="violet">{`${(s.score * 100).toFixed(0)}% совпадение`}</Badge>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
